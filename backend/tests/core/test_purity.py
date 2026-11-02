import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "apps" / "core"
FORBIDDEN = {"django", "rest_framework", "celery", "apps"}


@pytest.mark.parametrize("path", sorted(CORE.rglob("*.py")), ids=lambda p: p.name)
def test_core_imports_no_framework_code(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # Level 1 stays inside apps/core; anything higher reaches into other apps.
            assert node.level <= 1, f"{path.name} imports from outside apps/core"
            if node.level == 0 and node.module:
                names = [node.module]
        for name in names:
            assert name.split(".")[0] not in FORBIDDEN, f"{path.name} imports {name}"
