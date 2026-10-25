"""Small provider adapter. Agent control flow lives in agent_loop, not in an SDK."""

from __future__ import annotations

from dataclasses import dataclass, field

from safety import register_secret


class LLMError(RuntimeError):
    pass


def _failed_tool_generation(error) -> bool:
    body = error.body
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        body = body.get("error", body)
    return isinstance(body, dict) and (
        body.get("code") == "tool_use_failed" or "failed_generation" in body
    )


@dataclass
class ToolCall:
    name: str
    arguments: str
    call_id: str


@dataclass
class ModelTurn:
    items: list[dict]
    calls: list[ToolCall]
    text: str = ""
    usage: dict = field(default_factory=dict)


class OpenAIClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60):
        import openai

        register_secret(api_key)
        self._openai = openai
        self._client = openai.OpenAI(
            api_key=api_key, base_url="https://api.openai.com/v1", timeout=timeout, max_retries=2
        )
        self.model = model

    def respond(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        api = self._openai
        try:
            response = self._client.responses.create(
                model=self.model,
                input=messages,
                tools=tools,
                tool_choice="required",
                parallel_tool_calls=False,
                max_output_tokens=12000,
                store=False,
                include=["reasoning.encrypted_content"],
            )
        except api.AuthenticationError as exc:
            raise LLMError("LLM authentication failed; check OPENAI_API_KEY locally.") from exc
        except api.RateLimitError as exc:
            raise LLMError(
                "LLM rate/quota limit reached; check API billing or retry later."
            ) from exc
        except api.APITimeoutError as exc:
            raise LLMError(
                "LLM request timed out after bounded retries; increase --timeout or retry."
            ) from exc
        except api.APIConnectionError as exc:
            raise LLMError("Cannot reach the LLM API; check your network connection.") from exc
        except api.APIStatusError as exc:
            raise LLMError(
                f"LLM API rejected the request (HTTP {exc.status_code}); "
                "check model access and tool support. No completed report was produced."
            ) from exc
        if response.status != "completed":
            raise LLMError(
                "LLM response was incomplete or refused; no completed report was produced."
            )
        # Preserve all output items for subsequent requests, including reasoning items required
        # by some models. Raw reasoning is never emitted to logs or trace files.
        items = [item.model_dump(mode="json", exclude_none=True) for item in response.output]
        calls = [
            ToolCall(item.name, item.arguments, item.call_id)
            for item in response.output
            if item.type == "function_call"
        ]
        usage = response.usage.model_dump(mode="json") if response.usage else {}
        return ModelTurn(items, calls, response.output_text, usage)


class CompatibleClient:
    """Gemini/Groq Chat Completions adapter using only the basic HTTP SDK.

    Our agent retains its own loop. Tool signatures are passed back intact for
    Gemini; no model reasoning text is written to traces.
    """

    ENDPOINTS = {
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "groq": "https://api.groq.com/openai/v1",
    }

    def __init__(self, api_key: str, model: str, provider: str, timeout: float = 60):
        import openai

        if provider not in self.ENDPOINTS:
            raise LLMError("Unsupported compatible provider.")
        register_secret(api_key)
        self._openai = openai
        self._client = openai.OpenAI(
            api_key=api_key, base_url=self.ENDPOINTS[provider], timeout=timeout, max_retries=2
        )
        self.provider = provider
        self.model = model
        self.context_budget = 24000 if provider == "groq" else None

    @staticmethod
    def chat_messages(messages: list[dict]) -> list[dict]:
        result = []
        for item in messages:
            if item.get("type") == "function_call_output":
                result.append(
                    {"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]}
                )
            elif "role" in item:
                result.append(item)
            else:
                raise LLMError("Unexpected message type in compatible-provider conversation.")
        return result

    def respond(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        api = self._openai
        chat_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]
        try:
            output_budget = 4096 if self.provider == "groq" else 8192
            generation_retries = 0
            request_messages = self.chat_messages(messages)
            while True:
                try:
                    response = self._client.chat.completions.create(
                        model=self.model,
                        messages=request_messages,
                        tools=chat_tools,
                        tool_choice="required"
                        if len(tools) == 1 and tools[0]["name"] == "submit_report"
                        else "auto",
                        parallel_tool_calls=False,
                        max_tokens=output_budget,
                        # Groq can reject unknown generated tool names before our
                        # controller gets to return corrective feedback. Keep
                        # execution/schema validation in our Python allowlist.
                        extra_body={"disable_tool_validation": True}
                        if self.provider == "groq"
                        else {},
                    )
                    break
                except api.APIStatusError as exc:
                    # Some free accounts count the requested output allowance in
                    # their request-size budget. Reduce that allowance, not the
                    # evidence or tool schemas. At most two additional attempts.
                    if self.provider == "groq" and exc.status_code == 413 and output_budget > 1024:
                        output_budget //= 2
                        continue
                    if (
                        self.provider == "groq"
                        and exc.status_code == 400
                        and _failed_tool_generation(exc)
                        and generation_retries < 2
                    ):
                        generation_retries += 1
                        request_messages = [
                            *request_messages,
                            {
                                "role": "user",
                                "content": (
                                    "The provider could not parse your last tool call. Return one valid "
                                    "function call using an exact provided name and all required parameters. "
                                    "Arguments must be valid JSON. Continue the same investigation."
                                ),
                            },
                        ]
                        continue
                    raise
        except api.AuthenticationError as exc:
            raise LLMError(
                f"LLM authentication failed; check {self.provider.upper()}_API_KEY locally."
            ) from exc
        except api.RateLimitError as exc:
            raise LLMError(
                "LLM rate/quota limit reached after bounded retries. Check your provider's free-tier "
                "quota; wait for reset, use a smaller repository, or choose another provider."
            ) from exc
        except api.APITimeoutError as exc:
            raise LLMError(
                "LLM request timed out after bounded retries; increase --timeout or retry."
            ) from exc
        except api.APIConnectionError as exc:
            raise LLMError("Cannot reach the LLM API; check your network connection.") from exc
        except api.APIStatusError as exc:
            raise LLMError(
                f"LLM API rejected the request (HTTP {exc.status_code}); check the configured model, "
                "provider quota, input size, and tool support. No completed report was produced."
            ) from exc
        if not response.choices:
            raise LLMError("LLM returned no choices; no completed report was produced.")
        choice = response.choices[0]
        if choice.finish_reason not in {"stop", "tool_calls"}:
            raise LLMError(
                "LLM response was incomplete or refused; no completed report was produced."
            )
        message = choice.message
        if message.refusal:
            raise LLMError("LLM refused the request; no completed report was produced.")
        tool_calls = message.tool_calls or []
        if any(call.type != "function" for call in tool_calls):
            raise LLMError("LLM returned an unsupported tool-call type.")
        assistant = {"role": "assistant", "content": message.content}
        if tool_calls:
            # model_dump retains vendor extra_content such as Gemini thought signatures.
            assistant["tool_calls"] = [
                call.model_dump(mode="json", exclude_none=True) for call in tool_calls
            ]
        calls = [
            ToolCall(call.function.name, call.function.arguments, call.id) for call in tool_calls
        ]
        usage = response.usage.model_dump(mode="json") if response.usage else {}
        usage.update(tool_generation_retries=generation_retries, output_allowance=output_budget)
        return ModelTurn([assistant], calls, message.content or "", usage)


def create_client(settings):
    if settings.provider == "openai":
        return OpenAIClient(settings.api_key, settings.model, settings.timeout)
    return CompatibleClient(settings.api_key, settings.model, settings.provider, settings.timeout)
