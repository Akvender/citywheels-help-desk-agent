"""Automatic checks for one agent answer. Pure functions: no API calls, easy to test."""

import re
from decimal import Decimal

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# A money amount is a number right next to a currency marker: "EUR 340", "€340", "340 EUR", "340 euros".
_MONEY = re.compile(
    rf"(?:€|EUR)\s*(?P<before>{_NUMBER})|(?P<after>{_NUMBER})\s*(?:€|EUR|euros?)\b",
    re.IGNORECASE,
)
_ANY_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def money_amounts(text: str) -> list[Decimal]:
    """Amounts written next to a currency marker, in the order they appear."""
    amounts = []
    for match in _MONEY.finditer(text):
        raw = match.group("before") or match.group("after")
        amounts.append(Decimal(raw.replace(",", "").rstrip(".")))
    return amounts


def numbers_in(text: str) -> set[Decimal]:
    """Every number in a text (used on tool results, which are JSON)."""
    return {Decimal(raw) for raw in _ANY_NUMBER.findall(text)}


def check_case(case: dict, answer: str, trace) -> list[str]:
    """Return the reasons why the answer fails; an empty list means it passed."""
    amounts = money_amounts(answer)
    reasons = []
    reasons += _check_tools(case, trace)
    reasons += _check_amounts(case, amounts)
    reasons += _check_phrases(case, answer)
    reasons += _check_grounding(amounts, trace)
    return reasons


def _check_tools(case: dict, trace) -> list[str]:
    called = {call.name for call in trace}
    reasons = [f"tool not called: {name}" for name in case.get("expected_tools", []) if name not in called]
    any_of = case.get("expected_tools_any", [])
    if any_of and not called.intersection(any_of):
        reasons.append(f"none of these tools was called: {', '.join(any_of)}")
    return reasons


def _check_amounts(case: dict, amounts: list[Decimal]) -> list[str]:
    reasons = []
    expected = case.get("expected_total_eur")
    if expected is not None and Decimal(expected) not in amounts:
        reasons.append(f"expected total {expected} EUR is missing from the answer (found: {_show(amounts)})")
    max_amounts = case.get("max_amounts")
    if max_amounts is not None and len(amounts) > max_amounts:
        reasons.append(f"answer has {len(amounts)} amounts, at most {max_amounts} allowed ({_show(amounts)})")
    for forbidden in case.get("forbidden_amounts_eur", []):
        if Decimal(forbidden) in amounts:
            reasons.append(f"forbidden amount {forbidden} EUR is in the answer")
    return reasons


def _check_phrases(case: dict, answer: str) -> list[str]:
    text = answer.lower()
    reasons = []
    for group in case.get("must_contain_any", []):
        if not any(phrase.lower() in text for phrase in group):
            reasons.append(f"none of these phrases found: {' / '.join(group)}")
    for phrase in case.get("must_not_contain", []):
        if phrase.lower() in text:
            reasons.append(f"forbidden phrase found: {phrase}")
    return reasons


def _check_grounding(amounts: list[Decimal], trace) -> list[str]:
    """Anti-hallucination: every amount in the answer must also appear in some tool result."""
    if not amounts:
        return []
    if not trace:
        return ["amount not backed by a tool result: no tool was called"]
    known = set()
    for call in trace:
        known |= numbers_in(call.result)
    return [f"amount not backed by a tool result: {amount}" for amount in amounts if amount not in known]


def _show(amounts: list[Decimal]) -> str:
    return ", ".join(str(amount) for amount in amounts) or "none"
