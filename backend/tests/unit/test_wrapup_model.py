from typing import Any

import pytest
from pydantic import ValidationError

from app.simulation.models import WrapUp

SUMMARY = "She is paid late and needs Sharia-compliant financing."


def rec(product_id: str = "alpha-loan", reason: str = "Bridges the gap.") -> dict[str, str]:
    return {"product_id": product_id, "reason": reason}


def test_a_valid_wrapup_is_trimmed() -> None:
    wrapup = WrapUp.model_validate(
        {"needs_summary": f"  {SUMMARY}  ", "recommendations": [rec(reason="  Bridges the gap. ")]}
    )
    assert wrapup.needs_summary == SUMMARY
    assert wrapup.recommendations[0].reason == "Bridges the gap."


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        ({"needs_summary": "Too short.", "recommendations": [rec()]}, "at least 30 characters"),
        ({"needs_summary": "x" * 2001, "recommendations": [rec()]}, "at most 2000 characters"),
        ({"needs_summary": SUMMARY, "recommendations": []}, "at least 1 item"),
        (
            {"needs_summary": SUMMARY, "recommendations": [rec(p) for p in "abcd"]},
            "at most 3 items",
        ),
        (
            {"needs_summary": SUMMARY, "recommendations": [rec(), rec()]},
            "each product can be recommended only once",
        ),
        ({"needs_summary": SUMMARY, "recommendations": [rec(reason="ok")]}, "at least 5"),
        ({"needs_summary": SUMMARY, "recommendations": [rec(reason="x" * 501)]}, "at most 500"),
    ],
)
def test_invalid_wrapups_are_rejected(data: dict[str, Any], problem: str) -> None:
    with pytest.raises(ValidationError, match=problem):
        WrapUp.model_validate(data)
