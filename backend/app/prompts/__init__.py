"""Prompt templates (`*.md` files with `$placeholders`) and their versions.

Prompt wording lives only in these files. Python fills in the values.
"""

from app.prompts.loader import PROMPT_VERSION, render

__all__ = ["PROMPT_VERSION", "render"]
