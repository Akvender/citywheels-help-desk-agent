"""The calculate_refund tool: what comes back when a booking is cancelled."""

from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from helpdesk.config import NOW
from helpdesk.tools.booking_id import normalize_booking_id

CENT = Decimal("0.01")
ZERO = Decimal(0)
FULL_REFUND_FROM = timedelta(hours=48)
HALF_REFUND_FROM = timedelta(hours=24)

REFUND_METHODS = {
    "card": "to the same card within 5 working days",
    "voucher": "as a new voucher of the same value, never as money; the deposit too",
}

# Wording follows cancellations.md: these statuses cannot be cancelled and nothing is refunded.
NOT_CANCELLABLE_REASONS = {
    "cancelled": "The booking is already cancelled, so it cannot be cancelled again. Nothing is refunded.",
    "in_progress": "The rental has already started, so the booking cannot be cancelled. Nothing is refunded.",
    "completed": "The rental is already completed, so the booking cannot be cancelled. Nothing is refunded.",
}


def money(amount: Decimal) -> str:
    return str(amount.quantize(CENT, rounding=ROUND_HALF_UP))


def refund_percent_for(time_before_start: timedelta) -> int:
    if time_before_start >= FULL_REFUND_FROM:
        return 100
    if time_before_start >= HALF_REFUND_FROM:
        return 50
    return 0


def hours_label(time_before_start: timedelta) -> str:
    # Rounded down, so 47:59 shows "47.98" and never "48.00" next to a 50% refund.
    minutes = time_before_start // timedelta(minutes=1)
    return str((Decimal(minutes) / 60).quantize(CENT, rounding=ROUND_DOWN))


def compute_refund(booking: dict, cancel_at: datetime) -> dict:
    """Apply the cancellation rules. rental_price_eur is already the whole booking price."""
    time_before_start = datetime.fromisoformat(booking["start"]) - cancel_at
    hours = hours_label(time_before_start)
    result = {"cancel_at": cancel_at.isoformat(), "hours_before_start": hours}

    if booking["status"] != "confirmed":
        result["can_cancel"] = False
        result["reason"] = NOT_CANCELLABLE_REASONS.get(
            booking["status"], "The booking cannot be cancelled in its current status."
        )
        percent, rental, deposit = 0, ZERO, ZERO
        result["refund_method"] = "nothing is refunded"
    else:
        percent = refund_percent_for(time_before_start)
        rental = booking["rental_price_eur"] * percent / 100
        deposit = booking["deposit_eur"]  # always refunded in full on cancellation
        result["can_cancel"] = True
        result["reason"] = f"Cancelled {hours} hours before the start: {percent}% of the rental price is refunded."
        if time_before_start < timedelta(0):
            result["reason"] = "The rental start has already passed: 0% of the rental price is refunded."
        result["refund_method"] = REFUND_METHODS.get(
            booking["paid_with"], "refund method to be confirmed by the staff"
        )

    result["refund_percent"] = percent
    result["rental_refund_eur"] = money(rental)
    result["booking_fee_refund_eur"] = money(ZERO)  # the booking fee is never refunded
    result["deposit_refund_eur"] = money(deposit)
    result["total_refund_eur"] = money(rental + deposit)
    return result


def calculate_refund(
    bookings: dict[str, dict],
    booking_id: str,
    cancel_at: str | None = None,
    now: datetime = NOW,
) -> dict:
    """Tool entry point: validates input and never raises."""
    normalized = normalize_booking_id(booking_id)
    booking = bookings.get(normalized) if normalized else None
    if booking is None:
        return {"found": False, "booking_id": booking_id,
                "message": "No booking with this number was found."}

    when = now
    if cancel_at is not None:
        try:
            when = datetime.fromisoformat(cancel_at)
        except (TypeError, ValueError):
            return {"booking_id": normalized,
                    "error": "cancel_at must be an ISO 8601 date and time, e.g. 2026-06-11T10:00:00+02:00."}
        if when.tzinfo is None:
            return {"booking_id": normalized, "error": "cancel_at must include a time zone, e.g. +02:00."}

    return {"booking_id": normalized, "found": True, **compute_refund(booking, when)}
