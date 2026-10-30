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


def test_preamble_reachable_by_currency_question(sections):
    result = search_policies(sections, "Which currency are prices in?")

    assert pairs(result, 1) == [("prices.md", "Prices")]


@pytest.mark.parametrize("query", ["", "   ", None])
def test_empty_query(sections, query):
    assert search_policies(sections, query)["results"] == []


def test_top_k_and_ordering(sections):
    result = search_policies(sections, "price deposit hour", top_k=2)

    scores = [r["score"] for r in result["results"]]
    assert len(scores) == 2
    assert scores == sorted(scores, reverse=True)
    assert set(result["results"][0]) == {"source", "heading", "text", "score"}


def test_only_positive_scores():
    only = [PolicySection("a.md", "Dogs", "No dogs."), PolicySection("a.md", "Cats", "Meow.")]

    result = search_policies(only, "dogs")

    assert [r["heading"] for r in result["results"]] == ["Dogs"]


RECALL_CASES = [
    ("What time do you open on Saturday?", "When are you open?"),
    ("What time do you close?", "When are you open?"),
    ("Open on Sunday in November?", "When are you open?"),
    ("Christmas", "When are you open?"),
    ("Where is your shop?", "Where are you?"),
    ("How much is an e-bike for a whole day?", "Bike rental"),
    ("Is there a discount for a week?", "Bike rental"),
    ("Can I rent an e-bike at 15?", "Are there age limits?"),
    ("Can my 14-year-old rent an e-bike?", "Are there age limits?"),
    ("Deposit for a kids bike?", "Deposit"),
    ("Late return fee?", "Late return"),
    ("Do you have a bike lock?", "Add-ons"),
    ("Child seat price?", "Add-ons"),
    ("Storm tomorrow, can I get my money back?", "Bad weather"),
    ("Can I change the date of my booking?", "Changing a booking"),
    ("Can I take my dog?", "Can I take my dog?"),
    ("My bike was stolen", "What if the bike is stolen or lost?"),
    ("Which currency are prices in?", "Prices"),
]


@pytest.mark.parametrize("query, heading", RECALL_CASES)
def test_right_section_in_top_three(sections, query, heading):
    result = search_policies(sections, query)

    assert heading in [r["heading"] for r in result["results"][:3]]


@pytest.mark.parametrize(
    "query",
    [
        "What is the capital of Australia?",
        "Do you rent scooters?",
        "Is the bike insured?",
        "How do I fix a flat tire?",
    ],
)
def test_off_topic_has_no_results_and_a_note(sections, query):
    result = search_policies(sections, query)

    assert result == {"query": query, "results": [], "note": "No relevant policy found."}


def test_ebike_is_not_just_bike(sections):
    result = search_policies(sections, "ebike")

    assert "Electric bike" in result["results"][0]["text"]


def test_hyphenated_ebike_matches_section_text(sections):
    assert search_policies(sections, "E-Bike")["results"] == search_policies(sections, "ebike")["results"]


def test_prefix_matching_both_ways():
    heading_form = [PolicySection("a.md", "Cancelling", "Cancelled rides.")]
    plural_form = [PolicySection("a.md", "Parking", "Parking prices are low.")]

    assert search_policies(heading_form, "cancel")["results"][0]["score"] == 4  # cancel ~ cancelling + cancelled
    assert search_policies(plural_form, "price parking")["results"][0]["score"] == 5  # price ~ prices


def test_short_tokens_do_not_prefix_match():
    only = [PolicySection("a.md", "Cats", "A cat sat. Cats everywhere.")]

    assert search_policies(only, "ca")["results"] == []


@pytest.mark.parametrize("top_k", [None, "3", 2.5, -1, 0, True])
def test_garbage_top_k_falls_back_to_three(sections, top_k):
    result = search_policies(sections, "price of bike rental per day deposit", top_k=top_k)

    assert len(result["results"]) == 3


def test_none_query_has_note(sections):
    assert search_policies(sections, None)["results"] == []
    assert search_policies(sections, None)["note"] == "No relevant policy found."


def test_tie_prefers_more_heading_hits_then_shorter_section():
    long_body = PolicySection("a.md", "Other", "storm storm refund " + "x " * 20)
    heading_hit = PolicySection("a.md", "Storm refund", "nothing")
    short = PolicySection("a.md", "Third", "storm refund")

    result = search_policies([long_body, short, heading_hit], "storm refund")

    assert [r["heading"] for r in result["results"]] == ["Storm refund", "Third", "Other"]
