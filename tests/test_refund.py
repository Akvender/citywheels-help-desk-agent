import copy
from datetime import timedelta
from decimal import Decimal

import pytest

from helpdesk.config import NOW
from helpdesk.data import load_bookings
from helpdesk.tools.refund import calculate_refund

BOOKINGS = load_bookings()


@pytest.mark.parametrize(
    "booking_id, percent, rental, deposit, total",
    [
        ("CW-1001", 100, "40.00", "50.00", "90.00"),
        ("CW-1002", 50, "40.00", "300.00", "340.00"),
        ("CW-1003", 0, "0.00", "50.00", "50.00"),
        ("CW-1004", 100, "23.00", "50.00", "73.00"),
        ("CW-1007", 100, "36.00", "150.00", "186.00"),  # exactly 48 h
        ("CW-1009", 100, "119.00", "50.00", "169.00"),
        ("CW-1010", 50, "20.00", "150.00", "170.00"),  # exactly 24 h
    ],
)
def test_confirmed_bookings_follow_the_cancellation_table(
    booking_id, percent, rental, deposit, total
):
    result = calculate_refund(BOOKINGS, booking_id)

    assert result["found"] is True
    assert result["can_cancel"] is True
    assert result["refund_percent"] == percent
    assert result["rental_refund_eur"] == rental
    assert result["deposit_refund_eur"] == deposit
    assert result["total_refund_eur"] == total


def test_hours_before_start_is_reported_with_two_decimals():
    result = calculate_refund(BOOKINGS, "CW-1001")

    assert result["hours_before_start"] == "73.00"
    assert result["cancel_at"] == NOW.isoformat()


def test_card_refund_mentions_five_working_days():
    result = calculate_refund(BOOKINGS, "CW-1001")

    assert result["refund_method"] == "to the same card within 5 working days"


def test_voucher_refund_is_a_new_voucher_including_deposit():
    result = calculate_refund(BOOKINGS, "CW-1004")

    assert result["refund_method"] == (
        "as a new voucher of the same value, never as money; the deposit too"
    )


@pytest.mark.parametrize("booking_id", ["CW-1001", "CW-1002", "CW-1006", "CW-1010"])
def test_booking_fee_is_never_refunded(booking_id):
    assert calculate_refund(BOOKINGS, booking_id)["booking_fee_refund_eur"] == "0.00"


@pytest.mark.parametrize("booking_id", ["CW-1005", "CW-1006", "CW-1008"])
def test_other_statuses_cannot_be_cancelled_and_refund_nothing(booking_id):
    result = calculate_refund(BOOKINGS, booking_id)

    assert result["found"] is True
    assert result["can_cancel"] is False
    assert result["refund_percent"] == 0
    assert result["total_refund_eur"] == "0.00"
    assert result["deposit_refund_eur"] == "0.00"
    assert "cannot be cancelled" in result["reason"]


def test_just_below_48_hours_gives_half():
    start = BOOKINGS["CW-1007"]["start"]
    cancel_at = "2026-06-10T09:01:00+02:00"  # 47:59 before 2026-06-12T09:00

    result = calculate_refund(BOOKINGS, "CW-1007", cancel_at=cancel_at)

    assert start == "2026-06-12T09:00:00+02:00"
    assert result["refund_percent"] == 50
    assert result["total_refund_eur"] == "168.00"


def test_just_below_24_hours_gives_nothing_for_rental():
    cancel_at = "2026-06-10T09:01:00+02:00"  # 23:59 before 2026-06-11T09:00

    result = calculate_refund(BOOKINGS, "CW-1010", cancel_at=cancel_at)

    assert result["refund_percent"] == 0
    assert result["total_refund_eur"] == "150.00"
    assert result["hours_before_start"] == "23.98"


def test_cancel_at_in_another_timezone_is_compared_in_absolute_time():
    result = calculate_refund(BOOKINGS, "CW-1001", cancel_at="2026-06-10T07:00:00+00:00")

    assert result["hours_before_start"] == "73.00"


def test_hours_are_rounded_down_so_they_never_contradict_the_percent():
    cancel_at = "2026-06-10T09:00:01+02:00"  # 47:59:59 before CW-1007 starts

    result = calculate_refund(BOOKINGS, "CW-1007", cancel_at=cancel_at)

    assert result["refund_percent"] == 50
    assert result["hours_before_start"] == "47.98"


def test_confirmed_after_start_refunds_deposit_only():
    result = calculate_refund(BOOKINGS, "CW-1003", cancel_at="2026-06-10T16:00:00+02:00")

    assert result["can_cancel"] is True
    assert result["refund_percent"] == 0
    assert result["total_refund_eur"] == "50.00"
    assert "already passed" in result["reason"]


def test_half_cent_is_rounded_half_up():
    booking = {**BOOKINGS["CW-1002"], "rental_price_eur": Decimal("0.05")}

    result = calculate_refund({"CW-1002": booking}, "CW-1002")

    assert result["rental_refund_eur"] == "0.03"  # 50% of 0.05 = 0.025


def test_booking_id_is_normalized():
    assert calculate_refund(BOOKINGS, " cw1001 ")["booking_id"] == "CW-1001"


@pytest.mark.parametrize("raw", ["CW-9999", "hello", "", None])
def test_unknown_or_invalid_id_is_not_found(raw):
    result = calculate_refund(BOOKINGS, raw)

    assert result["found"] is False
    assert result["booking_id"] == raw
    assert "message" in result


@pytest.mark.parametrize("bad", ["2026-06-11T10:00:00", "tomorrow", "2026-13-45T00:00:00+02:00", 42])
def test_naive_or_malformed_cancel_at_returns_error(bad):
    result = calculate_refund(BOOKINGS, "CW-1001", cancel_at=bad)

    assert "error" in result
    assert result["booking_id"] == "CW-1001"


def test_explicit_now_is_used_as_default_cancel_at():
    later = NOW + timedelta(hours=30)

    result = calculate_refund(BOOKINGS, "CW-1001", now=later)

    assert result["hours_before_start"] == "43.00"
    assert result["refund_percent"] == 50


def test_input_is_not_mutated():
    before = copy.deepcopy(BOOKINGS)

    calculate_refund(BOOKINGS, "CW-1002")
    calculate_refund(BOOKINGS, "CW-1005")

    assert BOOKINGS == before
