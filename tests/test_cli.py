import json
import logging

import pytest

from fakes import FakeModel, assistant_calling, assistant_saying, tool_call
from helpdesk.cli import main
from helpdesk.config import NOW
from helpdesk.llm import ModelError


def factory_for(model):
    return lambda: model


def test_prints_answer(capsys):
    code = main(["Hi"], model_factory=factory_for(FakeModel([assistant_saying("Hello!")])))
    assert code == 0
    assert "Hello!" in capsys.readouterr().out


def test_verbose_shows_tool_calls_before_answer(capsys):
    call = tool_call("1", "get_booking", '{"booking_id": "CW-1002"}')
    model = FakeModel([assistant_calling(call), assistant_saying("Final answer")])
    main(["--verbose", "Where is CW-1002?"], model_factory=factory_for(model))
    captured = capsys.readouterr()
    assert "[tool] get_booking" in captured.err
    assert "get_booking" not in captured.out
    assert "Final answer" in captured.out


def test_without_verbose_tools_are_hidden(capsys):
    call = tool_call("1", "get_booking", '{"booking_id": "CW-1002"}')
    model = FakeModel([assistant_calling(call), assistant_saying("Final answer")])
    main(["q"], model_factory=factory_for(model))
    captured = capsys.readouterr()
    assert "get_booking" not in captured.out + captured.err


def test_no_question_prints_usage_and_exits_2(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([], model_factory=factory_for(FakeModel([])))
    assert exit_info.value.code == 2
    assert "usage" in capsys.readouterr().err.lower()


def test_unfinished_run_warns_on_stderr_but_exits_0(capsys):
    loop = assistant_calling(tool_call("1", "get_booking", '{"booking_id": "CW-1002"}'))
    code = main(["q"], model_factory=factory_for(FakeModel([loop] * 6)))
    captured = capsys.readouterr()
    assert code == 0
    assert "max_steps" in captured.err
    assert "help@citywheels.example" in captured.out


@pytest.mark.parametrize("error", [OSError("disk"), ValueError("bad json"), KeyError("id")])
def test_data_loading_errors_exit_1_with_readable_message(monkeypatch, capsys, error):
    def failing():
        raise error

    monkeypatch.setattr("helpdesk.cli.load_bookings", failing)
    assert main(["Hi"], model_factory=factory_for(FakeModel([]))) == 1
    assert "Could not load the shop data" in capsys.readouterr().err


class Crashing:
    def complete(self, messages, tools):
        raise RuntimeError("boom")


def test_unexpected_error_exits_1_without_traceback(capsys):
    assert main(["Hi"], model_factory=factory_for(Crashing())) == 1
    err = capsys.readouterr().err
    assert "Unexpected error: RuntimeError: boom" in err
    assert "Traceback" not in err


def test_unexpected_error_shows_traceback_with_verbose(capsys):
    assert main(["--verbose", "Hi"], model_factory=factory_for(Crashing())) == 1
    assert "Traceback" in capsys.readouterr().err


def test_missing_env_exits_2(monkeypatch, capsys):
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("helpdesk.cli.load_dotenv", lambda: None)
    assert main(["Hi"]) == 2
    assert "LLM_BASE_URL" in capsys.readouterr().err


def test_model_error_exits_1_with_friendly_text(capsys):
    class Broken:
        def complete(self, messages, tools):
            raise ModelError("timeout")

    assert main(["Hi"], model_factory=factory_for(Broken())) == 1
    assert "temporarily unavailable: timeout" in capsys.readouterr().err


def test_cli_gives_tools_and_prompt_the_same_now(capsys):
    call = tool_call("1", "calculate_refund", '{"booking_id": "CW-1001"}')
    model = FakeModel([assistant_calling(call), assistant_saying("ok")])

    main(["q"], model_factory=factory_for(model))

    system_prompt = model.calls[0][0]["content"]
    tool_result = json.loads(model.calls[1][-1]["content"])
    assert NOW.isoformat() in system_prompt
    assert tool_result["cancel_at"] == NOW.isoformat()


def test_tool_failure_details_are_logged_only_with_verbose(monkeypatch, capsys):
    def broken(*_args, **_kwargs):
        raise ValueError("secret detail")

    monkeypatch.setattr("helpdesk.tools.registry.get_booking", broken)
    call = tool_call("1", "get_booking", '{"booking_id": "CW-1002"}')

    for verbose, expected in ((False, False), (True, True)):
        # basicConfig does nothing when the root logger already has handlers (pytest adds its own)
        monkeypatch.setattr(logging.root, "handlers", [])
        monkeypatch.setattr(logging.root, "level", logging.WARNING)
        model = FakeModel([assistant_calling(call), assistant_saying("Sorry.")])
        main((["--verbose"] if verbose else []) + ["q"], model_factory=factory_for(model))
        assert ("secret detail" in capsys.readouterr().err) is expected
