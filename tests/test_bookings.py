from decimal import Decimal

import pytest

from helpdesk.tools.bookings import NOT_FOUND_MESSAGE, get_booking


@pytest.fixture
def bookings() -> dict[str, dict]:
    return {
        "CW-1002": {
            "id": "CW-1002",
            "status": "confirmed",
            "add_ons": ["child_seat"],
            "rental_price_eur": Decimal("80.0"),
            "booking_fee_eur": Decimal("2"),
            "deposit_eur": Decimal("300.50"),
        }
    }


def test_returns_booking_with_money_as_two_decimal_strings(bookings):
    result = get_booking(bookings, "CW-1002")

    assert result["found"] is True
    assert result["booking"]["rental_price_eur"] == "80.00"
    assert result["booking"]["booking_fee_eur"] == "2.00"
    assert result["booking"]["deposit_eur"] == "300.50"
    assert result["booking"]["status"] == "confirmed"


def test_normalizes_booking_number(bookings):  # smoke test; the rules are in test_booking_id.py
    assert get_booking(bookings, " cw1002 ")["found"] is True


def test_unknown_booking_number(bookings):
    assert get_booking(bookings, "CW-9999") == {
        "found": False,
        "booking_id": "CW-9999",
        "message": NOT_FOUND_MESSAGE,
    }


@pytest.mark.parametrize("raw", [None, 1002, "", "hello", ["CW-1002"]])
def test_garbage_input_does_not_raise(bookings, raw):
    result = get_booking(bookings, raw)

    expected_echo = raw if isinstance(raw, str) else None
    assert result == {"found": False, "booking_id": expected_echo, "message": NOT_FOUND_MESSAGE}


def test_long_input_echo_is_cut_to_50_chars(bookings):
    result = get_booking(bookings, "x" * 500)

    assert result["booking_id"] == "x" * 50


def test_half_up_rounding(bookings):
    bookings["CW-1002"]["rental_price_eur"] = Decimal("0.125")

    assert get_booking(bookings, "CW-1002")["booking"]["rental_price_eur"] == "0.13"


def test_nested_values_are_deep_copied(bookings):
    bookings["CW-1002"]["extra"] = {"notes": ["a"]}

    get_booking(bookings, "CW-1002")["booking"]["extra"]["notes"].append("b")

    assert bookings["CW-1002"]["extra"] == {"notes": ["a"]}


def test_does_not_mutate_input(bookings):
    get_booking(bookings, "CW-1002")["booking"]["add_ons"].append("lock")

    assert bookings["CW-1002"]["add_ons"] == ["child_seat"]
    assert bookings["CW-1002"]["rental_price_eur"] == Decimal("80.0")
