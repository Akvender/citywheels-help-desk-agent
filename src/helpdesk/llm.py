"""The only module that talks to the LLM provider."""

from typing import Protocol

import openai

from helpdesk.config import LLMSettings

TIMEOUT_SECONDS = 60
MAX_RETRIES = 2


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

    def __init__(self, settings: LLMSettings):
        self._model = settings.model
        self._client = openai.OpenAI(
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
        except openai.APIError as error:  # includes timeouts and connection errors
            raise ModelError(f"{type(error).__name__}: {error.message}") from error
        return response.choices[0].message.model_dump(exclude_none=True)
