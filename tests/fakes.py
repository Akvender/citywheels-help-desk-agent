"""Scripted stand-in for the LLM so that tests run offline."""

import copy


class FakeModel:
    def __init__(self, replies: list[dict]):
        self._replies = list(replies)
        self.calls: list[list[dict]] = []  # snapshot of the messages for every call

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        self.calls.append(copy.deepcopy(messages))
        return self._replies.pop(0)


def tool_call(call_id: str, name: str, arguments: str) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


def assistant_calling(*calls: dict) -> dict:
    return {"role": "assistant", "tool_calls": list(calls)}


def assistant_saying(text: str) -> dict:
    return {"role": "assistant", "content": text}
