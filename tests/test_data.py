from decimal import Decimal

from helpdesk.data import load_bookings, load_policy_sections


def test_bookings_are_keyed_by_id():
    bookings = load_bookings()

    assert len(bookings) == 10
    assert bookings["CW-1002"]["bikes"] == 2


def test_money_is_loaded_as_decimal_not_float():
    booking = load_bookings()["CW-1009"]

    assert isinstance(booking["rental_price_eur"], Decimal)
    assert booking["rental_price_eur"] == Decimal("119.0")


def test_policies_are_split_into_sections():
    sections = load_policy_sections()

    headings = {(s.source, s.heading) for s in sections}
    assert ("faq.md", "When are you open?") in headings
    assert ("cancellations.md", "Cancelling a booking") in headings


def test_document_preamble_is_kept_under_the_title():
    sections = load_policy_sections()

    preamble = next(s for s in sections if s.source == "prices.md" and s.heading == "Prices")
    assert "All prices are in euros" in preamble.text
