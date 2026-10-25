"""Exercise real SDK serialization against an in-memory HTTP transport, no network."""

import json

import httpx
import openai
import pytest

from llm_client import CompatibleClient, LLMError, OpenAIClient

SCHEMA = {
    "type": "function",
    "name": "list_files",
    "description": "List files",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    },
}


def chat_response(**changes):
    return {
        "id": "chat-123",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "tool-123",
                            "type": "function",
                            "function": {"name": "list_files", "arguments": "{}"},
                            "extra_content": {
                                "google": {"thought_signature": "opaque-test-signature"}
                            },
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        **changes,
    }


def mock_client(client, handler, base_url):
    client._client = openai.OpenAI(
        api_key="test-wire-key",
        base_url=base_url,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return client


@pytest.mark.parametrize(
    "provider,host",
    [
        ("gemini", "generativelanguage.googleapis.com"),
        ("groq", "api.groq.com"),
    ],
)
def test_compatible_wire_format_preserves_tool_signatures_and_results(provider, host):
    requests = []

    def handler(request):
        requests.append((request.url, json.loads(request.content)))
        return httpx.Response(200, json=chat_response())

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", provider),
        handler,
        CompatibleClient.ENDPOINTS[provider],
    )
    messages = [{"role": "user", "content": "Inspect"}]
    first = client.respond(messages, [SCHEMA])
    assert first.calls[0].name == "list_files"
    messages.extend(first.items)
    messages.append(
        {"type": "function_call_output", "call_id": "tool-123", "output": '{"ok":true}'}
    )
    client.respond(messages, [SCHEMA])
    url, body = requests[-1]
    assert url.host == host
    assert body["messages"][-1] == {
        "role": "tool",
        "tool_call_id": "tool-123",
        "content": '{"ok":true}',
    }
    signature = body["messages"][1]["tool_calls"][0]["extra_content"]["google"]["thought_signature"]
    assert signature == "opaque-test-signature"
    assert body["tools"][0]["function"]["name"] == "list_files"
    assert "strict" not in body["tools"][0]["function"]
    assert body.get("disable_tool_validation", False) is (provider == "groq")


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_final_report_request_forces_named_tool_with_provider_validation(provider):
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=chat_response())

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", provider),
        handler,
        CompatibleClient.ENDPOINTS[provider],
    )
    client.respond([], [{**SCHEMA, "name": "submit_report"}])
    assert captured[0]["tool_choice"] == {"type": "function", "function": {"name": "submit_report"}}
    assert not captured[0].get("disable_tool_validation", False)


@pytest.mark.parametrize(
    "status,expected", [(401, "authentication"), (429, "quota"), (400, "HTTP 400")]
)
def test_provider_errors_do_not_echo_raw_credentials(status, expected):
    secret = "raw-remote-error-credential-12345"
    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "gemini"),
        lambda request: httpx.Response(status, json={"error": {"message": secret}}),
        CompatibleClient.ENDPOINTS["gemini"],
    )
    with pytest.raises(LLMError, match=expected) as caught:
        client.respond([], [SCHEMA])
    assert secret not in str(caught.value)


def test_incomplete_output_is_a_failure():
    response = chat_response()
    response["choices"][0]["finish_reason"] = "length"
    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "groq"),
        lambda request: httpx.Response(200, json=response),
        CompatibleClient.ENDPOINTS["groq"],
    )
    with pytest.raises(LLMError, match="incomplete"):
        client.respond([], [SCHEMA])


def test_groq_request_budget_reduction_preserves_evidence():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["max_tokens"] > 1024:
            return httpx.Response(413, json={"error": {"message": "Request too large"}})
        return httpx.Response(200, json=chat_response())

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "groq"),
        handler,
        CompatibleClient.ENDPOINTS["groq"],
    )
    messages = [{"role": "user", "content": "Evidence remains unchanged"}]
    assert client.respond(messages, [SCHEMA]).calls[0].name == "list_files"
    assert [request["max_tokens"] for request in requests] == [4096, 2048, 1024]
    assert all(request["messages"] == messages for request in requests)
    assert all(request["tools"] == requests[0]["tools"] for request in requests)


def test_groq_oversized_request_retries_are_bounded():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(413, json={"error": {"message": "Request too large"}})

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "groq"),
        handler,
        CompatibleClient.ENDPOINTS["groq"],
    )
    with pytest.raises(LLMError, match="HTTP 413"):
        client.respond([], [SCHEMA])
    assert len(requests) == 3


def test_groq_invalid_tool_generation_gets_bounded_repair_feedback():
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "code": "tool_use_failed",
                        "message": "Invalid tool call generated",
                        "failed_generation": "private-provider-debug",
                    }
                },
            )
        return httpx.Response(200, json=chat_response())

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "groq"),
        handler,
        CompatibleClient.ENDPOINTS["groq"],
    )
    messages = [{"role": "user", "content": "Inspect"}]
    result = client.respond(messages, [SCHEMA])
    assert result.calls[0].name == "list_files"
    assert result.usage["tool_generation_retries"] == 1
    assert len(requests) == 2
    assert "valid JSON" in requests[1]["messages"][-1]["content"]
    assert "private-provider-debug" not in json.dumps(requests)
    assert messages == [{"role": "user", "content": "Inspect"}]


@pytest.mark.parametrize("tool_failure,attempts", [(True, 3), (False, 1)])
def test_only_repairable_tool_errors_are_retried(tool_failure, attempts):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": ("tool_use_failed" if tool_failure else "invalid_model"),
                    "message": "Request rejected",
                }
            },
        )

    client = mock_client(
        CompatibleClient("wire-test-key-1234", "test-model", "groq"),
        handler,
        CompatibleClient.ENDPOINTS["groq"],
    )
    with pytest.raises(LLMError, match="HTTP 400"):
        client.respond([], [SCHEMA])
    assert len(requests) == attempts


def test_openai_responses_wire_format_keeps_full_output_items():
    captured = []

    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "model": "gpt-4.1-mini",
                "status": "completed",
                "output": [
                    {
                        "type": "function_call",
                        "id": "fc_123",
                        "call_id": "call-123",
                        "name": "list_files",
                        "arguments": "{}",
                        "status": "completed",
                    }
                ],
                "parallel_tool_calls": False,
                "tool_choice": "required",
                "tools": [SCHEMA],
            },
        )

    client = mock_client(
        OpenAIClient("wire-test-key-1234", "gpt-4.1-mini"), handler, "https://api.openai.com/v1"
    )
    result = client.respond([{"role": "user", "content": "Inspect"}], [SCHEMA])
    assert result.calls[0].call_id == "call-123"
    assert result.items[0]["type"] == "function_call"
    assert captured[0]["store"] is False
    assert captured[0]["tools"][0]["strict"] is True
