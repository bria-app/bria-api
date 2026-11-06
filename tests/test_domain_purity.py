"""Test that domain code does not import infrastructure frameworks.

This guard ensures the purity of the domain layer: no file under
``app/modules/*/domain/`` or ``app/shared/domain/`` may import
fastapi, sqlalchemy, pydantic, jose, passlib, or httpx.
"""
from __future__ import annotations


import re
from pathlib import Path

# Banned packages — if any appear in an import statement the test fails
BANNED = {"fastapi", "sqlalchemy", "pydantic", "pydantic_settings", "jose", "passlib", "httpx"}

# Regex that matches ``import <pkg>`` or ``from <pkg>`` at the beginning of a
# line (ignoring leading whitespace and comments).
_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+([\w.]+)"
)

ROOT = Path(__file__).resolve().parent.parent / "app"


def _domain_files() -> list[Path]:
    """Collect all .py files under domain/ directories."""
    files: list[Path] = []
    # shared/domain
    shared_domain = ROOT / "shared" / "domain"
    if shared_domain.exists():
        files.extend(shared_domain.rglob("*.py"))
    # modules/*/domain
    modules_dir = ROOT / "modules"
    if modules_dir.exists():
        for module_dir in modules_dir.iterdir():
            domain_dir = module_dir / "domain"
            if domain_dir.is_dir():
                files.extend(domain_dir.rglob("*.py"))
    return files


def test_domain_purity() -> None:
    violations: list[str] = []
    for path in _domain_files():
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                m = _IMPORT_RE.match(line)
                if m:
                    top_package = m.group(1).split(".")[0]
                    if top_package in BANNED:
                        rel = path.relative_to(ROOT.parent)
                        violations.append(
                            f"{rel}:{lineno} imports '{top_package}': {line.rstrip()}"
                        )
    assert not violations, (
        "Domain purity violation — the following domain files import "
        "infrastructure packages:\n" + "\n".join(violations)
    )
