"""Code pattern checks to catch issues that mocks hide."""
import ast
import glob


def _get_all_conditionals_on_col_attrs(path: str) -> list[str]:
    issues = []
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            src_line = source.splitlines()[node.test.lineno - 1] if hasattr(node.test, 'lineno') else ""
            if "_col" in src_line and "is not None" not in src_line and "is None" not in src_line:
                issues.append(f"{path}:{node.test.lineno}: {src_line.strip()}")
    return issues


def test_no_bool_on_mongo_collections():
    """Use 'is not None' for motor/pymongo collection attributes.
    Motor collections also raise on bool() like pymongo's.
    """
    issues = []
    for path in glob.glob("src/**/*.py", recursive=True):
        issues.extend(_get_all_conditionals_on_col_attrs(path))
    assert not issues, "Use 'is not None' for mongo collections:\n" + "\n".join(issues)
