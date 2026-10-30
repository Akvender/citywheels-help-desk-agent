"""The agent loop: ask the model, run the tools it requests, repeat until it answers."""

from collections.abc import Callable
from dataclasses import dataclass

from helpdesk.config import NOW
from helpdesk.llm import ChatModel
from helpdesk.prompts import STAFF_CONTACT, build_system_prompt
from helpdesk.tools.registry import TOOL_SCHEMAS, dispatch

MAX_STEPS_ANSWER = f"I could not finish this request. Please contact the staff. {STAFF_CONTACT}"


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
    stopped: str  # "answer" or "max_steps"


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
            return AgentResult(reply.get("content") or "", trace, messages, "answer")
        for call in calls:
            trace.append(_run_call(call, tools, messages))
    return AgentResult(MAX_STEPS_ANSWER, trace, messages, "max_steps")


def _run_call(call: dict, tools: dict[str, Callable[..., dict]], messages: list[dict]) -> ToolCall:
    name = call["function"]["name"]
    arguments = call["function"]["arguments"]
    result = dispatch(tools, name, arguments)
    messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
    return ToolCall(name, arguments, result)
