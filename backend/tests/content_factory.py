"""Small, valid content for tests to break on purpose, written to a temporary folder.

The data is deliberately tiny: one bank, two products and one client whose hidden facts carry
marker text (`SECRET-...`) that leak tests can search for.
"""

import copy
import os
import time
from pathlib import Path
from typing import Any

import yaml

ALPHA = "alpha-loan"
BETA = "beta-deposit"
CLIENT = "test-client"
SECRET_CASH_GAP = "SECRET-CASH-GAP: two customers pay 90 days late."
SECRET_EXPANSION = "SECRET-EXPANSION: plans a second branch next year."


def bank_data(**overrides: Any) -> dict[str, Any]:
    """A valid `bank.yaml`."""
    data: dict[str, Any] = {
        "name": {"en": "Test Bank", "ar": "بنك الاختبار"},
        "tagline": "Tested first",
        "disclaimer": "Fictional bank for tests.",
        "currency": "QAR",
    }
    data.update(overrides)
    return data


def product_data(product_id: str = ALPHA, **overrides: Any) -> dict[str, Any]:
    """A valid conventional SME loan; pass overrides to change any field."""
    data: dict[str, Any] = {
        "id": product_id,
        "schema_version": 1,
        "name": "Alpha Loan",
        "summary": "A loan for tests.",
        "segments": ["sme"],
        "category": "financing",
        "sharia_compliant": False,
        "interest_based": True,
        "features": ["Fast approval", "Flexible limit"],
        "limitations": ["Variable rate", "Annual review"],
        "eligibility": ["Any business registered in Qatar"],
        "pricing": "Interest of 5% a year (fictional)",
        "client_view": "A business loan that charges interest.",
    }
    data.update(overrides)
    return data


def deposit_data() -> dict[str, Any]:
    """A valid Sharia-compliant deposit (the second product)."""
    return product_data(
        BETA,
        name="Beta Deposit",
        category="deposit",
        segments=["retail", "sme"],
        sharia_compliant=True,
        interest_based=False,
        pricing="Expected profit of 3% a year (fictional)",
        client_view="A savings deposit that pays an expected profit.",
    )


def client_data(client_id: str = CLIENT, **overrides: Any) -> dict[str, Any]:
    """A valid client with two hidden facts and one need."""
    data: dict[str, Any] = {
        "id": client_id,
        "schema_version": 1,
        "segment": "sme",
        "difficulty": "easy",
        "card": {
            "name": {"en": "Test Client", "ar": "عميل الاختبار"},
            "headline": "Owns a small test company",
            "opening_line": "Hello, I have a few minutes.",
        },
        "persona": {
            "age": 40,
            "gender": "female",
            "occupation": "Company owner",
            "nationality": "Qatari",
            "background": "Runs a small company in Doha.",
            "personality": "Calm and polite.",
            "speaking_style": "Short sentences.",
            "financial_knowledge": "medium",
        },
        "open_facts": ["Runs a company in Doha."],
        "hidden_facts": [
            {
                "id": "cash-gap",
                "content": SECRET_CASH_GAP,
                "signal": "Money has been tight.",
                "unlock_when": ["asks how customers pay"],
                "importance": "critical",
                "example_questions": ["How quickly do your customers pay you?"],
            },
            {
                "id": "expansion",
                "content": SECRET_EXPANSION,
                "unlock_when": ["asks about plans"],
                "requires": ["cash-gap"],
                "importance": "important",
                "example_questions": ["What are your plans for the business?"],
            },
        ],
        "needs": [
            {
                "id": "fund-gap",
                "description": "Bridge the gap until customers pay.",
                "evidence_facts": ["cash-gap"],
                "suitable_products": [ALPHA],
                "unsuitable_products": [{"id": BETA, "reason": "A deposit doesn't lend money."}],
            }
        ],
        "coach_notes": {
            "key_questions": ["How do customers pay you?", "What are your plans?"],
            "common_mistakes": ["Pitching a product before asking any questions."],
        },
    }
    data.update(overrides)
    return copy.deepcopy(data)


class ContentDir:
    """A content folder in a temporary directory, named `content` like the real one.

    Every write moves the file's modification time one second past the previous write, so
    change detection never depends on the file system's timestamp resolution.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._clock_ns = time.time_ns()

    def path(self, relative: str) -> Path:
        return self.root / relative

    def write(self, relative: str, data: Any) -> Path:
        """Write `data` as YAML (Arabic kept readable)."""
        return self.write_text(relative, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    def write_text(self, relative: str, text: str) -> Path:
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self._clock_ns += 1_000_000_000
        os.utime(path, ns=(self._clock_ns, self._clock_ns))
        return path

    def remove(self, relative: str) -> None:
        self.path(relative).unlink()


def make_content(tmp_path: Path) -> ContentDir:
    """Write the valid sample content to `tmp_path/content`."""
    content = ContentDir(tmp_path / "content")
    content.write("bank.yaml", bank_data())
    content.write(f"products/{ALPHA}.yaml", product_data())
    content.write(f"products/{BETA}.yaml", deposit_data())
    content.write(f"clients/{CLIENT}.yaml", client_data())
    return content
