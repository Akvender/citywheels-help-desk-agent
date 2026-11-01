"""Automatic checks for one agent answer. Pure functions: no API calls, easy to test."""

import json
import re
from decimal import Decimal

_NUMBER = r"\d+(?:,\d{3})*(?:[.,]\d+)?"  # 340, 340.00, 340,00 (decimal comma), 1,250.50
_MARKER = r"(?:€|EUR|PLN|zł)"
# A money amount is a number right next to a currency marker: "EUR 340", "€340", "340 EUR", "340,00 zł".
_MONEY = re.compile(
    rf"{_MARKER}\s*(?P<before>{_NUMBER})|(?P<after>{_NUMBER})\s*(?:{_MARKER}|euros?)(?!\w)",
    re.IGNORECASE,
)


def _to_decimal(raw: str) -> Decimal:
    """'1,250.50' -> 1250.50, '340,00' -> 340.00, '1,250' -> 1250."""
    if "." not in raw and "," in raw:
        head, tail = raw.rsplit(",", 1)
        if len(tail) != 3:  # not a thousands group, so the comma is a decimal comma
            return Decimal(head.replace(",", "") + "." + tail)
    return Decimal(raw.replace(",", ""))


_MARKDOWN_EMPHASIS = re.compile(r"[*_`]+")


def money_amounts(text: str) -> list[Decimal]:
    """Amounts written next to a currency marker, in the order they appear."""
    amounts = []
    # Without this, "**340.00** EUR" hides the amount from the parser and from the grounding check.
    plain = _MARKDOWN_EMPHASIS.sub("", text)
    for match in _MONEY.finditer(plain):
        amounts.append(_to_decimal(match.group("before") or match.group("after")))
    return amounts


def _eur_fields(value) -> list[Decimal]:
    """Values of every key ending in '_eur', at any depth of a parsed JSON value."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_eur") and isinstance(item, (int, float, str)) and not isinstance(item, bool):
                found.append(Decimal(str(item)))
            found += _eur_fields(item)
    elif isinstance(value, list):
        for item in value:
            found += _eur_fields(item)
    return found


def known_amounts(trace) -> set[Decimal]:
    """Money a tool really returned: '*_eur' fields plus amounts written in policy text.

    Other numbers (booking ids, hours, bike counts) are NOT money, so they cannot back an amount.
    """
    known = set()
    for call in trace:
        known |= set(money_amounts(call.result))
        try:
            known |= set(_eur_fields(json.loads(call.result)))
        except (ValueError, ArithmeticError):
            pass  # not JSON (e.g. plain text): the money_amounts() part above is enough
    return known


def check_case(case: dict, answer: str, trace) -> list[str]:
    """Return the reasons why the answer fails; an empty list means it passed."""
    amounts = money_amounts(answer)
    nonzero = [amount for amount in amounts if amount != 0]  # "0.00 EUR" is not a refund amount
    reasons = []
    reasons += _check_tools(case, trace)
    reasons += _check_amounts(case, amounts, nonzero)
    reasons += _check_phrases(case, answer)
    reasons += _check_grounding(nonzero, trace)
    return reasons


def _check_tools(case: dict, trace) -> list[str]:
    called = {call.name for call in trace}
    reasons = [f"tool not called: {name}" for name in case.get("expected_tools", []) if name not in called]
    any_of = case.get("expected_tools_any", [])
    if any_of and not called.intersection(any_of):
        reasons.append(f"none of these tools was called: {', '.join(any_of)}")
    return reasons


def _check_amounts(case: dict, amounts: list[Decimal], nonzero: list[Decimal]) -> list[str]:
    reasons = []
    expected = case.get("expected_total_eur")
    if expected is not None and Decimal(expected) not in amounts:
        reasons.append(f"expected total {expected} EUR is missing from the answer (found: {_show(amounts)})")
    limit = case.get("max_nonzero_amounts")
    if limit is not None and len(nonzero) > limit:
        reasons.append(f"answer has {len(nonzero)} non-zero amounts, at most {limit} allowed ({_show(nonzero)})")
    for forbidden in case.get("forbidden_amounts_eur", []):
        if Decimal(forbidden) in amounts:
            reasons.append(f"forbidden amount {forbidden} EUR is in the answer")
    return reasons


def contains_phrase(text: str, phrase: str) -> bool:
    """Case-insensitive match. A phrase that starts or ends with a letter/digit must not be glued to
    another letter/digit there: '16' does not match '2016', '2 EUR' does not match '12 EUR'."""
    pattern = re.escape(phrase.lower())
    if re.match(r"\w", phrase):
        pattern = rf"(?<!\w){pattern}"
    if re.search(r"\w$", phrase):
        pattern = rf"{pattern}(?!\w)"
    return re.search(pattern, text.lower()) is not None


def _check_phrases(case: dict, answer: str) -> list[str]:
    reasons = []
    for group in case.get("must_contain_any", []):
        if not any(contains_phrase(answer, phrase) for phrase in group):
            reasons.append(f"none of these phrases found: {' / '.join(group)}")
    for phrase in case.get("must_not_contain", []):
        if contains_phrase(answer, phrase):
            reasons.append(f"forbidden phrase found: {phrase}")
    return reasons


def _check_grounding(nonzero: list[Decimal], trace) -> list[str]:
    """Anti-hallucination: every money amount in the answer must be money a tool returned."""
    if not nonzero:
        return []
    if not trace:
        return ["amount not backed by a tool result: no tool was called"]
    known = known_amounts(trace)
    return [f"amount not backed by a tool result: {amount}" for amount in nonzero if amount not in known]


def _show(amounts: list[Decimal]) -> str:
    return ", ".join(str(amount) for amount in amounts) or "none"
