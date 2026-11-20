"""scripts/chat.py drives the same InterviewService as the API (CLAUDE.md rule 8)."""

import importlib.util
import io
from pathlib import Path
from types import ModuleType

from app.llm import Role
from app.llm.fake import FakeLLM
from tests.conftest import SettingsFactory
from tests.interview_factory import gate_reply

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "chat.py"


def load_chat() -> ModuleType:
    spec = importlib.util.spec_from_file_location("chat_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_script_runs_the_interview_with_debug_lines(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    script = tmp_path / "noura.txt"
    script.write_text(
        "# generic first\nWhat brings you in today?\n\nHow quickly do your customers pay you?\n",
        encoding="utf-8",
    )
    fake = FakeLLM()
    fake.script(Role.GATE, gate_reply(), gate_reply("late-payments", note="asks how they pay"))
    fake.script(Role.CLIENT, "A friend sent me.", "Some take three months.")
    out = io.StringIO()

    code = load_chat().main(
        ["--client", "noura-al-kuwari", "--debug", "--script", str(script)],
        settings=settings_factory(),
        llm=fake,
        out=out,
    )

    text = out.getvalue()
    assert code == 0
    assert text.startswith("Noura Al-Kuwari: Hello. I don't have long")
    assert "You: What brings you in today?\nNoura Al-Kuwari: A friend sent me." in text
    assert "[debug] eligible: late-payments, sharia-only" in text
    assert "[debug] unlocked this turn: late-payments" in text
    assert "[debug] unlocked so far: late-payments (t3)" in text
    assert "[debug] gate note: asks how they pay" in text
    assert "generic first" not in text  # comments are skipped
    assert len(fake.calls_for(Role.GATE)) == 2


def test_an_unknown_client_lists_the_clients(
    settings_factory: SettingsFactory, tmp_path: Path
) -> None:
    out = io.StringIO()
    script = tmp_path / "empty.txt"
    script.write_text("", encoding="utf-8")

    code = load_chat().main(
        ["--client", "nobody", "--script", str(script)],
        settings=settings_factory(),
        llm=FakeLLM(),
        out=out,
    )

    assert code == 2
    assert "rajesh-menon" in out.getvalue() and "noura-al-kuwari" in out.getvalue()
