"""Load and validate the program/category mapping that BigQuery applies in its views."""

from __future__ import annotations

import json
import re
from pathlib import Path

# RE2 (used by BigQuery REGEXP_CONTAINS) has no look-around or back-references.
_UNSUPPORTED_RE2 = re.compile(r"\(\?[=!<]|\\[1-9]")


def load_rules(path: Path) -> tuple[list[dict], str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    default_category = data.get("default_category") or "Other"
    rows: list[dict] = []
    seen_priorities: set[int] = set()
    for index, rule in enumerate(data.get("rules") or []):
        pattern = (rule.get("pattern") or "").strip()
        category = (rule.get("category") or "").strip()
        priority = rule.get("priority")
        if not pattern or not category or not isinstance(priority, int):
            raise ValueError(f"Rule #{index + 1} needs integer 'priority', 'category' and 'pattern'")
        if priority in seen_priorities:
            raise ValueError(f"Duplicate priority {priority} in category rules")
        if pattern != pattern.lower():
            raise ValueError(f"Rule {priority}: patterns must be lowercase (text is lowercased before matching)")
        if _UNSUPPORTED_RE2.search(pattern):
            raise ValueError(f"Rule {priority}: look-arounds/back-references are not supported by BigQuery")
        re.compile(pattern)  # basic syntax check
        seen_priorities.add(priority)
        rows.append(
            {
                "priority": priority,
                "category": category,
                "program": (rule.get("program") or None),
                "pattern": pattern,
            }
        )
    rows.sort(key=lambda r: r["priority"])
    return rows, default_category


def classify_text(text: str, rules: list[dict], default_category: str) -> tuple[str, str | None]:
    """Python mirror of the SQL logic; used by tests and the playlist review script."""
    lowered = (text or "").lower()
    for rule in rules:
        if re.search(rule["pattern"], lowered):
            return rule["category"], rule["program"]
    return default_category, None
