"""Booking lookup tool."""

import copy
from decimal import ROUND_HALF_UP, Decimal

from helpdesk.tools.booking_id import normalize_booking_id

NOT_FOUND_MESSAGE = "No booking with this number was found."
MAX_ECHO_LENGTH = 50


def get_booking(bookings: dict[str, dict], booking_id: str) -> dict:
    """Return a copy of the booking as JSON-friendly data, or {"found": False, ...}. Never raises."""
    normalized = normalize_booking_id(booking_id)
    booking = bookings.get(normalized) if normalized else None
    if booking is None:
        return {"found": False, "booking_id": _echo(booking_id), "message": NOT_FOUND_MESSAGE}
    return {"found": True, "booking": _serialize(copy.deepcopy(booking))}


def _echo(booking_id: object) -> str | None:
    # Only a short string is repeated back, so the LLM cannot be fed a huge or odd object.
    return booking_id[:MAX_ECHO_LENGTH] if isinstance(booking_id, str) else None


def _serialize(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
