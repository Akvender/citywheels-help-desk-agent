import json
from datetime import datetime

import pytest

from helpdesk.config import NOW
from helpdesk.data import PolicySection, load_bookings, load_policy_sections
from helpdesk.tools.registry import TOOL_SCHEMAS, build_tools, dispatch


def make_tools():
    return build_tools(load_bookings(), load_policy_sections(), NOW)


def schema_of(name):
    return next(s["function"] for s in TOOL_SCHEMAS if s["function"]["name"] == name)


def test_schemas_name_the_three_tools():
    names = [schema["function"]["name"] for schema in TOOL_SCHEMAS]
    assert names == ["search_policies", "get_booking", "calculate_refund"]


def test_cancel_at_is_optional_in_schema():
    refund = schema_of("calculate_refund")["parameters"]
    assert refund["required"] == ["booking_id"]
    assert "cancel_at" in refund["properties"]


def test_dispatch_runs_tool_and_returns_json_text():
    result = json.loads(dispatch(make_tools(), "get_booking", '{"booking_id": "CW-1002"}'))
    assert result["found"] is True


def test_dispatch_uses_bound_now_for_refund():
    result = json.loads(dispatch(make_tools(), "calculate_refund", '{"booking_id": "CW-1002"}'))
    assert result["cancel_at"] == NOW.isoformat()
    assert result["total_refund_eur"] == "340.00"


def test_dispatch_search_uses_bound_sections():
    sections = [PolicySection("x.md", "Parking", "Parking is free.")]
    tools = build_tools({}, sections, NOW)
    result = json.loads(dispatch(tools, "search_policies", '{"query": "parking free"}'))
    assert result["results"][0]["heading"] == "Parking"


def test_unknown_tool():
    result = json.loads(dispatch(make_tools(), "drop_tables", "{}"))
    assert result == {"error": "Unknown tool: drop_tables"}


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("get_booking", "{not json"),
        ("get_booking", "[1, 2]"),
        ("get_booking", ""),
        ("get_booking", '{"id": "CW-1002"}'),
        ("calculate_refund", "{}"),
        ("get_booking", {"booking_id": "CW-1002"}),
        (None, "{}"),
    ],
)
def test_bad_tool_calls_return_an_error(name, arguments):
    assert "error" in json.loads(dispatch(make_tools(), name, arguments))


def test_tool_failure_hides_details_from_the_model_but_logs_them(caplog):
    def broken(**_):
        raise ValueError("secret detail")

    result = json.loads(dispatch({"boom": broken}, "boom", "{}"))

    assert result == {"error": "Tool failed, do not guess."}
    assert "secret detail" in caplog.text


def test_type_error_inside_a_tool_is_not_reported_as_wrong_arguments():
    def buggy():
        return 1 + "a"

    error = json.loads(dispatch({"buggy": buggy}, "buggy", "{}"))["error"]
    assert error.startswith("Tool failed")


def test_schemas_reject_extra_properties():
    for schema in TOOL_SCHEMAS:
        assert schema["function"]["parameters"]["additionalProperties"] is False


def test_cancel_at_description_explains_format_and_relative_dates():
    description = schema_of("calculate_refund")["parameters"]["properties"]["cancel_at"]["description"]
    assert "2026-06-12T09:00:00+02:00" in description
    assert "current time" in description


def test_non_json_values_are_stringified():
    tools = {"when": lambda: {"at": datetime(2026, 1, 1)}}
    assert json.loads(dispatch(tools, "when", "{}"))["at"].startswith("2026-01-01")


@pytest.mark.parametrize(
    "smuggled",
    ['{"booking_id": "CW-1002", "now": "2026-06-01T09:00:00+02:00"}', '{"booking_id": "CW-1002", "bookings": {}}'],
)
def test_model_cannot_override_bound_data_or_time(smuggled):
    tools = build_tools(load_bookings(), load_policy_sections(), NOW)

    result = json.loads(dispatch(tools, "calculate_refund", smuggled))

    assert "unknown argument" in result["error"]
