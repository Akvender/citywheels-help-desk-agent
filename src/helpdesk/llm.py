"""The only module that talks to the LLM provider."""

from typing import Protocol

import openai

from helpdesk.config import LLMSettings

TIMEOUT_SECONDS = 60
MAX_RETRIES = 2
UNUSABLE_FINISH_REASONS = ("length", "content_filter")


class ModelError(Exception):
    """The model could not be reached or refused the request."""


class ChatModel(Protocol):
    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        """Return the raw assistant message."""


class OpenAICompatibleModel:
    """Chat model behind any OpenAI-compatible endpoint (OpenAI, Gemini, ...).

    Returns the assistant message as a raw dict: Gemini puts a thought_signature in
    tool calls and rejects the next request (HTTP 400) if it is not sent back unchanged.
    """

    def __init__(self, settings: LLMSettings, client: openai.OpenAI | None = None):
        self._model = settings.model
        self._client = client or openai.OpenAI(  # a client can be injected, so tests need no network
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=TIMEOUT_SECONDS,
            max_retries=MAX_RETRIES,
        )

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        try:
            response = self._client.chat.completions.create(
                model=self._model, messages=messages, tools=tools, temperature=0
            )
        except openai.OpenAIError as error:  # base class: HTTP, timeout and connection errors
            raise ModelError(f"{type(error).__name__}: {error}") from error
        if not response.choices:
            raise ModelError("empty response")
        choice = response.choices[0]
        if choice.finish_reason in UNUSABLE_FINISH_REASONS:  # never hand back a cut-off answer
            raise ModelError(f"response stopped early: {choice.finish_reason}")
        return choice.message.model_dump(exclude_none=True)
