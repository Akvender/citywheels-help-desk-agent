# CityWheels Help Desk Agent

[![tests](https://github.com/Akvender/citywheels-help-desk-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Akvender/citywheels-help-desk-agent/actions/workflows/tests.yml)

A command-line AI agent that answers customer questions for CityWheels, a made-up bike rental shop. It uses only the shop's own policies and booking data. The model chooses the tools, and Python code computes every amount.

## Quick start

```bash
uv sync --frozen
cp .env.example .env   # add your own LLM_API_KEY (Gemini free tier works)
uv run helpdesk "I want to cancel booking CW-1002. How much will I get back?" --verbose
uv run pytest          # offline, no key needed
uv run python eval/run_eval.py --runs 3 --model gemini-3.5-flash-lite
```

`SOLUTION.md` explains how the agent works, the decisions behind it, the evaluation results and the limitations.

## Layout

| Path | What it holds |
| --- | --- |
| `src/helpdesk/agent.py` | the tool-calling loop |
| `src/helpdesk/llm.py` | OpenAI-compatible model adapter |
| `src/helpdesk/prompts.py` | system prompt |
| `src/helpdesk/cli.py` | command-line entry point |
| `src/helpdesk/tools/` | `search_policies`, `get_booking`, `calculate_refund`, and the dispatcher |
| `data/` | the shop's policies and bookings (given, unchanged) |
| `tests/` | unit tests and agent-loop tests with a fake model |
| `eval/` | evaluation questions, checks, runner and results |
