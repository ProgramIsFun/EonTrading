"""Lint checks for common code patterns that cause runtime errors."""
import re
import glob


def test_no_pymongo_bool_check():
    """pymongo collections raise NotImplementedError on bool(). Use 'is not None' instead."""
    bad_patterns = []
    for path in glob.glob("src/**/*.py", recursive=True):
        with open(path) as f:
            for i, line in enumerate(f, 1):
                # Match: if self._something_col: or if not self._something_col
                if re.search(r"if\s+(not\s+)?self\.\w*_col[^.]", line) and "is not None" not in line and "is None" not in line:
                    bad_patterns.append(f"{path}:{i}: {line.strip()}")
    assert not bad_patterns, f"Use 'is not None' for pymongo collections:\n" + "\n".join(bad_patterns)
