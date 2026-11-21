import pytest
from pydantic import ValidationError

from app.config import Settings
from tests.conftest import TEST_API_KEY, TEST_BASE_URL, TEST_MODEL, SettingsFactory

REQUIRED = {"LLM_BASE_URL": TEST_BASE_URL, "LLM_API_KEY": TEST_API_KEY, "LLM_MODEL": TEST_MODEL}

SESSION_DEFAULTS = {
    "SESSION_TTL_MINUTES": 120,
    "MAX_SESSIONS": 200,
    "MAX_STUDENT_TURNS": 30,
    "MAX_MESSAGE_CHARS": 1000,
    "CLIENT_HISTORY_TURNS": 12,
    "MAX_UNLOCKS_PER_TURN": 2,
}


def test_session_settings_have_the_documented_defaults(settings_factory: SettingsFactory) -> None:
    settings = settings_factory()
    assert {name: getattr(settings, name) for name in SESSION_DEFAULTS} == SESSION_DEFAULTS


@pytest.mark.parametrize("name", list(SESSION_DEFAULTS))
def test_session_settings_must_be_at_least_one(
    settings_factory: SettingsFactory, name: str
) -> None:
    with pytest.raises(ValidationError, match=name):
        settings_factory(**{name: 0})


def test_the_message_interval_defaults_to_one_second_and_cannot_be_negative(
    settings_factory: SettingsFactory,
) -> None:
    # The test settings turn it off (tests/conftest.py), so build without the overrides.
    defaults = Settings(_env_file=None, **REQUIRED)
    assert defaults.MIN_MESSAGE_INTERVAL_S == 1.0
    with pytest.raises(ValidationError, match="MIN_MESSAGE_INTERVAL_S"):
        settings_factory(MIN_MESSAGE_INTERVAL_S=-1)


def test_transcripts_stay_out_of_the_logs_unless_asked_for() -> None:
    assert Settings(_env_file=None, **REQUIRED).LOG_TRANSCRIPTS is False
