"""Booking number normalisation shared by the booking and refund tools."""

import re

_BOOKING_ID = re.compile(r"^CW-?(\d{4})$")


def normalize_booking_id(raw: object) -> str | None:
    """Turn user input like ' cw1002 ' or 'CW-1002' into 'CW-1002'; None if it is not a booking number."""
    if not isinstance(raw, str):
        return None
    match = _BOOKING_ID.match(raw.strip().upper().replace(" ", ""))
    return f"CW-{match.group(1)}" if match else None
