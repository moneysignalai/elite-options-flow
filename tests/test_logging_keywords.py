import re
from pathlib import Path


def test_no_structlog_event_keyword_usage():
    repo_root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"\.(info|debug|warning|error|exception|critical)\(\s*event\s*=")
    violations: list[str] = []

    for path in repo_root.rglob("*.py"):
        # Skip common virtual environment directories just in case
        if any(part in {"venv", ".venv", "env"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            violations.append(f"{path.relative_to(repo_root)}:{line}")

    assert not violations, "Logger calls must pass event names positionally: " + ", ".join(violations)
