from fakes import FakeModel, assistant_calling, assistant_saying, tool_call
from helpdesk.cli import main
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
    out = capsys.readouterr().out
    assert "get_booking" in out
    assert out.index("get_booking") < out.index("Final answer")


def test_without_verbose_tools_are_hidden(capsys):
    call = tool_call("1", "get_booking", '{"booking_id": "CW-1002"}')
    model = FakeModel([assistant_calling(call), assistant_saying("Final answer")])
    main(["q"], model_factory=factory_for(model))
    assert "get_booking" not in capsys.readouterr().out


def test_no_question_prints_usage_and_exits_2(capsys):
    assert main([], model_factory=factory_for(FakeModel([]))) == 2
    assert "usage" in capsys.readouterr().err.lower()


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
