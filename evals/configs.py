"""The model setups in `evals/configs.yaml`."""

from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
CONFIGS_FILE = EVALS_DIR / "configs.yaml"
RESULTS_DIR = EVALS_DIR / "results"
TRACES_DIR = RESULTS_DIR / "traces"

ModelTag = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelConfig(_Strict):
    """One setup: a model for each role, and the retries it allows."""

    gate: ModelTag
    client: ModelTag
    coach: ModelTag
    max_retries: int | None = Field(default=None, ge=0)
    """LLM_MAX_RETRIES for the run; None keeps the app's setting."""


class JudgeConfig(_Strict):
    """The judge: one model for every setup, so its verdicts compare across setups."""

    model: ModelTag
    max_tokens: int = Field(gt=0)
    max_retries: int = Field(ge=0)


class EvalConfigs(_Strict):
    """The whole file: the recommended setup, the judge, and the setups by name."""

    recommended: str
    judge: JudgeConfig
    configs: dict[str, ModelConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _recommended_is_defined(self) -> Self:
        if self.recommended not in self.configs:
            raise ValueError(f"the recommended config {self.recommended!r} isn't defined")
        return self


def load_configs(path: Path = CONFIGS_FILE) -> EvalConfigs:
    """Read and validate the setups. Raises ValidationError or yaml.YAMLError."""
    return EvalConfigs.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
