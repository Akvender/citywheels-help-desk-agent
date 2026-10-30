"""Booking lookup tool."""

from decimal import Decimal

from helpdesk.tools.booking_id import normalize_booking_id

NOT_FOUND_MESSAGE = "No booking with this number was found."


def get_booking(bookings: dict[str, dict], booking_id: str) -> dict:
    """Return the booking as JSON-friendly data, or {"found": False, ...}. Never raises."""
    normalized = normalize_booking_id(booking_id)
    booking = bookings.get(normalized) if normalized else None
    if booking is None:
        return {"found": False, "booking_id": booking_id, "message": NOT_FOUND_MESSAGE}
    return {"found": True, "booking": {key: _serialize(value) for key, value in booking.items()}}


def _serialize(value):
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, list):
        return list(value)  # new list, so callers cannot change the stored booking
    return value
