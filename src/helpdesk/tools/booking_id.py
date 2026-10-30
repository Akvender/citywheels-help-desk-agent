"""Booking number helpers shared by the booking and refund tools."""

import re

MAX_ECHO_LENGTH = 50

_BOOKING_ID = re.compile(r"CW[- ]?(\d{4})")


def normalize_booking_id(raw: object) -> str | None:
    """Turn user input like ' cw1002 ' or 'CW-1002' into 'CW-1002'; None if it is not a booking number."""
    if not isinstance(raw, str):
        return None
    match = _BOOKING_ID.fullmatch(raw.strip().upper())
    return f"CW-{match.group(1)}" if match else None


def echo_booking_id(raw: object) -> str | None:
    """What a "not found" answer repeats back: only a short string, never a huge or odd object."""
    return raw[:MAX_ECHO_LENGTH] if isinstance(raw, str) else None
