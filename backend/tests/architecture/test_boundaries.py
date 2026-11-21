"""Import boundaries, checked by scanning `backend/app` with the AST: only `app/llm` imports
`openai`, and `app/api` imports from the `app.llm` package root, never its submodules."""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
LLM_SUBMODULES = {p.stem for p in (APP / "llm").glob("*.py") if p.stem != "__init__"}


def module_name(rel_path: Path) -> str:
    """`app/llm/client.py` -> `app.llm.client`; `app/llm/__init__.py` -> `app.llm`."""
    parts = rel_path.with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(rel_path: Path, source: str) -> list[tuple[int, str, list[str]]]:
    """Return (line, absolute module, imported names) for every import in a file."""
    package = module_name(rel_path)
    if rel_path.name != "__init__.py":
        package = package.rpartition(".")[0]
    found: list[tuple[int, str, list[str]]] = []
    for node in ast.walk(ast.parse(source, filename=str(rel_path))):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name, []) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".")[: len(package.split(".")) - (node.level - 1)]
                base = ".".join(base_parts)
                module = f"{base}.{node.module}" if node.module else base
            else:
                module = node.module or ""
            found.append((node.lineno, module, [alias.name for alias in node.names]))
    return found


def violations(rel_path: Path, source: str) -> list[str]:
    """Describe every import in a file that breaks the boundaries."""
    problems = []
    in_llm = rel_path.parts[:2] == ("app", "llm")
    in_api = rel_path.parts[:2] == ("app", "api")
    for line, module, names in imports(rel_path, source):
        where = f"{rel_path}:{line}"
        if (module == "openai" or module.startswith("openai.")) and not in_llm:
            problems.append(f"{where} imports {module}; only app/llm may import openai")
        if in_api and module.startswith("app.llm."):
            problems.append(f"{where} imports {module}; app/api must import from app.llm")
        if in_api and module == "app.llm":
            for name in sorted(set(names) & LLM_SUBMODULES):
                problems.append(f"{where} imports submodule app.llm.{name} via the package root")
    return problems


def app_files() -> list[Path]:
    return sorted(p.relative_to(BACKEND) for p in APP.rglob("*.py"))


def test_only_app_llm_imports_openai_and_api_uses_the_llm_package_root() -> None:
    problems = [
        problem
        for rel_path in app_files()
        for problem in violations(rel_path, (BACKEND / rel_path).read_text(encoding="utf-8"))
    ]
    assert problems == []


def test_the_scan_sees_the_real_openai_import() -> None:
    # Guards against a scan that silently checks nothing.
    client = Path("app/llm/client.py")
    modules = {m for _, m, _ in imports(client, (BACKEND / client).read_text(encoding="utf-8"))}
    assert "openai" in modules
    assert Path("app/api/routes_health.py") in app_files()


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("app/api/bad.py", "import openai"),
        ("app/simulation/bad.py", "from openai.types.chat import ChatCompletion"),
        ("app/api/bad.py", "from app.llm.client import OpenAICompatClient"),
        ("app/api/bad.py", "import app.llm.fake"),
        ("app/api/bad.py", "from app.llm import client"),
        ("app/api/bad.py", "from ..llm.errors import LLMError"),
    ],
)
def test_the_checker_flags_forbidden_imports(path: str, source: str) -> None:
    assert violations(Path(path), source)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("app/llm/client.py", "import openai\nfrom openai import AsyncOpenAI"),
        ("app/api/ok.py", "from app.llm import LLMClient, Role, llm_dep"),
        ("app/api/ok.py", "from ..llm import Role"),
        ("app/api/ok.py", "import app.llm"),
        ("app/coaching/ok.py", "from app.llm.fake import FakeLLM"),
    ],
)
def test_the_checker_allows_permitted_imports(path: str, source: str) -> None:
    assert violations(Path(path), source) == []
