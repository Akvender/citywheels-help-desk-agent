"""Connects the tool functions to the model: JSON schemas it sees and a safe dispatcher."""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from functools import partial

from helpdesk.data import PolicySection
from helpdesk.tools.bookings import get_booking
from helpdesk.tools.policies import search_policies
from helpdesk.tools.refund import calculate_refund

logger = logging.getLogger(__name__)

# The descriptions below are part of the prompt: the model decides which tool to call from them.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_policies",
            "description": (
                "Search the CityWheels shop rules (prices, opening hours, e-bikes, age limits, "
                "add-ons, cancellations, weather, ...). Use it for any question about how the shop works."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Keywords of the question."}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_booking",
            "description": "Look up one booking by its number (e.g. CW-1002): dates, bike, price, status.",
            "parameters": {
                "type": "object",
                "properties": {"booking_id": {"type": "string", "description": "Booking number, e.g. CW-1002."}},
                "required": ["booking_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_refund",
            "description": (
                "Calculate how much money the customer gets back if a booking is cancelled. "
                "Always use it for refund amounts; never compute them yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "string", "description": "Booking number, e.g. CW-1002."},
                    "cancel_at": {
                        "type": "string",
                        "description": (
                            "ISO 8601 with offset, e.g. 2026-06-12T09:00:00+02:00. Only if the customer "
                            "asks about a moment other than now; convert relative dates using the "
                            "current time from the system prompt."
                        ),
                    },
                },
                "required": ["booking_id"],
                "additionalProperties": False,
            },
        },
    },
]


def build_tools(
    bookings: dict[str, dict], sections: list[PolicySection], now: datetime
) -> dict[str, Callable[..., dict]]:
    """Bind the data to each tool, so the model only has to supply its own arguments."""
    return {
        "search_policies": partial(search_policies, sections),
        "get_booking": partial(get_booking, bookings),
        "calculate_refund": partial(calculate_refund, bookings, now=now),
    }


_PARAMETERS = {schema["function"]["name"]: schema["function"]["parameters"] for schema in TOOL_SCHEMAS}


def _check_arguments(name: str, arguments: dict) -> str | None:
    # The schema is the contract: the model may not pass anything else, e.g. its own "now" or data.
    parameters = _PARAMETERS.get(name)
    if parameters is None:  # a tool without a schema (only in tests) is not checked
        return None
    unknown = sorted(set(arguments) - set(parameters["properties"]))
    missing = sorted(set(parameters["required"]) - set(arguments))
    if unknown:
        return f"unknown argument(s) {', '.join(unknown)}"
    if missing:
        return f"missing argument(s) {', '.join(missing)}"
    return None


def dispatch(tools: dict[str, Callable[..., dict]], name: str, raw_arguments: str) -> str:
    """Run one tool call and return JSON text. Never raises: errors go back to the model."""
    return json.dumps(_run(tools, name, raw_arguments), default=str)


def _run(tools: dict[str, Callable[..., dict]], name: str, raw_arguments: str) -> dict:
    tool = tools.get(name) if isinstance(name, str) else None
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    if not isinstance(raw_arguments, str | None):
        return {"error": "Arguments must be a JSON string."}
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {"error": "Arguments are not valid JSON."}
    if not isinstance(arguments, dict):
        return {"error": "Arguments must be a JSON object."}
    problem = _check_arguments(name, arguments)
    if problem:
        return {"error": f"Wrong arguments: {problem}"}
    try:
        return tool(**arguments)
    except Exception as error:  # noqa: BLE001 - a tool bug must not crash the conversation
        logger.exception("Tool %s failed", name)
        return {"error": f"Tool failed, do not guess: {type(error).__name__}: {error}"}
