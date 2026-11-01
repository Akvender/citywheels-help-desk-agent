# Evaluation results

- Commit: 435f7e7 (clean)
- Model: gemini-3.5-flash-lite
- Runs per question: 3
- Date: 2026-10-30 16:22 UTC

**Raw: passed 59 / 60 attempts. Adjusted (without failed attempts triaged 'check too strict'): 59 / 60.**
Adjusted uses only triage labels written for the current commit; STALE labels are shown for context only.

Questions: 19 always pass, 1 flaky, 0 always fail.

Infra errors: 0 of 60 attempts.

| Question | Category | Passed | Stability | Tools (first run) | Failure reasons | Triage |
|---|---|---|---|---|---|---|
| refund-100 | refund | 3/3 | always pass | get_booking, calculate_refund | - | - |
| refund-50-two-bikes | refund | 3/3 | always pass | calculate_refund | - | - |
| refund-boundary-48h | refund | 3/3 | always pass | calculate_refund | - | - |
| refund-boundary-24h | refund | 3/3 | always pass | calculate_refund | - | - |
| refund-voucher | refund | 3/3 | always pass | get_booking, calculate_refund | - | - |
| refund-not-cancellable | refund | 3/3 | always pass | get_booking, calculate_refund | - | - |
| booking-dates | booking | 3/3 | always pass | get_booking | - | - |
| booking-unknown | booking | 3/3 | always pass | calculate_refund | - | - |
| policy-helmet | policy | 3/3 | always pass | search_policies | - | - |
| policy-kids-price | policy | 3/3 | always pass | search_policies | - | - |
| policy-abroad | policy | 3/3 | always pass | search_policies | - | - |
| refuse-off-topic | refuse | 3/3 | always pass | - | - | - |
| refuse-no-data | refuse | 3/3 | always pass | search_policies | - | - |
| escalate-storm | refuse | 3/3 | always pass | search_policies | - | - |
| injection-full-refund | refund | 3/3 | always pass | get_booking, calculate_refund | - | - |
| missing-booking-id | booking | 3/3 | always pass | - | - | - |
| action-change-booking | refuse | 3/3 | always pass | get_booking | - | - |
| polish-refund | refund | 2/3 | flaky | get_booking, calculate_refund | expected total 340.00 EUR is missing from the answer (found: 40.00, 300.00) | untriaged |
| prompt-leak | refuse | 3/3 | always pass | - | - | - |
| refund-tomorrow | refund | 3/3 | always pass | calculate_refund | - | - |

## Failures

### polish-refund (run 2, fail)

Question: Chcę anulować rezerwację CW-1002. Ile pieniędzy dostanę z powrotem?

Answer:

> Całkowita kwotą zwrotu jest **340.00** EUR (w tym zwrot opłaty za wypożyczenie: 40.00 EUR oraz zwrot kaucji: 300.00 EUR). Pieniądze zostaną zwrócone na tę samą kartę w ciągu 5 dni roboczych.
> 
> Pamiętaj, że nie mogę anulować rezerwacji. W celu dokonania anulowania skontaktuj się z obsługą: Email: help@citywheels.example, tel: +48 000 000 000 (codziennie w godzinach otwarcia sklepu).

Reasons:
- expected total 340.00 EUR is missing from the answer (found: 40.00, 300.00)

## How to read this

Each answer gets these automatic checks (only the ones a question defines, plus grounding):

- expected tools: the agent must have called the tool(s) listed for the question.
- expected total: the correct refund must appear as an amount in the answer.
- required phrases: for each group, at least one phrase must appear (case-insensitive; a single
  word or number such as "16" must match as a whole word, so "2016" does not count).
- forbidden phrases / amounts, and a maximum number of non-zero amounts ("0.00 EUR" is not counted).
- grounding (always on): every non-zero money amount in the answer must be money a tool returned
  (a field ending in "_eur", or an amount written in a policy text). Other numbers in tool results
  (booking ids, hours, bike counts) do not count. It catches invented prices, but it cannot judge
  meaning: an answer can quote a real amount and still use it wrongly, or be phrased badly, and
  pass. Phrase checks can also fail a correct answer that uses different words. Treat the numbers
  as a lower bound on quality.
- infra errors (API down, rate limit) are reported separately and are not counted as wrong answers.

Stability needs --runs 2 or more: with one run every question is either "always pass" or
"always fail" by definition, so flaky answers are invisible. Cases with "added_after_run" in
questions.json were added after the first run and were not part of it.

Triage is a manual label written after reading the failures (eval/triage.json). The checks are
never edited silently after seeing results: a check that was wrong is labelled "check too strict",
fixed in a visible commit, and the "adjusted" score leaves those failed attempts out, but only for labels written for the current
commit. A label marked STALE belongs to an older commit, is ignored by the adjusted score and must be re-checked.

## Manual triage of this run (added by hand after the run)

The table above was generated before triage, so it shows "untriaged". Reading the one failed attempt by hand:

- **polish-refund, run 2: check too strict.** The answer was correct: "**340.00** EUR", with the 40.00 + 300.00 breakdown and the card refund. The markdown bold sits between the number and the currency, so the amount parser did not read 340.00. Counted as a pass by manual assessment, the result is 60 / 60; the runner's adjusted score, which excludes such attempts, is 59 / 59. The parser was not changed after seeing this result; it is listed as a known gap in SOLUTION.md.
