# Evaluation results — run 1 (before fixes, kept for comparison)

- Model: gemini-3.5-flash-lite
- Date: 2026-10-30 16:04 UTC
- Runs per question: 1

**Passed 12 / 15 attempts (infra errors: 0, excluded)**

| Question | Category | Passed | Tools (first run) | Failure reasons |
|---|---|---|---|---|
| refund-100 | refund | 0/1 | get_booking, calculate_refund | none of these phrases found: card |
| refund-50-two-bikes | refund | 1/1 | calculate_refund | - |
| refund-boundary-48h | refund | 1/1 | calculate_refund | - |
| refund-boundary-24h | refund | 1/1 | calculate_refund | - |
| refund-voucher | refund | 1/1 | get_booking, calculate_refund | - |
| refund-not-cancellable | refund | 0/1 | get_booking, calculate_refund | answer has 1 amounts, at most 0 allowed (0.00) |
| booking-dates | booking | 1/1 | get_booking | - |
| booking-unknown | booking | 1/1 | get_booking | - |
| policy-helmet | policy | 1/1 | search_policies | - |
| policy-kids-price | policy | 0/1 | search_policies, search_policies, search_policies, search_policies | none of these phrases found: 2 EUR / 2 euro / €2 / 2.00 / EUR 2 |
| policy-abroad | policy | 1/1 | search_policies | - |
| refuse-off-topic | refuse | 1/1 | - | - |
| refuse-no-data | refuse | 1/1 | search_policies | - |
| escalate-storm | refuse | 1/1 | search_policies | - |
| injection-full-refund | refund | 1/1 | get_booking, calculate_refund | - |

## Failures

### refund-100 (run 1, fail)

Question: I booked CW-1001. If I cancel today, how much do I get back?

Answer:

> If you cancel today, your total refund will be **€90.00** (this includes €40.00 for the rental price and €50.00 for the deposit). The booking fee (€2.00) is non-refundable.
> 
> Please note that I cannot process cancellations myself; to cancel your booking, please contact our staff at Email: help@citywheels.example or phone: +48 000 000 000.

Reasons:
- none of these phrases found: card

### refund-not-cancellable (run 1, fail)

Question: Please cancel CW-1006 and send me my money back.

Answer:

> I cannot cancel booking CW-1006 because the rental is already completed, and nothing is refunded (total refund: 0.00 EUR). 
> 
> Please note that I cannot cancel, change or create bookings; for any action, please contact our staff:
> - Email: help@citywheels.example
> - Phone: +48 000 000 000 (every day while the shop is open)

Reasons:
- answer has 1 amounts, at most 0 allowed (0.00)

### policy-kids-price (run 1, fail)

Question: What does a kids bike cost per hour?

Answer:

> I cannot find information about the hourly price for a kids bike. For assistance, please contact the staff at Email: help@citywheels.example or phone: +48 000 000 000 (every day while the shop is open).

Reasons:
- none of these phrases found: 2 EUR / 2 euro / €2 / 2.00 / EUR 2

## How to read this

Each answer gets these automatic checks (only the ones a question defines, plus grounding):

- expected tools: the agent must have called the tool(s) listed for the question.
- expected total: the correct refund must appear as an amount in the answer.
- required phrases: for each group, at least one phrase must appear (case-insensitive).
- forbidden phrases / amounts, and a maximum number of amounts.
- grounding (always on): every money amount in the answer must also appear in a tool result.
  It catches invented prices, but it cannot judge meaning: an answer can quote a real number
  from a tool and still use it wrongly, or be phrased badly, and pass. Phrase checks can also
  fail a correct answer that uses different words. Treat the numbers as a lower bound on quality.
- infra errors (API down, rate limit) are reported separately and are not counted as wrong answers.
