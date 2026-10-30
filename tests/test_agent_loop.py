import copy
import json

import pytest

from fakes import FakeModel, assistant_calling, assistant_saying, tool_call
from helpdesk.agent import run_agent
from helpdesk.config import NOW
from helpdesk.data import load_bookings, load_policy_sections
from helpdesk.llm import ModelError
from helpdesk.prompts import STAFF_CONTACT, build_system_prompt
from helpdesk.tools.registry import build_tools


@pytest.fixture
def tools():
    return build_tools(load_bookings(), load_policy_sections(), NOW)


def tool_messages(messages):
    return [m for m in messages if m["role"] == "tool"]


def test_plain_answer_without_tools(tools):
    model = FakeModel([assistant_saying("Hello!")])
    result = run_agent("Hi", model, tools)
    assert (result.answer, result.trace, result.stopped) == ("Hello!", [], "answer")


def test_tool_result_goes_back_with_matching_id(tools):
    call = tool_call("call_1", "get_booking", '{"booking_id": "CW-1002"}')
    model = FakeModel([assistant_calling(call), assistant_saying("Found it.")])
    result = run_agent("Where is CW-1002?", model, tools)
    second_call = model.calls[1]
    assert second_call[-2] == assistant_calling(call)
    assert second_call[-1]["role"] == "tool"
    assert second_call[-1]["tool_call_id"] == "call_1"
    assert json.loads(second_call[-1]["content"])["found"] is True
    assert result.answer == "Found it."
    assert [t.name for t in result.trace] == ["get_booking"]


def test_two_tool_calls_in_one_reply_are_each_answered(tools):
    reply = assistant_calling(
        tool_call("a", "get_booking", '{"booking_id": "CW-1002"}'),
        tool_call("b", "get_booking", '{"booking_id": "CW-1003"}'),
    )
    model = FakeModel([reply, assistant_saying("Both.")])
    result = run_agent("Two bookings", model, tools)
    answered = tool_messages(model.calls[1])
    assert [m["tool_call_id"] for m in answered] == ["a", "b"]
    assert len(result.trace) == 2
    assert len(model.calls) == 2


def test_provider_metadata_is_passed_back_unchanged(tools):
    signed = tool_call("call_1", "get_booking", '{"booking_id": "CW-1002"}')
    signed["extra_content"] = {"google": {"thought_signature": "abc123=="}}
    reply = assistant_calling(signed)
    expected = json.loads(json.dumps(reply))
    model = FakeModel([reply, assistant_saying("Done.")])
    run_agent("q", model, tools)
    assert model.calls[1][-2] == expected


def test_max_steps_gives_safe_answer_with_contact(tools):
    looping = assistant_calling(tool_call("x", "get_booking", '{"booking_id": "CW-1002"}'))
    model = FakeModel([looping] * 3)
    result = run_agent("q", model, tools, max_steps=3)
    assert result.stopped == "max_steps"
    assert STAFF_CONTACT in result.answer
    assert len(model.calls) == 3


def test_history_is_prepended_and_not_mutated(tools):
    history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "reply"}]
    snapshot = copy.deepcopy(history)
    model = FakeModel([assistant_saying("ok")])
    result = run_agent("now", model, tools, history=history)
    roles_and_text = [(m["role"], m.get("content")) for m in model.calls[0][1:]]
    assert roles_and_text == [("user", "earlier"), ("assistant", "reply"), ("user", "now")]
    assert history == snapshot
    assert result.messages[-1]["content"] == "ok"


def test_system_prompt_has_date_contact_and_refund_rule():
    prompt = build_system_prompt(NOW)
    assert "2026-06-10" in prompt
    assert "help@citywheels.example" in prompt
    assert "card or voucher" in prompt


def test_model_error_propagates(tools):
    class Broken:
        def complete(self, messages, tools):
            raise ModelError("down")

    with pytest.raises(ModelError):
        run_agent("q", Broken(), tools)


class EchoToolResult:
    """Fake model: asks for the refund, then answers with exactly what the tool returned."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return assistant_calling(tool_call("r1", "calculate_refund", '{"booking_id": "CW-1002"}'))
        result = json.loads(messages[-1]["content"])
        return assistant_saying(f"You get {result['total_refund_eur']} EUR {result['refund_method']}.")


def test_refund_amount_from_the_tool_reaches_the_final_answer_unchanged(tools):
    result = run_agent("Cancel CW-1002", EchoToolResult(), tools)

    assert "340.00 EUR" in result.answer
    assert json.loads(result.trace[0].result)["total_refund_eur"] == "340.00"


@pytest.mark.parametrize(
    "reply",
    [{"role": "assistant"}, {"role": "assistant", "content": None}, {"role": "assistant", "content": "  \n"}],
)
def test_blank_answer_gives_safe_fallback_with_contact(tools, reply):
    result = run_agent("q", FakeModel([reply]), tools)
    assert result.stopped == "empty"
    assert STAFF_CONTACT in result.answer


@pytest.mark.parametrize(
    "bad_call",
    [
        {"id": "x"},
        {"id": "x", "function": None},
        {"id": "x", "function": {"name": "get_booking", "arguments": "{broken"}},
    ],
)
def test_malformed_tool_call_is_answered_with_an_error_not_a_crash(tools, bad_call):
    model = FakeModel([{"role": "assistant", "tool_calls": [bad_call]}, assistant_saying("Sorry.")])
    result = run_agent("q", model, tools)
    answered = tool_messages(model.calls[1])
    assert [m["tool_call_id"] for m in answered] == ["x"]
    assert "error" in json.loads(answered[0]["content"])
    assert result.answer == "Sorry."


def test_non_dict_tool_call_is_skipped_without_crash(tools):
    model = FakeModel([{"role": "assistant", "tool_calls": [None, "oops"]}, assistant_saying("Sorry.")])

    result = run_agent("q", model, tools)

    assert result.answer == "Sorry."
    assert result.trace == []


def test_tool_call_without_id_cannot_be_answered_but_does_not_crash(tools):
    reply = {"role": "assistant", "tool_calls": [{"function": {"name": "get_booking", "arguments": "{}"}}]}
    result = run_agent("q", FakeModel([reply, assistant_saying("Sorry.")]), tools)
    assert result.answer == "Sorry."
    assert len(result.trace) == 1
