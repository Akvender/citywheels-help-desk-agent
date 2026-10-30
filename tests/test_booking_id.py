import pytest

from helpdesk.tools.booking_id import echo_booking_id, normalize_booking_id


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("CW-1002", "CW-1002"),
        (" cw-1002 ", "CW-1002"),
        ("cw1002", "CW-1002"),
        ("CW 1002", "CW-1002"),
        ("CW-99", None),
        ("CW-10023", None),
        ("C W 1 0 0 2", None),
        ("CW-10 02", None),
        ("1002", None),
        ("", None),
        (None, None),
        (1002, None),
    ],
)
def test_normalize_booking_id(raw, expected):
    assert normalize_booking_id(raw) == expected


def test_echo_is_cut_to_50_chars_and_only_for_strings():
    assert echo_booking_id("x" * 500) == "x" * 50
    assert echo_booking_id(12345) is None
