from types import SimpleNamespace

import openai
import pytest
from openai.types.chat import ChatCompletion

from helpdesk.config import LLMSettings
from helpdesk.llm import ModelError, OpenAICompatibleModel

SETTINGS = LLMSettings(base_url="http://unused.example", api_key="k", model="m")


def completion(message: dict, finish_reason: str = "stop", empty: bool = False) -> ChatCompletion:
    choice = {"index": 0, "finish_reason": finish_reason, "message": message}
    return ChatCompletion.model_validate(
        {"id": "1", "object": "chat.completion", "created": 0, "model": "m",
         "choices": [] if empty else [choice]}
    )


def stub_client(result=None, error=None):
    def create(**_):
        if error:
            raise error
        return result

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def ask(client) -> dict:
    return OpenAICompatibleModel(SETTINGS, client=client).complete([{"role": "user", "content": "hi"}], [])


def test_returns_plain_answer_as_dict():
    reply = ask(stub_client(completion({"role": "assistant", "content": "Hello"})))
    assert reply == {"role": "assistant", "content": "Hello"}


def test_thought_signature_survives_in_returned_dict():
    call = {"id": "c1", "type": "function", "function": {"name": "get_booking", "arguments": "{}"},
            "extra_content": {"google": {"thought_signature": "abc=="}}}
    reply = ask(stub_client(completion({"role": "assistant", "tool_calls": [call]}, "tool_calls")))
    assert reply["tool_calls"][0]["extra_content"] == {"google": {"thought_signature": "abc=="}}


@pytest.mark.parametrize(
    "error",
    [
        openai.APIConnectionError(request=SimpleNamespace()),
        openai.APITimeoutError(request=SimpleNamespace()),
    ],
)
def test_connection_problems_become_model_error(error):
    with pytest.raises(ModelError) as raised:
        ask(stub_client(error=error))
    assert type(error).__name__ in str(raised.value)


def test_empty_choices_is_model_error():
    with pytest.raises(ModelError, match="empty response"):
        ask(stub_client(completion({}, empty=True)))


@pytest.mark.parametrize("reason", ["length", "content_filter"])
def test_truncated_or_filtered_answer_is_never_returned(reason):
    with pytest.raises(ModelError, match=reason):
        ask(stub_client(completion({"role": "assistant", "content": "Half an ans"}, reason)))
