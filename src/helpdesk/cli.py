"""Command line entry point: python -m helpdesk "question"."""

import argparse
import sys
from collections.abc import Callable

from dotenv import load_dotenv

from helpdesk.agent import run_agent
from helpdesk.config import NOW, load_llm_settings
from helpdesk.data import load_bookings, load_policy_sections
from helpdesk.llm import ChatModel, ModelError, OpenAICompatibleModel
from helpdesk.tools.registry import build_tools

RESULT_PREVIEW_CHARS = 300


def _default_model() -> ChatModel:
    return OpenAICompatibleModel(load_llm_settings())


def main(argv: list[str] | None = None, model_factory: Callable[[], ChatModel] = _default_model) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="helpdesk", description="CityWheels help desk assistant.")
    parser.add_argument("question", nargs="*", help="the customer's question")
    parser.add_argument("--verbose", action="store_true", help="show every tool call")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_request:
        return int(exit_request.code or 0)
    question = " ".join(args.question).strip()
    if not question:
        parser.print_usage(sys.stderr)
        return 2

    try:
        model = model_factory()
    except RuntimeError as error:  # missing environment variables
        print(error, file=sys.stderr)
        return 2

    tools = build_tools(load_bookings(), load_policy_sections(), NOW)
    try:
        result = run_agent(question, model, tools)
    except ModelError as error:
        print(f"The assistant is temporarily unavailable: {error}", file=sys.stderr)
        return 1

    if args.verbose:
        for call in result.trace:
            print(f"[tool] {call.name}({call.arguments}) -> {call.result[:RESULT_PREVIEW_CHARS]}")
    print(result.answer)
    return 0
