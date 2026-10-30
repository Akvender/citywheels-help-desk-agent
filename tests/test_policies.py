import pytest

from helpdesk.data import PolicySection, load_policy_sections
from helpdesk.tools.policies import search_policies


@pytest.fixture(scope="module")
def sections() -> list[PolicySection]:
    return load_policy_sections()


def pairs(result: dict, limit: int) -> list[tuple[str, str]]:
    return [(r["source"], r["heading"]) for r in result["results"][:limit]]


def test_opening_hours_is_top_result(sections):
    result = search_policies(sections, "What time do you open on Saturday?")

    assert pairs(result, 1) == [("faq.md", "When are you open?")]


def test_day_price_of_ebike(sections):
    result = search_policies(sections, "How much is an e-bike for a whole day?")

    assert ("prices.md", "Bike rental") in pairs(result, 3)


def test_age_limit_for_ebike(sections):
    result = search_policies(sections, "Can my 14-year-old rent an e-bike?")

    assert ("faq.md", "Are there age limits?") in pairs(result, 3)


def test_cancellation_refund(sections):
    result = search_policies(sections, "I want to cancel, how much do I get back?")

    assert "cancellations.md" in [r["source"] for r in result["results"][:3]]


def test_dog(sections):
    result = search_policies(sections, "Can I take my dog?")

    assert pairs(result, 1) == [("faq.md", "Can I take my dog?")]


def test_christmas_finds_opening_hours(sections):
    result = search_policies(sections, "Do you open on Christmas?")

    assert ("faq.md", "When are you open?") in pairs(result, 3)


def test_unrelated_question_has_no_results(sections):
    result = search_policies(sections, "What is the capital of Australia?")

    assert result == {"query": "What is the capital of Australia?", "results": []}


def test_preamble_reachable_by_currency_question(sections):
    result = search_policies(sections, "Which currency are prices in?")

    assert pairs(result, 1) == [("prices.md", "Prices")]


@pytest.mark.parametrize("query", ["", "   ", None])
def test_empty_query(sections, query):
    assert search_policies(sections, query)["results"] == []


def test_top_k_and_ordering(sections):
    result = search_policies(sections, "bike", top_k=2)

    scores = [r["score"] for r in result["results"]]
    assert len(scores) == 2
    assert scores == sorted(scores, reverse=True)
    assert set(result["results"][0]) == {"source", "heading", "text", "score"}


def test_only_positive_scores():
    only = [PolicySection("a.md", "Dogs", "No dogs."), PolicySection("a.md", "Cats", "Meow.")]

    result = search_policies(only, "dogs")

    assert [r["heading"] for r in result["results"]] == ["Dogs"]
