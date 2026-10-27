import re

import pytest

from pipeline.categorize import classify_text, load_rules
from pipeline.config import PROJECT_ROOT

RULES, DEFAULT = load_rules(PROJECT_ROOT / "config" / "category_rules.json")


@pytest.mark.parametrize(
    "text, category",
    [
        ("Derana Dream Star Season 12 | Grand Finale", "Dream Star"),
        ("Ada Derana News 7.00 PM | Derana News", "News"),
        ("Derana 360 | With Dilka", "News"),
        ("Sri Lanka vs India | Cricket Highlights", "Sports"),
        ("Derana Little Star Season 13", "Reality shows"),
        ("Teledrama Episode 145 | Sangeethe", "Entertainment"),
        ("Something completely different", DEFAULT),
    ],
)
def test_examples(text, category):
    assert classify_text(text, RULES, DEFAULT)[0] == category


def test_rules_are_bigquery_compatible():
    for rule in RULES:
        assert rule["pattern"] == rule["pattern"].lower()
        assert not re.search(r"\(\?[=!<]", rule["pattern"])


def test_priorities_sorted_and_unique():
    priorities = [r["priority"] for r in RULES]
    assert priorities == sorted(set(priorities))
