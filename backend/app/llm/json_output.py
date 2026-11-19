"""Turn raw model replies into clean text and validated JSON."""

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

_BLOCK = re.compile(r"<(think|thinking)>.*?</\1>", re.IGNORECASE | re.DOTALL)
_CLOSE = re.compile(r"</(?:think|thinking)>", re.IGNORECASE)
_OPEN = re.compile(r"<(?:think|thinking)>", re.IGNORECASE)
_FENCE = re.compile(r"```[\w-]*[ \t]*\n?(.*?)```", re.DOTALL)
_PROBLEM_LIMIT = 300


def strip_reasoning(text: str) -> str:
    """Remove `<think>…</think>` blocks and any leading reasoning, then trim whitespace.

    Also handles a closing tag with no opener (the chat template opened the block, so all
    text before it is reasoning) and an opener with no closing tag (the reply was cut off
    mid-thought, so nothing after it is an answer).
    """
    text = _BLOCK.sub("", text)
    closings = list(_CLOSE.finditer(text))
    if closings:
        text = text[closings[-1].end() :]
    opener = _OPEN.search(text)
    if opener:
        text = text[: opener.start()]
    return text.strip()


def extract_json(text: str) -> dict[str, Any]:
    """Return the first top-level JSON object in `text`, ignoring code fences and prose.

    Raises ValueError if the text holds no JSON object.
    """
    decoder = json.JSONDecoder()
    fenced = [match.group(1) for match in _FENCE.finditer(text)]
    for candidate in [*fenced, text]:
        start = candidate.find("{")
        while start != -1:
            try:
                value, _ = decoder.raw_decode(candidate, start)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(value, dict):
                    return value
            start = candidate.find("{", start + 1)
    raise ValueError("the reply contains no JSON object")


def parse_reply[T: BaseModel](text: str, schema: type[T]) -> T:
    """Extract the JSON object in `text` and validate it against `schema`.

    Raises ValueError with a short, text-free description of the problem.
    """
    data = extract_json(text)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or 'object'}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        message = f"the JSON does not match the schema: {problems}"
        raise ValueError(message[:_PROBLEM_LIMIT]) from None


def schema_instruction(schema: type[BaseModel]) -> str:
    """Return a compact instruction asking for JSON that matches `schema` (prompt mode)."""
    compact = json.dumps(schema.model_json_schema(), separators=(",", ":"), ensure_ascii=False)
    return (
        "Reply with only a JSON object that matches this JSON Schema, "
        f"with no other text and no code fences: {compact}"
    )


def json_retry_instruction(problem: str) -> str:
    """Return the follow-up user message for the single retry after an unusable JSON reply."""
    return f"Your previous reply could not be used ({problem}). Return only valid JSON."
