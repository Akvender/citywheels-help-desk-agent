# CityWheels Help Desk Agent

[![tests](https://github.com/Akvender/citywheels-help-desk-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/Akvender/citywheels-help-desk-agent/actions/workflows/tests.yml)

A command-line AI assistant for CityWheels, a fictional bike rental shop. It answers questions from local policies and booking data, using tools for retrieval, booking lookup and refund calculations. It provides information only; it cannot create, change or cancel bookings.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- An API key and access to an OpenAI-compatible chat completions endpoint with tool calling

## Setup

From the repository root:

```bash
uv sync --frozen
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env` for the copy step. Fill in the three LLM settings in `.env` before asking a question. Keep credentials out of version control.

## Usage

```bash
uv run helpdesk "I want to cancel booking CW-1002. How much will I get back?"
uv run helpdesk "What time do you open on Saturday?" --verbose
```

The answer goes to stdout. With `--verbose`, tool names, arguments and result previews go to stderr; each preview is limited to 300 characters. Each invocation starts a separate conversation.

## Configuration

The CLI loads `.env`; existing process environment variables take precedence. All three settings are required.

| Variable | Meaning |
| --- | --- |
| `LLM_BASE_URL` | Base URL of the OpenAI-compatible endpoint |
| `LLM_API_KEY` | API credential for that endpoint |
| `LLM_MODEL` | Provider model identifier |

The example file selects `gemini-3.8-flash`; the committed evaluation used `gemini-3.5-flash-lite`. Set the model explicitly to reproduce that choice.

`src/helpdesk/config.py` fixes the reference time at `2026-06-10T09:00:00+02:00`, as required by [the data specification](data/README.md), and locates the repository's `data/` directory. These are code settings, not environment variables.

## Testing

```bash
uv run pytest -q
uv run pytest --cov=helpdesk --cov-report=term-missing
```

The suite contains 217 tests, runs offline and requires no API key. Measured statement coverage is 99%. GitHub Actions runs the tests on pushes and pull requests.

## Evaluation

Evaluation calls the real provider and requires the LLM configuration above.

```bash
uv run python eval/run_eval.py --runs 3 --model gemini-3.5-flash-lite --out eval/local-results.md
```

The runner writes Markdown and JSON reports; existing files at the output paths are overwritten. See the [committed results](eval/results.md) and [evaluation method and triage](SOLUTION.md#evaluation) for interpretation.

## Project structure

| Path | Purpose |
| --- | --- |
| `src/helpdesk/cli.py` | CLI entry point and error reporting |
| `src/helpdesk/agent.py` | Model and tool loop |
| `src/helpdesk/llm.py` | Chat model interface and OpenAI-compatible adapter |
| `src/helpdesk/config.py` | LLM settings, reference time and data location |
| `src/helpdesk/data.py` | Booking and policy loading |
| `src/helpdesk/prompts.py` | System prompt and staff contact |
| `src/helpdesk/tools/` | Policy search, booking lookup, refund calculation and dispatch |
| `data/` | Supplied bookings and shop policies |
| `tests/` | Offline tests and scripted model doubles |
| `eval/` | Questions, checks, runner, results and manual triage |

See [SOLUTION.md](SOLUTION.md) for architecture, design decisions and limitations.
