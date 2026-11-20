import pytest
from pydantic import ValidationError

from tests.conftest import SettingsFactory

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
