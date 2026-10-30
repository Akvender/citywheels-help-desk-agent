"""The calculate_refund tool: what comes back when a booking is cancelled."""

from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from helpdesk.config import NOW
from helpdesk.tools.booking_id import normalize_booking_id

CENT = Decimal("0.01")
FULL_REFUND_FROM = timedelta(hours=48)
HALF_REFUND_FROM = timedelta(hours=24)

REFUND_METHODS = {
    "card": "to the same card within 5 working days",
    "voucher": "as a new voucher of the same value, never as money; the deposit too",
}

NOT_CANCELLABLE_REASONS = {
    "cancelled": "The booking is already cancelled, so it cannot be cancelled again and nothing is refunded.",
    "in_progress": (
        "The booking cannot be cancelled because the rental has already started. "
        "This does not mean the deposit is lost: staff settle it when the bike is returned."
    ),
    "completed": (
        "The booking cannot be cancelled because the rental is already completed. "
        "This does not mean the deposit is lost: staff settle it when the bike is returned."
    ),
}


def money(amount: Decimal) -> str:
    return str(amount.quantize(CENT, rounding=ROUND_HALF_UP))


def refund_percent_for(time_before_start: timedelta) -> int:
    if time_before_start >= FULL_REFUND_FROM:
        return 100
    if time_before_start >= HALF_REFUND_FROM:
        return 50
    return 0


def breakdown(percent: int, rental: Decimal, deposit: Decimal) -> dict:
    return {
        "refund_percent": percent,
        "rental_refund_eur": money(rental),
        "booking_fee_refund_eur": money(Decimal(0)),  # the booking fee is never refunded
        "deposit_refund_eur": money(deposit),
        "total_refund_eur": money(rental + deposit),
    }


def compute_refund(booking: dict, cancel_at: datetime) -> dict:
    """Apply the cancellation rules; rental_price_eur is already the whole booking price."""
    time_before_start = datetime.fromisoformat(booking["start"]) - cancel_at
    hours = Decimal(int(time_before_start.total_seconds())) / 3600
    base = {"cancel_at": cancel_at.isoformat(), "hours_before_start": money(hours)}

    if booking["status"] != "confirmed":
        reason = NOT_CANCELLABLE_REASONS.get(
            booking["status"], "The booking cannot be cancelled in its current status."
        )
        return {**base, "can_cancel": False, "reason": reason,
                **breakdown(0, Decimal(0), Decimal(0)), "refund_method": "nothing is refunded"}

    percent = refund_percent_for(time_before_start)
    rental = booking["rental_price_eur"] * percent / 100
    reason = f"Cancelled {hours:.2f} hours before the start: {percent}% of the rental price is refunded."
    if time_before_start < timedelta(0):
        reason = (
            "Interpretation: the rental start has already passed, so 0% of the rental "
            "price is refunded; the deposit is still refunded in full."
        )
    return {**base, "can_cancel": True, "reason": reason,
            **breakdown(percent, rental, booking["deposit_eur"]),
            "refund_method": REFUND_METHODS[booking["paid_with"]]}


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
            return {"error": "cancel_at must be an ISO 8601 date and time, e.g. 2026-06-11T10:00:00+02:00."}
        if when.tzinfo is None:
            return {"error": "cancel_at must include a time zone, e.g. +02:00."}

    return {"booking_id": normalized, "found": True, **compute_refund(booking, when)}
