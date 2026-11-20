"""The coach's report: the JSON the coach model writes, and the checked version the API shows."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

CoachText = Annotated[str, StringConstraints(strip_whitespace=True)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class WentWell(_Frozen):
    """Something the student did well, and the student turns that show it."""

    point: CoachText
    evidence_turns: list[int]


class MissedPoint(_Frozen):
    """Something the student missed: a need, a product, or a moment in the interview."""

    point: CoachText
    need_id: str | None
    product_id: str | None
    evidence_turns: list[int]
    better_question: CoachText | None


class Improvement(_Frozen):
    """A habit for the next interview, with an example question or phrase."""

    tip: CoachText
    example: CoachText | None


class CoachReport(_Frozen):
    """The coach's three sections, plus feedback on the student's written summary."""

    went_well: list[WentWell]
    missed: list[MissedPoint]
    how_to_improve: list[Improvement]
    summary_feedback: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
