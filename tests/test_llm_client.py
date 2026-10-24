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
