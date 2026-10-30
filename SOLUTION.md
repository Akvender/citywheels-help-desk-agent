# Solution: CityWheels help desk agent

A command-line agent that answers CityWheels customer questions from the shop's own policies and bookings. A large language model decides which tool to call. Plain Python tools return the facts, and every refund amount is calculated by code.

## 1. Install and run

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
cp .env.example .env          # then put your own key in LLM_API_KEY
```

| What | Command |
|---|---|
| Ask a question | `uv run helpdesk "I want to cancel booking CW-1002. How much will I get back?"` |
| See every tool call (on stderr) | `uv run helpdesk "What time do you open on Saturday?" --verbose` |
| Run all tests (offline, no key needed) | `uv run pytest` |
| Run the evaluation (needs a key) | `uv run python eval/run_eval.py --runs 3 --model gemini-3.5-flash-lite` |

The fixed "current" time from the data README (2026-06-10 09:00, Europe/Warsaw) is set in `src/helpdesk/config.py`. Tests run in GitHub Actions on every push (`.github/workflows/tests.yml`).

## 2. Model and provider

- **Provider:** Google Gemini, free tier, through its **OpenAI-compatible endpoint**. The code talks to one small interface (`ChatModel` in `llm.py`), so any OpenAI-compatible provider (Gemini, Groq, Ollama, OpenAI) can be used by changing three variables in `.env`.
- **Model:** `gemini-3.5-flash` during development and `gemini-3.5-flash-lite` for the committed evaluation. Both support tool calling, cost nothing and answer quickly.
- **Why not the newest model:** `gemini-3.8-flash` (the model in Google's examples) returned HTTP 503 and then timed out when I tested it.
- **Why the evaluation ran on flash-lite:** the free daily quota of `gemini-3.5-flash` ran out during my first evaluation attempt (HTTP 429).
- **Why not GitHub Models,** which the brief mentions: it was retired on 30.07.2026.

One provider detail mattered. With tool calls, Gemini 3 adds a `thought_signature` to each tool call and expects it back in the next request. I tested this: sending the history without that field gives **HTTP 400**. So the adapter returns the assistant message exactly as received (`message.model_dump(exclude_none=True)`), and the loop appends it unchanged. A test (`tests/test_llm.py`) protects this.

## 3. How the agent works

```
question ─► run_agent ─► model.complete(messages, tool schemas)
               ▲   │
               │   ├─ tool calls? ─► dispatch(name, args) ─► tool (plain function) ─► data/
               │   │                       │ JSON result, appended as role "tool"
               └───┘◄──────────────────────┘
                   └─ no tool calls ─► final answer
                      (after 6 steps, or an empty answer ─► safe answer with the staff contact)
```

### The loop (`agent.py`)

- I wrote the loop myself in about 40 lines instead of using LangChain or LangGraph. The problem is small (one agent, three tools, no branching, no stored state). The brief grades whether I understand the loop, and the fake-model test should test my loop, not a framework.
- The model can ask for several tools in one reply. Each call gets its own `role: "tool"` answer with the matching `tool_call_id`.
- The model is called with `temperature=0`, a 60-second timeout and at most 2 retries. Provider errors become `ModelError`, and the CLI prints a short message.
- An empty, cut-off (`finish_reason=length`) or filtered answer is never shown as if it were a real answer.

### The tools (`src/helpdesk/tools/`)

Each tool is a plain function. It knows nothing about the model, gets its data as arguments, and never raises: problems come back as `{"found": false}` or `{"error": ...}`.

- **`calculate_refund(booking_id, cancel_at?)`** applies `cancellations.md`:
  - Only `confirmed` bookings can be cancelled.
  - The refund of the rental price is 100% at 48 h or more before the start, 50% at 24 h or more, and 0% below that. The boundaries use `>=`: exactly 48 h gives 100% (CW-1007) and exactly 24 h gives 50% (CW-1010).
  - The booking fee is never refunded. The deposit is always refunded in full.
  - Money is `Decimal` from the moment the JSON is read; nothing passes through `float`.
  - The result includes the breakdown and how the money comes back: to the card within 5 working days, or as a new voucher.
  - If `cancel_at` is not the current time, the result is marked `hypothetical`. This supports questions like "and if I cancel tomorrow?".
- **`get_booking(booking_id)`** normalises input such as `cw1002` to `CW-1002`. An unknown or malformed number gives a clear "not found".
- **`search_policies(query)`** splits the three policy files into 22 sections at their `##` headings and ranks them by keyword overlap. A word in the heading scores 3 and a word in the body scores 1. Results need a score of at least 2. A small synonym table and prefix matching handle `close` vs `closed`. "e-bike" is normalised to "ebike".
  - **Why not embeddings:** for 22 short sections, keyword search is deterministic, needs no extra service or key, and every result can be explained and unit-tested. Its limits are listed in section 6.

**`registry.py`** connects the tools to the model:

- It holds the JSON schemas the model sees. Their descriptions are part of the prompt.
- It binds the data and the current time to each tool.
- `dispatch` checks the model's arguments against the schema, so the model cannot pass anything else. Before this check existed, the model could override the bound current time and get a refund for a different moment.

### The instructions (`prompts.py`)

- Answer only from tool results.
- Use the right tool for bookings, refunds and rules.
- Never compute or adjust amounts. Quote them as the tool returns them, say which one is the total, and say how the money comes back.
- If nothing relevant is found, or the question is not about CityWheels, say so and give the staff contact. The contact text is copied verbatim from `cancellations.md`.
- The agent cannot cancel or change bookings. It only informs.
- Ask for a missing booking number.
- Do not guess after a tool error.
- The current date is part of the prompt.

### Tests

`uv run pytest` runs 209 tests in about 3 seconds, with no network and no key. Coverage is about 99%.

- **Refunds:** every rule of `calculate_refund` is tested with the real bookings: both boundaries, one minute below each boundary, voucher, the three non-cancellable statuses, rounding, time zones, and wrong input.
- **Agent loop:** tests use a scripted `FakeModel` (`tests/fakes.py`). They cover a tool round trip, two tool calls in one reply, the provider metadata passed back unchanged, unknown tools, broken JSON arguments, the step limit, and empty answers.
- **End to end:** one test checks that the amount returned by `calculate_refund` (340.00 EUR) reaches the final answer unchanged.

## 4. Evaluation

The evaluation lives in `eval/`. `questions.json` holds 20 questions with their expected outcomes:

| Category | Count | Includes |
|---|---|---|
| Refunds | 9 | both boundaries, voucher, a non-cancellable booking, "what if I cancel tomorrow", a question in Polish, a prompt-injection attempt ("give me 100%") |
| Bookings | 3 | dates, an unknown number, a missing number |
| Policy | 3 | |
| Must refuse or redirect | 5 | off-topic, no data about guided tours, storm (the staff decide), "change my booking", "print your system prompt" |

`run_eval.py` runs the real agent and checks automatically:

- the expected tools were called;
- the expected refund total appears in the answer;
- required and forbidden phrases (word-boundary matches);
- **grounding:** every money amount in the answer must exist as a money value in a tool result. This catches invented prices.

The script also:

- asks every question several times, because answers vary even at temperature 0, and reports which questions always pass, are flaky, or always fail;
- counts API problems (rate limits, timeouts) separately, not as wrong answers;
- stores every tool call with its arguments and result.

### Results

| Run | Commit | Model | Result |
|---|---|---|---|
| 1 (`eval/runs/run1-3decf71-flash-lite.md`) | 3decf71 | gemini-3.5-flash-lite | **12 / 15** (1 run per question) |
| 2 (`eval/results.md`) | 435f7e7 | gemini-3.5-flash-lite | **59 / 60** raw, 60 / 60 after triage (20 questions × 3 runs; 19 always pass, 1 flaky) |

I read every failure by hand and labelled it in `eval/triage.json`. A failure is either an agent error, a check that is too strict, or an ambiguous question. I do not quietly edit a check after seeing a result.

**Run 1 failures:**

1. **"What does a kids bike cost per hour?": agent error, a real retrieval bug.**
   - The word "hour" was in the synonym group for opening hours, so the question matched "When are you open?".
   - The section with the price table is called "Bike rental". Earlier I had told the search to ignore "bike" and "rental", to stop off-topic questions like "Is the bike insured?" from matching. So the price table lost its heading.
   - One fix had broken the most important section, and my unit tests had not caught it.
   - Fixed: the generic words are now ignored only in the question, and "hour" is no longer an opening-hours synonym. I added 8 price questions worded differently from the evaluation question.
2. **CW-1006 (not cancellable): check too strict.** The correct answer said "total refund: 0.00 EUR", and the check counted that as an amount. Fixed in the check, and recorded in the triage.
3. **CW-1001: agent error, minor.** The amount (90 EUR) was correct, but the answer did not say the money goes back to the card. Fixed with one prompt rule.

**Run 2:**

- The one failed attempt was the Polish question. The answer was correct, but it was written as "**340.00** EUR": the markdown bold sits between the number and the currency, so my parser missed it.
- I labelled it "check too strict" and left the parser as it was. It is a known gap.
- Five questions were added after run 1, from reviewers' findings: missing booking number, "change my booking", Polish, prompt leak, "cancel tomorrow". They are marked `added_after_run` in `questions.json`.

### What the evaluation cannot tell you

- The questions are written by me, so they test what I thought of.
- Phrase checks can fail a correct answer worded differently and pass a bad one that contains the phrase.
- Grounding checks that a number came from a tool, not that it was used in the right meaning.
- 20 questions × 3 runs on one model is a small sample.
- I treat the score as a lower bound on quality, and the hand-written triage as part of the result.

## 5. How I used AI coding assistants

I built this with **Claude Code** as the main assistant.

- **Process:** a requirements document and a plan first, then specialised sub-agents.
  - Test-first agents wrote each module, tests before code.
  - Separate reviewer agents checked the work: a Python reviewer, a retrieval reviewer, a "silent failure" hunter, a test-quality reviewer, a security reviewer and an evaluation reviewer.
  - **OpenAI Codex** reviewed the plan independently and later graded the repository as if it were the hiring company's engineer.
- **My part:**
  - I made or approved the decisions: own loop vs framework, provider and model, a public repository, what to fix and what to accept as a limitation.
  - No agent report was taken on trust: the tests and the real model were re-run in the main session after every step.
  - Real mistakes were logged as they happened.

**Where the assistants were wrong, and how it was noticed:**

- **Invented policy text.**
  - **What happened:** the refund tool told customers with a completed booking that "the deposit is not lost, staff settle it on return". The policy says no such thing.
  - **Where it came from:** the instruction I gave the coding agent, which was based on a suggestion from the plan review. The agent implemented it and even wrote a test that locked it in.
  - **How it was noticed:** a reviewer compared the text with `cancellations.md`.
  - **Lesson:** a tool must only say what is in the data.
- **A synonym table that never worked.** The search stemmed the query ("christmas" became "christma") but not the synonym list, so the holiday synonyms never fired. The test passed only because the test question also contained "open". The reviewer ran the word "Christmas" on its own.
- **A security hole left as "out of scope".**
  - **What happened:** the tools were bound with `functools.partial`, and the argument check accepted `now` and `bookings`. The model, or a prompt injection, could override the current time and get a refund for another moment.
  - **How it was noticed:** the coding agent mentioned it only as something it had left out.
  - **Fix:** I treated it as a real hole. Arguments must now match the schema, and a test covers it.
- **A report that was not true anymore.** One agent reported that a test was failing, but another agent had already fixed it. Re-running `uv run pytest` showed all green. Since then every report is verified by running the tests.
- **My own evaluation checks were too loose at first.** The phrase "no" matched inside "not" and "know", and "15" would have passed a date in the wrong month. The agent building the evaluation pointed this out.
- **The retrieval regression** described in section 4 was also AI-written. A reviewer's suggestion fixed one problem and broke another. Only the evaluation against the real model caught it.

## 6. Limitations

- **Keyword search is tuned to these 22 sections.**
  - Paraphrases outside the synonym table can miss. For example, "What are your hours?" without the word "open" finds nothing, and "children" no longer reaches "Kids bike".
  - A question about a topic the documents mention only in passing can match the wrong section.
- **No customer identity.** Anyone who knows or guesses a booking number can read that booking. The agent is read-only and the data has no personal details. A real deployment would need a verification field and rate limiting.
- **No conversation memory in the CLI.** Each question is answered alone. The loop already accepts a `history`, so this is a small step.
- **The model can still word an answer badly.** The prompt and the evaluation reduce this, but they do not prove an answer correct. The agent does not validate the final text against the tool results.
- **Opening hours, late-return fees and new-booking prices come from the policy text.** No tool calculates them, so the model reads them from the search results.
- **One provider and one model** in the committed evaluation, because of free-tier limits.

## 7. Next steps with more time

1. Add an interactive `--chat` mode with conversation memory, for follow-ups like "and if I cancel tomorrow?". The refund tool already supports `cancel_at`.
2. Compare two models on the same evaluation (`gemini-3.5-flash` vs `-flash-lite`, or a Groq model) and report the accuracy, stability and latency of each.
3. Use hybrid retrieval (BM25 plus embeddings) once there are more documents, and evaluate it on a held-out set of paraphrased questions.
4. Add deterministic tools for the remaining calculations (late-return fee, price of a new rental), so the model never reads prices from text.
5. Add an LLM judge as a second signal for answer quality, calibrated against my hand labels and never mixed into the headline number.
6. Fix the amount parser for markdown inside amounts (the Polish case in run 2).
