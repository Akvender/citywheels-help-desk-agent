"""Command line entry point: python -m helpdesk "question"."""

import argparse
import logging
import sys
import traceback
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


def _fail(message: str, code: int) -> int:
    print(message, file=sys.stderr)
    return code


def main(argv: list[str] | None = None, model_factory: Callable[[], ChatModel] = _default_model) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="helpdesk", description="CityWheels help desk assistant.")
    parser.add_argument("question", nargs="*", help="the customer's question")
    parser.add_argument("--verbose", action="store_true", help="show every tool call")
    args = parser.parse_args(argv)
    # Tool failures are logged with details; they are shown only with --verbose.
    logging.basicConfig(level=logging.ERROR if args.verbose else logging.CRITICAL)
    question = " ".join(args.question).strip()
    if not question:
        parser.error("a question is required")  # prints usage and exits with code 2

    try:
        return _answer(question, args.verbose, model_factory)
    except Exception as error:  # noqa: BLE001 - last resort: a readable message instead of a traceback
        if args.verbose:
            traceback.print_exc()
        return _fail(f"Unexpected error: {type(error).__name__}: {error}", 1)


def _answer(question: str, verbose: bool, model_factory: Callable[[], ChatModel]) -> int:
    try:
        model = model_factory()
    except RuntimeError as error:  # missing environment variables
        return _fail(str(error), 2)
    try:
        tools = build_tools(load_bookings(), load_policy_sections(), NOW)
    except (OSError, ValueError, KeyError) as error:
        return _fail(f"Could not load the shop data: {type(error).__name__}: {error}", 1)
    try:
        result = run_agent(question, model, tools, now=NOW)
    except ModelError as error:
        return _fail(f"The assistant is temporarily unavailable: {error}", 1)

    if verbose:
        for call in result.trace:
            print(f"[tool] {call.name}({call.arguments}) -> {call.result[:RESULT_PREVIEW_CHARS]}", file=sys.stderr)
    if result.stopped != "answer":
        print(f"Warning: the assistant did not finish normally (stopped: {result.stopped}).", file=sys.stderr)
    print(result.answer)
    return 0
