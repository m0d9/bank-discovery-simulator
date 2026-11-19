from app.llm.roles import Role, resolve_model, role_timeout
from tests.conftest import SettingsFactory


def test_every_role_falls_back_to_llm_model(settings_factory: SettingsFactory) -> None:
    settings = settings_factory(LLM_MODEL="base")
    for role in Role:
        assert resolve_model(role, None, settings=settings) == "base"


def test_role_specific_model_wins_over_llm_model(settings_factory: SettingsFactory) -> None:
    settings = settings_factory(LLM_MODEL="base", LLM_MODEL_GATE="small", LLM_MODEL_COACH="big")
    assert resolve_model(Role.GATE, None, settings=settings) == "small"
    assert resolve_model(Role.CLIENT, None, settings=settings) == "base"
    assert resolve_model(Role.COACH, None, settings=settings) == "big"


def test_override_wins_over_everything(settings_factory: SettingsFactory) -> None:
    settings = settings_factory(LLM_MODEL="base", LLM_MODEL_GATE="small")
    assert resolve_model(Role.GATE, "picked", settings=settings) == "picked"


def test_empty_override_is_ignored(settings_factory: SettingsFactory) -> None:
    settings = settings_factory(LLM_MODEL="base")
    assert resolve_model(Role.CLIENT, "", settings=settings) == "base"


def test_role_timeouts_default_to_the_brief(settings_factory: SettingsFactory) -> None:
    settings = settings_factory()
    assert role_timeout(Role.GATE, settings) == 30
    assert role_timeout(Role.CLIENT, settings) == 90
    assert role_timeout(Role.COACH, settings) == 240
