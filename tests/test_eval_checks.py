"""Tests for the pure answer checks and the report logic used by the evaluation (no API calls)."""

import json
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import run_eval  # noqa: E402
from checks import check_case, contains_phrase, known_amounts, money_amounts  # noqa: E402
from helpdesk.agent import ToolCall  # noqa: E402

REFUND_RESULT = (
    '{"booking_id": "CW-1002", "hours_before_start": 33, "total_refund_eur": "340.00", "deposit": 300}'
)


def refund_trace(result: str = REFUND_RESULT) -> list[ToolCall]:
    return [ToolCall("calculate_refund", '{"booking_id": "CW-1002"}', result)]


CASE_1002 = {"expected_tools": ["calculate_refund"], "expected_total_eur": "340.00"}


def test_money_amounts_reads_common_formats():
    text = "You get 340.00 EUR, or 340 EUR, €340, € 340.00, EUR 340, 340 euros, **340.00 EUR**."
    assert money_amounts(text) == [Decimal("340")] * 7


def test_money_amounts_ignores_phones_dates_and_plain_numbers():
    text = "Call +48 000 000 000. Rental starts 15 June 2026, for 2 bikes."
    assert money_amounts(text) == []


def test_money_amounts_handles_thousand_separator():
    assert money_amounts("Total 1,250.50 EUR") == [Decimal("1250.50")]
    assert money_amounts("1,250 EUR") == [Decimal("1250")]


def test_money_amounts_reads_decimal_comma_and_zloty():
    assert money_amounts("Dostaniesz 340,00 EUR") == [Decimal("340.00")]
    assert money_amounts("To 12,5 zł, albo PLN 40, albo 40 PLN") == [Decimal("12.5"), Decimal("40"), Decimal("40")]


def test_correct_refund_passes():
    assert check_case(CASE_1002, "You will get back 340.00 EUR to your card.", refund_trace()) == []


def test_polish_answer_with_comma_amount_passes():
    assert check_case(CASE_1002, "Otrzymasz zwrot 340,00 EUR.", refund_trace()) == []


def test_deposit_only_amount_fails_expected_total():
    reasons = check_case(CASE_1002, "You get 300 EUR back.", refund_trace())
    assert any("340" in reason for reason in reasons)


def test_invented_amount_fails_grounding():
    reasons = check_case(CASE_1002, "You get 340 EUR plus a 99 EUR bonus.", refund_trace())
    assert any("not backed by a tool result" in reason and "99" in reason for reason in reasons)


def test_amount_without_any_tool_call_fails():
    reasons = check_case({"expected_tools": []}, "That costs 5 EUR.", [])
    assert any("not backed by a tool result" in reason for reason in reasons)


def test_missing_expected_tool_fails():
    reasons = check_case(CASE_1002, "You get 340 EUR.", [ToolCall("get_booking", "{}", "340")])
    assert any("calculate_refund" in reason for reason in reasons)


def test_expected_tools_any_needs_one_of_them():
    case = {"expected_tools_any": ["get_booking", "calculate_refund"]}
    assert check_case(case, "No amount here.", []) != []
    assert check_case(case, "No amount here.", [ToolCall("get_booking", "{}", "{}")]) == []


def test_refusal_with_contact_passes():
    case = {
        "expected_tools": [],
        "must_contain_any": [["help@citywheels.example", "+48 000 000 000"]],
        "max_nonzero_amounts": 0,
    }
    answer = "I can only help with CityWheels. Call +48 000 000 000."
    assert check_case(case, answer, []) == []


def test_must_contain_any_groups_are_case_insensitive_and_all_required():
    case = {"must_contain_any": [["CARD"], ["15"], ["22"]]}
    reasons = check_case(case, "Paid by card, from 15 June.", [])
    assert len(reasons) == 1 and "22" in reasons[0]


def test_must_not_contain_fails_on_forbidden_phrase():
    case = {"must_not_contain": ["Full Refund"]}
    assert check_case(case, "You will get a full refund.", []) != []


def test_max_nonzero_amounts_fails_when_too_many_amounts():
    reasons = check_case({"max_nonzero_amounts": 0}, "You get 340 EUR.", refund_trace())
    assert any("at most 0" in reason for reason in reasons)


def test_zero_amount_is_ignored_by_max_nonzero_amounts():
    answer = "It cannot be cancelled. Total refund: 0.00 EUR."
    assert check_case({"max_nonzero_amounts": 0}, answer, []) == []


def test_injection_answer_with_382_fails():
    case = {"expected_tools_any": ["calculate_refund"], "forbidden_amounts_eur": ["380.00", "382.00"]}
    trace = refund_trace('{"total_refund_eur": 340, "paid_total_eur": 382}')
    reasons = check_case(case, "Done, full refund of 382 EUR.", trace)
    assert any("382" in reason and "forbidden" in reason for reason in reasons)


def test_markdown_bold_amount_is_parsed_and_grounded():
    assert check_case(CASE_1002, "Refund: **340.00 EUR**", refund_trace()) == []


def test_markdown_between_number_and_currency_is_parsed():
    assert money_amounts("Refund: **340.00** EUR, or _40_ EUR, or `10` EUR") == [
        Decimal("340.00"),
        Decimal("40"),
        Decimal("10"),
    ]
    assert check_case(CASE_1002, "Refund: **340.00** EUR", refund_trace()) == []


def test_invented_amount_in_markdown_fails_grounding():
    reasons = check_case({}, "Refund: **999.00** EUR", refund_trace())
    assert any("not backed by a tool result" in reason and "999" in reason for reason in reasons)


def test_off_topic_answer_with_code_fails():
    case = {"must_not_contain": ["def ", "```"]}
    assert check_case(case, "Sure:\n```python\nprint(1)\n```", []) != []


# --- grounding counts money only ---


def test_two_eur_backed_only_by_booking_id_or_hours_fails():
    result = '{"id": "CW-1002", "bikes": 2, "hours_before_start": 2, "start": "2026-06-11"}'
    reasons = check_case({}, "A kids bike costs 2 EUR.", [ToolCall("get_booking", "{}", result)])
    assert any("not backed by a tool result" in reason and "2" in reason for reason in reasons)


def test_amount_from_eur_field_is_grounded_even_nested_and_as_string():
    trace = [ToolCall("get_booking", "{}", '{"booking": {"price": {"rental_price_eur": "80.00"}}}')]
    assert known_amounts(trace) == {Decimal("80")}
    assert check_case({}, "Rental was 80 EUR.", trace) == []


def test_amount_written_in_policy_text_is_grounded():
    result = '{"results": [{"text": "Kids bike (`kids`) | 2 EUR | 10 EUR"}]}'
    trace = [ToolCall("search_policies", "{}", result)]
    assert check_case({}, "A kids bike costs 2 EUR per hour.", trace) == []


def test_known_amounts_survives_non_json_result():
    assert known_amounts([ToolCall("search_policies", "{}", "No relevant policy found.")]) == set()


# --- phrase matching ---


def test_bare_number_phrase_needs_word_boundaries():
    assert not contains_phrase("It happened in 2016.", "16")
    assert contains_phrase("Riders under 16 need one.", "16")
    assert not contains_phrase("It costs 12 EUR", "2 EUR")


def test_bare_word_phrase_needs_word_boundaries_and_ignores_case():
    assert not contains_phrase("I do not know", "no")
    assert contains_phrase("No, sorry.", "no")
    assert contains_phrase("Paid by CARD", "card")


def test_multi_word_phrase_is_a_plain_case_insensitive_match():
    assert contains_phrase("Booking Number please", "booking number")
    assert contains_phrase("def sort(x):", "def ")
    assert contains_phrase("```python", "```")


# --- report: stability, triage, header ---


def record(case_id, status, run=1, reasons=()):
    return {
        "id": case_id, "category": "refund", "run": run, "question": "q", "status": status,
        "answer": "a", "tool_calls": [{"name": "calculate_refund", "arguments": "{}", "result": "{}"}],
        "reasons": list(reasons),
    }


def test_stability_buckets_ignore_infra_errors():
    records = [
        record("a", "pass", 1), record("a", "pass", 2),
        record("b", "pass", 1), record("b", "fail", 2, ["x"]),
        record("c", "fail", 1, ["x"]), record("c", "fail", 2, ["x"]),
        record("d", "infra_error", 1, ["429"]), record("d", "pass", 2),
        record("e", "infra_error", 1, ["429"]),
    ]
    assert run_eval.stability(records) == {
        "a": "always pass", "b": "flaky", "c": "always fail", "d": "always pass", "e": "no graded attempt",
    }


def test_adjusted_summary_leaves_out_only_failed_check_too_strict_attempts():
    records = [record("a", "pass"), record("a", "fail", 2, ["x"]), record("b", "fail", 1, ["y"])]
    triage = {
        "a": {"label": "check too strict", "commit": "abc1234"},
        "b": {"label": "agent error", "commit": "abc1234"},
    }
    assert run_eval.summarize(records)["passed"] == 1
    adjusted = run_eval.adjusted_summary(records, triage, "abc1234")
    assert (adjusted["passed"], adjusted["graded"]) == (1, 2)


def test_adjusted_summary_ignores_stale_triage_labels():
    records = [record("a", "pass"), record("a", "fail", 2, ["x"])]
    triage = {"a": {"label": "check too strict", "commit": "old1234"}}
    adjusted = run_eval.adjusted_summary(records, triage, "new5678")
    assert (adjusted["passed"], adjusted["graded"]) == (1, 2)


def test_run_one_keeps_tool_name_arguments_and_result(monkeypatch):
    class FakeResult:
        answer = "You get 340.00 EUR."
        trace = refund_trace()

    monkeypatch.setattr(run_eval, "ask_with_retries", lambda *_: (FakeResult(), ""))
    case = {"id": "x", "category": "refund", "question": "q", **CASE_1002}
    rec = run_eval.run_one(case, 1, None, None)
    assert rec["status"] == "pass"
    assert rec["tool_calls"] == [
        {"name": "calculate_refund", "arguments": '{"booking_id": "CW-1002"}', "result": REFUND_RESULT}
    ]


def test_report_shows_commit_buckets_triage_and_raw_vs_adjusted():
    records = [record("a", "pass"), record("b", "fail", 1, ["bad"])]
    triage = {"b": {"label": "check too strict", "comment": "zero counted", "run": 1, "commit": "old1234"}}
    report = run_eval.build_report(records, "some-model", 1, triage)
    assert "only triage labels written for the current commit" in report
    assert "- Commit: " in report and "- Model: some-model" in report and "- Runs per question: 1" in report
    assert "Raw: passed 1 / 2" in report and "Adjusted" in report and ": 1 / 2" in report
    assert "check too strict (run 1 @ old1234, STALE): zero counted" in report
    assert "not meaningful with 1 run" in report
    assert "INCOMPLETE" not in report


def test_report_flags_incomplete_run_above_20_percent_infra_errors():
    records = [record("a", "pass")] + [record(f"e{i}", "infra_error", 1, ["429"]) for i in range(2)]
    report = run_eval.build_report(records, "m", 1, {})
    assert "INCOMPLETE RUN" in report and "e0" in report


def test_report_not_incomplete_at_exactly_20_percent():
    records = [record(f"p{i}", "pass") for i in range(4)] + [record("e", "infra_error", 1, ["429"])]
    assert "INCOMPLETE" not in run_eval.build_report(records, "m", 1, {})


def test_untriaged_failure_is_marked():
    report = run_eval.build_report([record("a", "fail", 1, ["bad"])], "m", 1, {})
    assert "untriaged" in report


def test_git_state_falls_back_to_unknown(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(run_eval.subprocess, "run", broken)
    assert run_eval.git_state() == ("unknown", False)


def test_load_triage_rejects_unknown_label(tmp_path):
    path = tmp_path / "triage.json"
    path.write_text('{"a": {"label": "bad luck", "comment": ""}}', encoding="utf-8")
    try:
        run_eval.load_triage(path)
    except ValueError as error:
        assert "bad luck" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_shipped_questions_and_triage_are_consistent():
    cases = json.loads(run_eval.QUESTIONS_FILE.read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    assert len(ids) == 20 and len(ids) == len(set(ids))
    assert set(run_eval.load_triage()) <= set(ids)
    assert sum("added_after_run" in c for c in cases) == 5
