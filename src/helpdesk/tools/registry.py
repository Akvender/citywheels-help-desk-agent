"""Connects the tool functions to the model: JSON schemas it sees and a safe dispatcher."""

import json
from collections.abc import Callable
from datetime import datetime
from functools import partial

from helpdesk.data import PolicySection
from helpdesk.tools.bookings import get_booking
from helpdesk.tools.policies import search_policies
from helpdesk.tools.refund import calculate_refund

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
                            "ISO 8601 with time zone; only when the customer asks about "
                            "a different moment than now."
                        ),
                    },
                },
                "required": ["booking_id"],
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


def dispatch(tools: dict[str, Callable[..., dict]], name: str, raw_arguments: str) -> str:
    """Run one tool call and return JSON text. Never raises: errors go back to the model."""
    return json.dumps(_run(tools, name, raw_arguments), default=str)


def _run(tools: dict[str, Callable[..., dict]], name: str, raw_arguments: str) -> dict:
    tool = tools.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return {"error": "Arguments are not valid JSON."}
    if not isinstance(arguments, dict):
        return {"error": "Arguments must be a JSON object."}
    try:
        return tool(**arguments)
    except TypeError as error:
        return {"error": f"Wrong arguments: {error}"}
    except Exception as error:  # noqa: BLE001 - a tool bug must not crash the conversation
        return {"error": f"Tool failed: {type(error).__name__}"}
