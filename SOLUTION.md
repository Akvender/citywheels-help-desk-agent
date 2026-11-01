# CityWheels Help Desk Agent: Solution

## Overview

The assistant answers questions about a fictional bike rental shop using the supplied policies and bookings. The LLM chooses tools and writes the response; tools supply facts and calculate refund amounts. The prompt requires the model to use tool results rather than outside knowledge and to send action requests or unresolved questions to staff. The system does not modify bookings.

Refund arithmetic is deterministic Python code. Other prices and fees are retrieved as policy text; there are no calculation tools for new rentals or late returns.

## Architecture

```text
CLI -> configuration and data loaders -> bound tool registry
 |
 v
agent loop <-> ChatModel / OpenAI-compatible adapter <-> provider
 |
 +-> dispatch -> search_policies   -> policy sections
             -> get_booking      -> bookings
             -> calculate_refund -> bookings + fixed reference time
 |
 +-> final answer and tool trace -> CLI
```

| Component | Responsibility |
| --- | --- |
| `cli.py` | Parse the question and `--verbose`, load settings and data, print answers and errors |
| `agent.py` | Build messages, execute requested tools and return an `AgentResult` |
| `llm.py` | Define `ChatModel`, call the provider and normalize provider failures as `ModelError` |
| `tools/registry.py` | Publish tool schemas, bind data and time, validate argument names and dispatch calls |
| `tools/` | Retrieve policies, look up bookings and calculate refunds independently of the model |
| `data.py` | Load bookings with `Decimal` values and split Markdown policies into sections |
| `config.py` | Read LLM settings and define the data path and fixed reference time |
| `prompts.py` | Define tool-use instructions, response constraints and staff contact |

For a question about cancelling CW-1002, the CLI loads the data and binds it to the tools. The agent sends the question, system prompt and tool schemas to the model. Requested calls are dispatched, recorded in the trace and appended as tool messages with matching `tool_call_id` values. The model then receives those results and can request more tools or answer; `calculate_refund` returns a total of `340.00` EUR for cancellation at the reference time. Multiple calls in one reply are executed sequentially.

## Key design decisions

### A small explicit loop

I used an application-owned loop rather than LangChain or LangGraph because the task has one agent and three tools, with no workflow branching or persistent state. The `ChatModel` interface allows the same loop to run against a scripted model in tests.

### Provider adapter and model choice

I used Gemini's free tier through its OpenAI-compatible endpoint. Provider URL, credential and model are configuration settings, while the agent depends only on `ChatModel`. Other endpoints must support the chat completions and tool-calling behavior this adapter uses.

Development used `gemini-3.5-flash`. The committed evaluations use `gemini-3.5-flash-lite` because the larger model reached its free daily quota (HTTP 429) during the first evaluation run. `gemini-3.8-flash` returned HTTP 503 responses and timeouts during testing. GitHub Models, suggested in the brief, [was retired on July 30, 2026](https://docs.github.com/en/github-models).

### Preserve provider metadata

The adapter returns `message.model_dump(exclude_none=True)`, and the loop appends that message unchanged. This preserves Gemini's tool-call `thought_signature` for subsequent requests; reconstructing only standard fields would discard it. Adapter and loop tests cover metadata preservation.

### Keyword retrieval

The three policy files load into 22 sections, split at `##` headings with document preambles retained. A small keyword search avoids an embedding service and makes ranking reproducible. Heading matches score 3 and body matches score 1; sections need at least 2 points, and the tool returns up to 3 results.

Search normalizes e-bike spellings, expands a synonym table and supports prefix matches when the shorter word has at least 4 characters. The current tokenizer removes stopwords and generic bike-rental terms from both queries and section text. Retrieval remains sensitive to wording; its limits are described below.

### Decimal arithmetic and bounded tool arguments

Booking JSON is loaded with `parse_float=Decimal`, avoiding conversion through binary floating point. Refund output is formatted to two decimal places using `ROUND_HALF_UP`; displayed hours are rounded down so that a value just below a threshold does not appear to meet it.

The registry binds bookings and the reference time with `functools.partial`. Dispatch checks required and unknown argument names against the published schemas, preventing the model from overriding bound values such as `now` or `bookings`. This is a limited schema check, not general JSON Schema type validation: tool functions validate relevant values, and dispatch catches execution failures.

### Failure handling

The default loop limit is 6 model calls. Exhausting it or receiving a blank answer produces a fallback with the staff contact. The adapter rejects truncated (`length`) and filtered (`content_filter`) responses, and raises `ModelError` for empty provider choices or SDK errors. The CLI reports these failures on stderr.

Provider calls use temperature 0, a 60-second SDK timeout and at most 2 SDK retries. These settings do not guarantee identical answers or a 60-second total runtime. Unknown tools, malformed arguments and tool exceptions return JSON errors to the model rather than terminating the loop.

## Tools

The following contracts describe model-visible arguments; data and time are supplied by the application. Dispatch serializes results as JSON text.

| Tool | Inputs | Successful output | Missing data or invalid input |
| --- | --- | --- | --- |
| `search_policies` | Required string `query` | `query` and ranked `results`, each containing `source`, `heading`, `text`, `score` | Empty `results` plus `note: "No relevant policy found."` |
| `get_booking` | Required string `booking_id` | `found: true` and a copied `booking`, with decimal money formatted as strings | `found: false`, echoed `booking_id` and a message |
| `calculate_refund` | Required string `booking_id`; optional string `cancel_at` in ISO 8601 with a time-zone offset | Booking ID, `found`, cancellation time, hours before start, eligibility, reason, refund method, percentage and amount breakdown | Unknown booking: `found: false` and a message; invalid cancellation time: booking ID and `error` |

Booking IDs are normalized, so `cw1002` resolves to `CW-1002`. Dispatch failures have the shape `{"error": "..."}`; unexpected execution failures return `{"error": "Tool failed, do not guess."}` and log the exception.

### Refund rules

For a `confirmed` booking, the rental refund is:

| Time before rental start | Rental price refunded |
| --- | --- |
| At least 48 hours | 100% |
| At least 24 hours, less than 48 hours | 50% |
| Less than 24 hours | 0% |

The boundaries are inclusive: CW-1007 is exactly at 48 hours and CW-1010 exactly at 24 hours at the fixed reference time. The booking fee is never refunded. The deposit is returned in full when a confirmed booking is cancelled, including when the rental refund is zero. Bookings marked `in_progress`, `completed` or `cancelled` cannot be cancelled and return zero for every refund component.

The tool uses the stored rental price for the whole booking, including add-ons. It returns `rental_refund_eur`, `booking_fee_refund_eur`, `deposit_refund_eur` and `total_refund_eur`. Card refunds go to the same card within 5 working days; voucher payments return as a new voucher, including the deposit.

Without `cancel_at`, calculation uses `2026-06-10T09:00:00+02:00`. A different cancellation time adds `hypothetical: true` and qualifies the reason. This supports what-if questions without performing a cancellation. Storm-warning exceptions require staff review rather than an automatic override.

## Testing

The offline suite contains 209 tests. `uv run pytest --cov=helpdesk --cov-report=term-missing` passes all of them with 99% statement coverage (363 of 366 statements). The uncovered statements are in the `__main__.py` entry point. See [README.md](README.md#testing) for standard commands.

Refund tests cover the supplied bookings, inclusive thresholds and one minute below them, non-cancellable statuses, voucher payments, rounding, time zones and invalid input. Booking and retrieval tests cover normalization, missing records, ranking and price-query regressions. Registry tests check malformed JSON, unknown or missing arguments and attempts to override bound data or time.

`tests/fakes.py` supplies `FakeModel` for scripted tool round trips, multiple calls, provider metadata, failures, empty answers and the step limit. An integration test checks that the tool's `340.00` EUR result reaches the final answer unchanged. Adapter tests use an injected client; no test needs a live provider. CLI and evaluation-check behavior are also tested. CI runs the suite on pushes and pull requests.

## Evaluation

### Method

`eval/questions.json` contains 20 authored cases: 9 refund questions, 3 booking questions, 3 policy questions and 5 refusal or escalation cases. They include both refund boundaries, voucher payment, missing and unknown booking IDs, a Polish question, hypothetical cancellation and prompt-injection attempts. Five cases are marked `added_after_run` because they were added after run 1.

`eval/run_eval.py` calls the real agent repeatedly and records answers plus full tool arguments and results. Checks cover expected tools, expected refund totals, required or forbidden phrases with word boundaries, forbidden amounts and limits on nonzero amounts. Grounding checks require each parsed nonzero monetary amount to occur in tool-returned money fields or policy text. Zero amounts are excluded from grounding and nonzero-amount limits.

The report separates infrastructure errors from graded answers and groups questions as always passing, flaky or always failing. The runner retries `ModelError` failures twice with a 20-second wait, in addition to SDK retries, and marks a run incomplete if more than 20% of attempts have infrastructure errors.

### Recorded results

Both runs used `gemini-3.5-flash-lite` and recorded no infrastructure errors.

| Run | Recorded revision | Attempts | Raw result | Manual interpretation |
| --- | --- | --- | --- | --- |
| [Run 1](eval/runs/run1-3decf71-flash-lite.md) | `3decf71` (archive filename and triage) | 15 questions, once each | 12/15 | Three failures investigated and fixes recorded |
| [Run 2](eval/results.md) | `435f7e7` | 20 questions, three times each | 59/60 | The single failure was a parser issue, not a wrong answer (see below); 19 questions always passed and 1 was flaky |

The runner's adjusted score excludes attempts triaged as "check too strict" rather than counting them as passes, so with the current triage it reports 59/59.

### Failure triage

`eval/triage.json` records labels and explanations tied to a run and revision. Labels distinguish agent errors, overly strict checks, ambiguous questions and infrastructure failures. Only matching-revision labels for overly strict checks affect the runner's adjusted denominator; stale labels remain visible for context.

Run 1 exposed these failures:

- The kids-bike hourly-price question retrieved opening hours. Two causes: `hour` was in the opening-hours synonym group, and the price table's heading ("Bike rental") consisted only of terms filtered as generic, so it received no heading score. Both are fixed and covered by eight additional price-query tests in `tests/test_policies.py`.
- For CW-1006, the answer correctly stated a zero refund, but the check counted `0.00 EUR` against a no-amount limit. The current check limits nonzero amounts instead, as recorded in triage.
- For CW-1001, the answer gave the correct `90.00` EUR refund but omitted the card refund method. The system prompt now explicitly requires the payment-return method alongside a refund amount.

Run 2's sole raw failure was the Polish response containing `**340.00** EUR`. Manual triage accepted the answer, including its breakdown and card method; the parser missed the total because Markdown separated the number from the currency. The parser gap remains open.

### Evaluation limits

The cases were authored during development and include post-run additions, so they are not a held-out benchmark. Phrase checks can reject correct wording or accept an incorrect explanation containing the expected words. Amount grounding checks provenance, not whether an amount was used correctly, and only checks amounts the parser recognizes. Twenty questions with three attempts on one provider and model do not establish general reliability; manual acceptance must be read alongside the raw score.

## Use of AI coding assistants

I used Claude Code as the main coding assistant and Codex for a second review of the plan and repository. The workflow started with requirements and a plan, followed by test-first module work and separate review passes. I made the design and fix-priority decisions and verified each step by rerunning the tests and the real model. Three issues in assistant-written code were caught this way:

- Tools bound with `functools.partial` accepted `now` and `bookings` as model arguments, so the model could override the reference time. Dispatch now rejects arguments outside the schema, with tests.
- Query words were stemmed but the synonym table was not, so holiday synonyms never matched. Retrieval was changed to prefix matching.
- A retrieval change regressed price questions; the evaluation against the real model exposed it (see run 1 above).

## Limitations

- Keyword retrieval is specific to this small corpus. Unrecognized paraphrases, typos or topics mentioned only in passing can miss relevant sections or retrieve unrelated text. For example, an hours question without an opening-related keyword can fail.
- There is no customer identity verification or rate limiting. Anyone with a booking number can request it; the supplied data contains no customer identity fields.
- Each CLI question starts a new conversation. `run_agent` accepts history, but the CLI does not persist it.
- Final text is not validated against tool results at runtime. Prompt constraints and evaluation do not guarantee that the model follows every rule.
- Opening hours, late fees and new-rental prices are returned as text rather than calculated by dedicated tools.
- The committed evaluation covers one provider and model.

## Future work

Add an interactive chat mode using the existing history parameter. Compare models on the same evaluation, including latency and stability, and maintain a held-out paraphrase set before extending retrieval with BM25 or embeddings. Add deterministic tools for late-return fees and new-rental prices, and fix Markdown handling in the amount parser. A separately reported LLM judge could complement the rule checks after calibration against manual labels. A deployment using real customer bookings would also need identity verification and rate limiting.
