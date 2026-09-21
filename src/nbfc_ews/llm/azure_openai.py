"""Azure Open AI, through the Responses API.

Stateless on purpose: store=False on every call and never apreviouse_response_id,
so nothing about a case is kept oon Azure's side. The whole history travels with
each request instead.

Logs carry_ids, token counts, and timings - never message text. Borrows facts are PII,
and a log line is the easiest place for them to leak."""


import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any

from nbfc_ews.config import (
    AZURE_CHAT_DEPLOYMENT,
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
)
from nbfc_ews.llm.base import Message, ModelReply, ToolCall, ToolSpec, Usage

log = logging.getLogger(__name__)

# Worth waiting for. Everything else is a bad request, and retrying a bad
# request only burns quota. 0 stands for "never got an HTTP answer at all"
RETRYABLE = frozenset({0, 429, 500, 502, 503, 504})

class ModelError(Exception):
    """The model service refused the request or returned something unuseable."""

class ModelIncomplete(ModelError):
    """The model stopped early - usually its output budget ran out mid-thought."""

class ContentBlocked(ModelError):
    """Azure's content filter blocked the prompt or the completion."""

class TransportError(Exception):
    """An HTTP failure, before anyone has decided what it means."""

    def __init__(self, status: int, body: str, retry_after: float | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body
        self.retry_after = retry_after

Transport = Callable[[dict[str, Any]], dict[str, Any]]

def http_transport(url: str, api_key: str, timeout: float) -> Transport:
    """The real thing. Tests pass their own function instead."""

    def send(body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json", "api-key": api_key}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result: dict[str, Any] = json.loads(response.read())
                return result
        except urllib.error.HTTPError as exc:
            raise TransportError(
                exc.code,
                exc.read().decode(errors="replace")[:500],
                _retry_after(exc.headers.get("Retry-After") if exc.headers else None),
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TransportError(0, str(exc)) from exc

    return send

def _retry_after(value: str | None) -> float | None:
    """Seconds, if Azure said so. The header can also be ba date; ignore that."""
    try:
        return float(value) if value else None
    except ValueError:
        return None

class AzureChatModel:
    """The ChatModel protocol, implemented against a real deployment."""

    def __init__(
            self,
            *,
            endpoint: str = AZURE_OPENAI_ENDPOINT,
            api_key: str = AZURE_OPENAI_API_KEY,
            deployment: str = AZURE_CHAT_DEPLOYMENT,
            reasoning_effort: str = "low",
            max_output_tokens: int = 4000,
            timeout: float = 60.0,
            max_retries: int = 3,
            backoff: float = 1.0,
            transport: Transport | None = None,
            sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not deployment:
            raise ModelError("AZURE_CHAT_DEPLOYMENT is not set")
        if transport is None:
            if not endpoint or not api_key:
                raise ModelError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set")
            url = f"{endpoint.rstrip('/')}/openai/v1/responses"
            transport = http_transport(url, api_key, timeout)

        self._deployment = deployment
        self._reasoning_effort = reasoning_effort
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        self._backoff = backoff
        self._transport = transport
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self._deployment

    def complete(
            self,
            messages: Sequence[Message],
            tools: Sequence[ToolSpec] = (),
    ) -> ModelReply:
        body : dict[str, Any] = {
            "model": self._deployment,
            "input": to_input(messages),
            "store": False,
            "reasoning": {"effort": self._reasoning_effort},
            "max_output_tokens": self._max_output_tokens,
        }
        if tools:
            body["tools"] = [to_tool(spec) for spec in tools]

        started = time.monotonic()
        raw = self._send(body)
        reply = from_response(raw)

        usage = raw.get("usage") or {}
        log.info (
            "model call id=%s model=%s in=%d  out=%d reasoning=%d tools=%d ms=%d",
            raw.get("id"),
            reply.model,
            reply.usage.input_tokens,
            reply.usage.output_tokens,
            (usage.get("output_token_details") or {}).get("reasoning_tokens", 0),
            len(reply.tool_calls),
            (time.monotonic() - started)*1000
        )
        return reply

    def _send(self, body: dict[str, Any]) -> dict[str, Any]:
        attempt = 0
        while True:
            try:
                return self._transport(body)
            except TransportError as exc:
                if exc.status not in RETRYABLE or attempt >= self._max_retries:
                    raise _interpret(exc) from exc
                delay = exc.retry_after if exc.retry_after is not None else self._backoff * 2 **attempt
                attempt += 1
                log.warning("model call retry %d after HTTP %d, waiting %.1fs", attempt, exc.status, delay)
                self._sleep(delay)

def _interpret(exc: TransportError) -> ModelError:
    """A 400 carrying 'content_filter' means the prompt itself was blocked."""
    if exc.status == 400 and "content_filter" in exc.body:
        return ContentBlocked("the prompt was blocked by Azure's content filter")
    return ModelError(f"Azure returned {exc.status}: {exc.body}")


# --- mapping out: our messages  -> Response API input ---------------------------------------------------------

def to_input(messages: Sequence[Message]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if message.tool_call_id is None:
                raise ModelError("a tool message must carry the tool_call_id it answers")
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
        elif message.role == "assistant" and message.tool_calls:
            if message.content:
                items.append({
                    "role": "assistant", "content": message.content
                })
            items.extend(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                    for call in message.tool_calls
                )
        else:
            items.append ({"role": message.role, "content": message.content})
    return items

def to_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": spec.parameters,
        "strict": True,
    }

# --- mapping in: Responses API output  ->  our ModelReply --------------------------------------------

def from_response(raw: dict[str, Any]) -> ModelReply:
    status = raw.get("status")
    if status == "incomplete":
        reason = (raw.get("incomplete_details") or {}).get("reason", "unknown")
        if reason == "content_filter":
            raise ContentBlocked("the completion was blocked by azure's content filter")
        raise ModelIncomplete(f"the model stopped early: {reason}")
    if status != "completed":
        raise ModelError(f"unexpected response status: {status!r}")
    if any(f.get("blocked") for f in raw.get("content_filters") or []):
        raise ContentBlocked("Azure's content filter blocked this response")

    texts: list[str] = []
    calls: list[ToolCall] = []
    for item in raw.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            texts.extend(
                part["text"] for part in item.get("content") or [] if part.get("type") == "output_text"
            )
        elif kind == "function_call":
            calls.append(
                ToolCall(id=item["call_id"], name=item["name"], arguments=_arguments(item))
            )

        # "reasoning" items are the model's private working. Ignored.

    usage = raw.get("usage") or {}
    return ModelReply(
        text= "".join(texts) or None,
        tool_calls=tuple(calls),
        usage=Usage(input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    ),
                    model=raw.get("model",""),
        )

def _arguments(item: dict[str, Any]) -> dict[str, Any]:
    """Arguments arrive as a JSON *string*, Never echo them in an error - they
    can carry account_ids."""

    try:
        parsed = json.loads(item.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        raise ModelError(f"too {item.get('name')!r}: arguments are not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ModelError(f"tool {item.get('name')!r}: arguments are not a JSON object")
    return parsed 

