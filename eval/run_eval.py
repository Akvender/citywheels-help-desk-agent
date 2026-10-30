"""Run the agent on every question in eval/questions.json and check the answers.

Usage: uv run python eval/run_eval.py [--runs 1] [--delay 4] [--model NAME] [--only ID ...] [--out eval/results.md]
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from checks import check_case
from dotenv import load_dotenv

from helpdesk.agent import run_agent
from helpdesk.config import NOW, load_llm_settings
from helpdesk.data import load_bookings, load_policy_sections
from helpdesk.llm import ModelError, OpenAICompatibleModel
from helpdesk.tools.registry import build_tools

QUESTIONS_FILE = Path(__file__).with_name("questions.json")
RETRY_WAIT_SECONDS = 20
MAX_RETRIES = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the CityWheels help desk agent.")
    parser.add_argument("--runs", type=int, default=1, help="how many times to ask each question")
    parser.add_argument("--delay", type=float, default=4, help="seconds to wait between questions")
    parser.add_argument("--model", help="model name; overrides LLM_MODEL")
    parser.add_argument("--only", nargs="+", help="run only these question ids")
    parser.add_argument("--out", default="eval/results.md", help="markdown report path")
    return parser.parse_args()


def ask_with_retries(case: dict, model, tools):
    """Run the agent; on API errors wait and retry. Returns (result, error_text)."""
    error = ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            return run_agent(case["question"], model, tools), ""
        except ModelError as model_error:
            error = str(model_error)
            if attempt < MAX_RETRIES:
                print(f"  API error ({error}); retrying in {RETRY_WAIT_SECONDS} s")
                time.sleep(RETRY_WAIT_SECONDS)
    return None, error


def run_one(case: dict, run: int, model, tools) -> dict:
    """Produce one raw record: status is 'pass', 'fail' or 'infra_error'."""
    result, error = ask_with_retries(case, model, tools)
    record = {"id": case["id"], "category": case["category"], "run": run, "question": case["question"]}
    if result is None:
        return {**record, "status": "infra_error", "answer": "", "tools": [], "reasons": [error]}
    reasons = check_case(case, result.answer, result.trace)
    return {
        **record,
        "status": "fail" if reasons else "pass",
        "answer": result.answer,
        "tools": [call.name for call in result.trace],
        "reasons": reasons,
    }


def summarize(records: list[dict]) -> dict:
    graded = [r for r in records if r["status"] != "infra_error"]
    return {
        "passed": sum(r["status"] == "pass" for r in graded),
        "graded": len(graded),
        "infra_errors": len(records) - len(graded),
    }


def per_question_rows(records: list[dict], runs: int) -> list[str]:
    rows = []
    for case_id in dict.fromkeys(r["id"] for r in records):  # unique ids, original order
        mine = [r for r in records if r["id"] == case_id]
        passes = sum(r["status"] == "pass" for r in mine)
        errors = sum(r["status"] == "infra_error" for r in mine)
        reasons = "; ".join(sorted({reason for r in mine for reason in r["reasons"]})) or "-"
        tools = ", ".join(mine[0]["tools"]) or "-"
        note = f" ({errors} infra error)" if errors else ""
        rows.append(f"| {case_id} | {mine[0]['category']} | {passes}/{runs}{note} | {tools} | {reasons} |")
    return rows


def failure_sections(records: list[dict]) -> list[str]:
    lines = []
    for r in records:
        if r["status"] == "pass":
            continue
        lines += [f"### {r['id']} (run {r['run']}, {r['status']})", "", f"Question: {r['question']}", ""]
        lines += ["Answer:", "", *[f"> {line}" for line in r["answer"].splitlines() or ["(none)"]], ""]
        lines += ["Reasons:", *[f"- {reason}" for reason in r["reasons"]], ""]
    return lines or ["No failures.", ""]


HOW_TO_READ = """\
Each answer gets these automatic checks (only the ones a question defines, plus grounding):

- expected tools: the agent must have called the tool(s) listed for the question.
- expected total: the correct refund must appear as an amount in the answer.
- required phrases: for each group, at least one phrase must appear (case-insensitive).
- forbidden phrases / amounts, and a maximum number of amounts.
- grounding (always on): every money amount in the answer must also appear in a tool result.
  It catches invented prices, but it cannot judge meaning: an answer can quote a real number
  from a tool and still use it wrongly, or be phrased badly, and pass. Phrase checks can also
  fail a correct answer that uses different words. Treat the numbers as a lower bound on quality.
- infra errors (API down, rate limit) are reported separately and are not counted as wrong answers."""


def build_report(records: list[dict], model_name: str, runs: int) -> str:
    stats = summarize(records)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Evaluation results", "",
        f"- Model: {model_name}", f"- Date: {date}", f"- Runs per question: {runs}", "",
        f"**Passed {stats['passed']} / {stats['graded']} attempts "
        f"(infra errors: {stats['infra_errors']}, excluded)**", "",
        "| Question | Category | Passed | Tools (first run) | Failure reasons |",
        "|---|---|---|---|---|",
        *per_question_rows(records, runs), "",
        "## Failures", "", *failure_sections(records),
        "## How to read this", "", HOW_TO_READ, "",
    ]
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    load_dotenv()
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    settings = load_llm_settings()
    model = OpenAICompatibleModel(settings)
    tools = build_tools(load_bookings(), load_policy_sections(), NOW)
    cases = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] in args.only]

    records = []
    for index, case in enumerate(cases):
        for run in range(1, args.runs + 1):
            if records:
                time.sleep(args.delay)
            record = run_one(case, run, model, tools)
            records.append(record)
            print(f"[{index + 1}/{len(cases)}] {case['id']} run {run}: {record['status']}")

    out = Path(args.out)
    out.write_text(build_report(records, settings.model, args.runs), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    stats = summarize(records)
    print(f"Passed {stats['passed']} / {stats['graded']} (infra errors: {stats['infra_errors']})")


if __name__ == "__main__":
    main()
