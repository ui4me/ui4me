"""tests/fixtures/markdown_cases.json: expected output of the Python ui.markdown renderer."""
import json
from pathlib import Path

import pytest

from ui4me._ui.components.markdown import render_markdown

CASES = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "markdown_cases.json").read_text())
CASES = CASES["cases"] if isinstance(CASES, dict) else CASES


@pytest.mark.parametrize("case", CASES, ids=[c.get("name", str(i)) for i, c in enumerate(CASES)])
def test_markdown_case(case):
    assert render_markdown(case["input"]) == case["expected"]
