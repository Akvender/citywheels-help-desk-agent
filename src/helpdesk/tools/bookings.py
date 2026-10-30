"""Booking lookup tool."""

import copy
from decimal import ROUND_HALF_UP, Decimal

from helpdesk.tools.booking_id import echo_booking_id, normalize_booking_id

NOT_FOUND_MESSAGE = "No booking with this number was found."


def get_booking(bookings: dict[str, dict], booking_id: str) -> dict:
    """Return a copy of the booking as JSON-friendly data, or {"found": False, ...}. Never raises."""
    normalized = normalize_booking_id(booking_id)
    booking = bookings.get(normalized) if normalized else None
    if booking is None:
        return {"found": False, "booking_id": echo_booking_id(booking_id), "message": NOT_FOUND_MESSAGE}
    return {"found": True, "booking": _serialize(copy.deepcopy(booking))}


def _serialize(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
