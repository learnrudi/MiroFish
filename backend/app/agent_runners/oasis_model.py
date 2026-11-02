"""CAMEL boundary for one reviewed Codex create_post decision.

This does not create Compute jobs or make model API calls. The injected
exchange supplies a reviewed response to the actual CAMEL message/tool packet.
"""

import hashlib
import json
import logging
import re

from camel.models import BaseModelBackend
from camel.utils import BaseTokenCounter
from openai.types.chat import ChatCompletion

logger = logging.getLogger(__name__)


def validate_decision(response, digest):
    """Only the exact reviewed request may yield one bounded create_post call."""
    if not isinstance(response, dict) or set(response) != {
        "schema_version", "request_sha256", "tool_call"
    }:
        raise ValueError("Invalid response envelope")
    if type(response["schema_version"]) is not int or response["schema_version"] != 1:
        raise ValueError("Unsupported response version")
    if response["request_sha256"] != digest:
        raise ValueError("Response does not match this request")
    call = response["tool_call"]
    if not isinstance(call, dict) or set(call) != {"name", "arguments"}:
        raise ValueError("Expected exactly one tool call")
    if call["name"] != "create_post":
        raise ValueError("Only create_post is supported by this experiment")
    args = call["arguments"]
    if not isinstance(args, dict) or set(args) != {"content"}:
        raise ValueError("create_post requires only content")
    content = args["content"]
    if not isinstance(content, str) or not content.strip() or len(content) > 280:
        raise ValueError("Post content must contain 1-280 characters")
    return call


class ByteCounter(BaseTokenCounter):
    """Conservative context budget for this bounded fixture, not usage billing."""

    def encode(self, text):
        return list(text.encode("utf-8"))

    def decode(self, tokens):
        return bytes(tokens).decode("utf-8")

    def count_tokens_from_messages(self, messages):
        return len(str(messages).encode("utf-8")) + 32


class ReviewedActionModel(BaseModelBackend):
    def __init__(self, exchange, *, identity, model, effort):
        if not all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._-]{1,80}", value)
                   for value in (identity, model, effort)):
            raise ValueError("Runner identity, model and effort must be explicit identifiers")
        super().__init__(model_type=model, max_retries=0)
        self.exchange = exchange
        self.identity = identity
        self.effort = effort
        self.last_error = None

    @property
    def token_counter(self):
        return ByteCounter()

    @property
    def token_limit(self):
        return 65536

    def _run(self, messages, response_format=None, tools=None):
        self.last_error = None
        try:
            return self._complete(messages, response_format, tools)
        except Exception as error:
            # OASIS catches model exceptions; the harness must inspect this.
            self.last_error = error
            logger.warning("runner_decision_failed", extra={"error_type": type(error).__name__})
            raise

    def _complete(self, messages, response_format, tools):
        if response_format is not None:
            raise ValueError("Structured text responses are outside this one-action experiment")
        if not isinstance(messages, list) or not messages or not all(
            isinstance(message, dict) and message.get("role") in {"system", "user", "assistant"}
            and isinstance(message.get("content"), str) for message in messages
        ):
            raise ValueError("This experiment requires text-only conversation messages")
        if (not isinstance(tools, list) or len(tools) != 1
                or not isinstance(tools[0], dict)
                or tools[0].get("type") != "function"
                or not isinstance(tools[0].get("function"), dict)
                or tools[0].get("function", {}).get("name") != "create_post"):
            raise ValueError("Exactly the create_post tool must be offered")
        body = {
            "schema_version": 1,
            "runner": {"provider": "codex", "identity": self.identity,
                       "model": str(self.model_type), "effort": self.effort},
            "messages": messages,
            "tools": tools,
        }
        encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > 65536:
            raise ValueError("Request exceeds the experiment's 64 KiB budget")
        digest = hashlib.sha256(encoded).hexdigest()
        packet = {**body, "request_sha256": digest}
        logger.info("runner_decision_requested", extra={"request_sha256": digest, "identity": self.identity})
        call = validate_decision(self.exchange(packet), digest)
        return ChatCompletion(
            id=f"chatcmpl-{digest}", created=0, model=str(self.model_type),
            object="chat.completion", choices=[{
                "index": 0, "finish_reason": "tool_calls",
                "message": {"role": "assistant", "content": None, "tool_calls": [{
                    "id": f"call_{digest}", "type": "function",
                    "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])},
                }]},
            }],
        )

    async def _arun(self, messages, response_format=None, tools=None):
        return self._run(messages, response_format, tools)
