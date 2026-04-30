"""Smoke tests to catch issues that mocks hide.

Verifies code doesn't use patterns that break with real library objects
(e.g., pymongo Collection raising on bool()).
"""
import ast
import glob


def _get_all_conditionals_on_col_attrs(path: str) -> list[str]:
    """Find all conditionals that test a _col attribute with bool() instead of 'is not None'."""
    issues = []
    with open(path) as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            src_line = source.splitlines()[node.test.lineno - 1] if hasattr(node.test, 'lineno') else ""
            # Check for bare attribute access on _col fields in conditionals
            if "_col" in src_line and "is not None" not in src_line and "is None" not in src_line:
                issues.append(f"{path}:{node.test.lineno}: {src_line.strip()}")
    return issues


def test_no_bool_on_pymongo_collections():
    """All pymongo collection attributes must use 'is not None', never bare truthiness.

    pymongo 4.12+ raises NotImplementedError on bool(Collection).
    Mocks don't catch this because MagicMock.__bool__ returns True.
    """
    issues = []
    for path in glob.glob("src/**/*.py", recursive=True):
        issues.extend(_get_all_conditionals_on_col_attrs(path))
    assert not issues, "Use 'is not None' for pymongo collections:\n" + "\n".join(issues)
