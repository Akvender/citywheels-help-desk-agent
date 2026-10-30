from decimal import Decimal

import pytest

from helpdesk.tools.bookings import get_booking

NOT_FOUND_MESSAGE = "No booking with this number was found."


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


@pytest.mark.parametrize("raw", ["cw1002", " CW-1002 ", "cw 1002"])
def test_normalizes_booking_number(bookings, raw):
    assert get_booking(bookings, raw)["found"] is True


def test_unknown_booking_number(bookings):
    assert get_booking(bookings, "CW-9999") == {
        "found": False,
        "booking_id": "CW-9999",
        "message": NOT_FOUND_MESSAGE,
    }


@pytest.mark.parametrize("raw", [None, 1002, "", "hello", ["CW-1002"]])
def test_garbage_input_does_not_raise(bookings, raw):
    result = get_booking(bookings, raw)

    assert result == {"found": False, "booking_id": raw, "message": NOT_FOUND_MESSAGE}


def test_does_not_mutate_input(bookings):
    get_booking(bookings, "CW-1002")["booking"]["add_ons"].append("lock")

    assert bookings["CW-1002"]["add_ons"] == ["child_seat"]
    assert bookings["CW-1002"]["rental_price_eur"] == Decimal("80.0")
