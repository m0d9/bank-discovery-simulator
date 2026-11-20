"""Value types shared by every model client."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.llm.roles import Role

# How a JSON reply was requested: through response_format, through the prompt, or not at all.
JsonMode = Literal["schema", "prompt", "none"]


class ChatMessage(BaseModel):
    """One chat message sent to the model."""

    model_config = ConfigDict(frozen=True)

    role: Literal["system", "user", "assistant"]
    content: str


class LLMResult(BaseModel):
    """The text a model call produced, plus the measurements telemetry needs.

    Token counts cover every request the call made (retries included); they are None when the
    server reported no usage. `latency_ms` is the wall time of the whole call.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    model: str
    role: Role
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int
    attempts: int
    json_mode: JsonMode
    cached: bool = False
    json_retried: bool = False
    """`chat_json` only: the first reply was unusable JSON, so the call asked once more.
    `attempts` can't tell this apart from retries after a timeout or a server error."""
