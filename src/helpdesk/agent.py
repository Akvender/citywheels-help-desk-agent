"""The agent loop: ask the model, run the tools it requests, repeat until it answers."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from helpdesk.config import NOW
from helpdesk.llm import ChatModel
from helpdesk.prompts import STAFF_CONTACT, build_system_prompt
from helpdesk.tools.registry import TOOL_SCHEMAS, dispatch

MAX_STEPS_ANSWER = f"I could not finish this request. Please contact the staff. {STAFF_CONTACT}"
EMPTY_ANSWER = f"I could not produce an answer. Please contact the staff. {STAFF_CONTACT}"


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: str
    result: str


@dataclass
class AgentResult:
    answer: str
    trace: list[ToolCall]
    messages: list[dict]
    stopped: Literal["answer", "max_steps", "empty"]


def run_agent(
    question: str,
    model: ChatModel,
    tools: dict[str, Callable[..., dict]],
    *,
    history: list[dict] | None = None,
    max_steps: int = 6,
    now=NOW,
) -> AgentResult:
    messages = [{"role": "system", "content": build_system_prompt(now)}]
    messages += history or []  # copies the items into a new list; the caller's list stays untouched
    messages.append({"role": "user", "content": question})
    trace: list[ToolCall] = []

    for _ in range(max_steps):
        reply = model.complete(messages, TOOL_SCHEMAS)
        messages.append(reply)  # unchanged: providers may need their own fields back
        calls = reply.get("tool_calls") or []
        if not calls:
            answer = (reply.get("content") or "").strip()
            if not answer:
                return AgentResult(EMPTY_ANSWER, trace, messages, "empty")
            return AgentResult(answer, trace, messages, "answer")
        for call in calls:
            # The model's output is untrusted: any field may be missing or have the wrong type.
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                function = {}
            name, arguments = function.get("name"), function.get("arguments")
            result = dispatch(tools, name, arguments)
            trace.append(ToolCall(str(name), arguments if isinstance(arguments, str) else "", result))
            if call.get("id"):  # a result can only be sent back for a call that has an id
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return AgentResult(MAX_STEPS_ANSWER, trace, messages, "max_steps")
