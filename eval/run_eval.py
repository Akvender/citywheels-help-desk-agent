"""Run the agent on every question in eval/questions.json and check the answers.

Usage: uv run python eval/run_eval.py [--runs 3] [--delay 4] [--model NAME] [--only ID ...] [--out eval/results.md]
"""

import argparse
import json
import os
import subprocess
import sys
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
TRIAGE_FILE = Path(__file__).with_name("triage.json")
TRIAGE_LABELS = ("agent error", "check too strict", "ambiguous question", "infrastructure")
INCOMPLETE_SHARE = 0.2  # more than 20% infra errors: the run is not a fair measurement
RETRY_WAIT_SECONDS = 20
MAX_RETRIES = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the CityWheels help desk agent.")
    parser.add_argument("--runs", type=int, default=1, help="how many times to ask each question (3 shows flakiness)")
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
    """Produce one raw record: status is 'pass', 'fail' or 'infra_error'. Tool calls are kept in full."""
    result, error = ask_with_retries(case, model, tools)
    record = {"id": case["id"], "category": case["category"], "run": run, "question": case["question"]}
    if result is None:
        return {**record, "status": "infra_error", "answer": "", "tool_calls": [], "reasons": [error]}
    reasons = check_case(case, result.answer, result.trace)
    tool_calls = [{"name": c.name, "arguments": c.arguments, "result": c.result} for c in result.trace]
    return {
        **record,
        "status": "fail" if reasons else "pass",
        "answer": result.answer,
        "tool_calls": tool_calls,
        "reasons": reasons,
    }


def git_state() -> tuple[str, bool]:
    """Short commit SHA and whether tracked files have uncommitted changes ('unknown', False if git fails)."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False
    return sha.stdout.strip() or "unknown", bool(status.stdout.strip())


def load_triage(path: Path = TRIAGE_FILE) -> dict:
    """question id -> {"label", "comment", "run", "commit"}; a missing file means nothing is triaged."""
    if not path.exists():
        return {}
    triage = json.loads(path.read_text(encoding="utf-8"))
    for case_id, entry in triage.items():
        if entry["label"] not in TRIAGE_LABELS:
            raise ValueError(f"triage '{case_id}': unknown label '{entry['label']}'")
    return triage


def summarize(records: list[dict]) -> dict:
    graded = [r for r in records if r["status"] != "infra_error"]
    return {
        "passed": sum(r["status"] == "pass" for r in graded),
        "graded": len(graded),
        "infra_errors": len(records) - len(graded),
        "total": len(records),
    }


def adjusted_summary(records: list[dict], triage: dict, sha: str) -> dict:
    """Like summarize(), but failed attempts of questions triaged 'check too strict' are left out.

    Only labels written for the current commit count: a label from an older run must not change a newer score.
    """
    def excluded(r: dict) -> bool:
        entry = triage.get(r["id"], {})
        return r["status"] == "fail" and entry.get("label") == "check too strict" and entry.get("commit") == sha

    kept = [r for r in records if not excluded(r)]
    return summarize(kept)


def stability(records: list[dict]) -> dict[str, str]:
    """Per question: 'always pass', 'flaky' or 'always fail' (infra errors are not counted)."""
    result = {}
    for case_id in dict.fromkeys(r["id"] for r in records):
        graded = [r["status"] for r in records if r["id"] == case_id and r["status"] != "infra_error"]
        if not graded:
            result[case_id] = "no graded attempt"
        elif all(status == "pass" for status in graded):
            result[case_id] = "always pass"
        elif all(status == "fail" for status in graded):
            result[case_id] = "always fail"
        else:
            result[case_id] = "flaky"
    return result


def triage_cell(case_id: str, triage: dict, sha: str) -> str:
    entry = triage.get(case_id)
    if entry is None:
        return "untriaged"
    stale = "" if entry.get("commit") == sha else ", STALE"
    where = f"run {entry.get('run', '?')} @ {entry.get('commit', '?')}{stale}"
    return f"{entry['label']} ({where}): {entry['comment']}"


def per_question_rows(records: list[dict], runs: int, triage: dict, sha: str) -> list[str]:
    rows = []
    for case_id, bucket in stability(records).items():
        mine = [r for r in records if r["id"] == case_id]
        passes = sum(r["status"] == "pass" for r in mine)
        errors = sum(r["status"] == "infra_error" for r in mine)
        failed = any(r["status"] == "fail" for r in mine)
        reasons = "; ".join(sorted({x for r in mine if r["status"] == "fail" for x in r["reasons"]})) or "-"
        tools = ", ".join(c["name"] for c in mine[0]["tool_calls"]) or "-"
        note = f" ({errors} infra error)" if errors else ""
        triage_text = triage_cell(case_id, triage, sha) if failed else "-"
        rows.append(
            f"| {case_id} | {mine[0]['category']} | {passes}/{runs}{note} | {bucket} "
            f"| {tools} | {reasons} | {triage_text} |"
        )
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
commit. A label marked STALE belongs to an older commit, is ignored by the adjusted score and must be re-checked."""


def header_lines(model_name: str, runs: int, records: list[dict]) -> list[str]:
    sha, dirty = git_state()
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stats = summarize(records)
    lines = ["# Evaluation results", ""]
    if stats["total"] and stats["infra_errors"] / stats["total"] > INCOMPLETE_SHARE:
        lines += [
            f"**INCOMPLETE RUN: {stats['infra_errors']} of {stats['total']} attempts hit infrastructure "
            "errors. Do not read the score below as a quality result.**",
            "",
        ]
    state = "dirty: uncommitted changes" if dirty else "clean"
    lines += [f"- Commit: {sha} ({state})", f"- Model: {model_name}", f"- Runs per question: {runs}"]
    return lines + [f"- Date: {date}", ""]


def summary_lines(records: list[dict], runs: int, triage: dict, sha: str) -> list[str]:
    stats, adjusted = summarize(records), adjusted_summary(records, triage, sha)
    buckets = list(stability(records).values())
    infra_ids = sorted({r["id"] for r in records if r["status"] == "infra_error"})
    stable_note = " (Stability is not meaningful with 1 run; use --runs 3.)" if runs < 2 else ""
    infra_note = f" (questions: {', '.join(infra_ids)}); excluded from the scores." if infra_ids else "."
    return [
        f"**Raw: passed {stats['passed']} / {stats['graded']} attempts. Adjusted (without failed attempts "
        f"triaged 'check too strict'): {adjusted['passed']} / {adjusted['graded']}.**",
        "Adjusted uses only triage labels written for the current commit; STALE labels are shown for context only.",
        "",
        f"Questions: {buckets.count('always pass')} always pass, {buckets.count('flaky')} flaky, "
        f"{buckets.count('always fail')} always fail.{stable_note}",
        "",
        f"Infra errors: {stats['infra_errors']} of {stats['total']} attempts{infra_note}",
        "",
    ]


def build_report(records: list[dict], model_name: str, runs: int, triage: dict | None = None) -> str:
    triage = load_triage() if triage is None else triage
    sha, _ = git_state()
    lines = header_lines(model_name, runs, records) + summary_lines(records, runs, triage, sha)
    lines += [
        "| Question | Category | Passed | Stability | Tools (first run) | Failure reasons | Triage |",
        "|---|---|---|---|---|---|---|",
        *per_question_rows(records, runs, triage, sha), "",
        "## Failures", "", *failure_sections(records),
        "## How to read this", "", HOW_TO_READ, "",
    ]
    return "\n".join(lines)


def warn_if_overwriting(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            print(f"WARNING: overwriting existing {path}", file=sys.stderr)


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
    warn_if_overwriting(out, out.with_suffix(".json"))
    out.write_text(build_report(records, settings.model, args.runs), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    stats = summarize(records)
    print(f"Passed {stats['passed']} / {stats['graded']} (infra errors: {stats['infra_errors']})")


if __name__ == "__main__":
    main()
