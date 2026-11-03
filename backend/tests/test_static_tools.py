"""Tests for the static analysis tool runners.

Every test that would normally call a subprocess either mocks the tool as
absent (via ``shutil.which`` → ``None``) or as present (via a fake subprocess
result). No real static tool is invoked, so the suite runs without Ruff,
Bandit, ESLint, or cppcheck being installed.

Labeling: every finding produced by a static tool must carry
``source = FindingSource.STATIC_ANALYSIS``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.agents.static_tools import (
    run_bandit,
    run_eslint,
    run_ruff,
    run_static_analysis,
    run_cppcheck,
)
from app.llm.schemas import FindingSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ruff_json(code_id: str, message: str, row: int = 1, end_row: int = 1) -> str:
    return json.dumps(
        [
            {
                "code": code_id,
                "message": message,
                "location": {"row": row, "column": 1},
                "end_location": {"row": end_row, "column": 10},
                "filename": "tmp.py",
                "url": f"https://docs.astral.sh/ruff/rules/{code_id.lower()}/",
            }
        ]
    )


def _bandit_json(
    test_id: str = "B106",
    test_name: str = "hardcoded_password_funcarg",
    issue_text: str = "Possible hardcoded password",
    severity: str = "MEDIUM",
    line: int = 3,
) -> str:
    return json.dumps(
        {
            "results": [
                {
                    "test_id": test_id,
                    "test_name": test_name,
                    "issue_text": issue_text,
                    "issue_severity": severity,
                    "issue_confidence": "HIGH",
                    "line_number": line,
                    "line_range": [line],
                }
            ],
            "metrics": {},
        }
    )


def _eslint_json(rule_id: str, message: str, line: int = 1, severity: int = 2) -> str:
    return json.dumps(
        [
            {
                "filePath": "/tmp/x.js",
                "messages": [
                    {
                        "ruleId": rule_id,
                        "message": message,
                        "severity": severity,
                        "line": line,
                        "column": 1,
                        "endLine": line,
                        "endColumn": 20,
                    }
                ],
                "errorCount": 1,
                "warningCount": 0,
            }
        ]
    )


def _cppcheck_xml(error_id: str, msg: str, sev: str = "error", line: int = 5) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<results version="2">\n'
        '  <cppcheck version="2.13"/>\n'
        f'  <error id="{error_id}" severity="{sev}" msg="{msg}" verbose="{msg}">\n'
        f'    <location file="tmp.cpp" line="{line}" column="1"/>\n'
        "  </error>\n"
        "</results>\n"
    )


# ---------------------------------------------------------------------------
# Ruff
# ---------------------------------------------------------------------------


class TestRunRuff:
    def test_returns_empty_when_ruff_not_installed(self) -> None:
        with patch("app.agents.static_tools.shutil.which", return_value=None):
            findings = run_ruff("x = 1\n", filename="a.py")
        assert findings == []

    def test_returns_empty_when_ruff_produces_no_output(self) -> None:
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/ruff"),
            patch(
                "app.agents.static_tools._run_tool",
                return_value=("", "", 0),
            ),
        ):
            findings = run_ruff("x = 1\n", filename="a.py")
        assert findings == []

    def test_parses_valid_ruff_output(self) -> None:
        stdout = _ruff_json("F401", "module imported but unused", row=1, end_row=1)
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/ruff"),
            patch(
                "app.agents.static_tools._run_tool",
                return_value=(stdout, "", 1),
            ),
        ):
            findings = run_ruff("import os\n", filename="a.py")
        assert len(findings) == 1
        f = findings[0]
        assert "F401" in f["title"]
        assert f["source"] == FindingSource.STATIC_ANALYSIS
        assert f["start_line"] == 1
        assert f["end_line"] == 1
        assert f["confidence"] == pytest.approx(0.95)

    def test_finding_source_is_static_analysis(self) -> None:
        stdout = _ruff_json("E501", "line too long", row=2, end_row=2)
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/ruff"),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 1)),
        ):
            findings = run_ruff("x = " + "a" * 100 + "\n", filename="a.py")
        assert all(f["source"] == FindingSource.STATIC_ANALYSIS for f in findings)

    def test_handles_malformed_json_gracefully(self) -> None:
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/ruff"),
            patch("app.agents.static_tools._run_tool", return_value=("not json", "", 1)),
        ):
            findings = run_ruff("x = 1\n")
        assert findings == []


# ---------------------------------------------------------------------------
# Bandit
# ---------------------------------------------------------------------------


class TestRunBandit:
    def test_returns_empty_when_bandit_not_installed(self) -> None:
        with patch("app.agents.static_tools.shutil.which", return_value=None):
            findings = run_bandit("x = 1\n", filename="a.py")
        assert findings == []

    def test_parses_valid_bandit_output(self) -> None:
        stdout = _bandit_json(
            test_id="B106",
            test_name="hardcoded_password_funcarg",
            issue_text="Possible hardcoded password",
            severity="MEDIUM",
            line=3,
        )
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/bandit"),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 1)),
        ):
            findings = run_bandit('connect(password="admin")\n', filename="db.py")
        assert len(findings) == 1
        f = findings[0]
        assert "B106" in f["title"]
        assert f["source"] == FindingSource.STATIC_ANALYSIS
        assert f["category"] == "security"
        assert f["start_line"] == 3

    def test_high_severity_maps_correctly(self) -> None:
        stdout = _bandit_json(severity="HIGH")
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/bandit"),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 1)),
        ):
            findings = run_bandit("x = eval(input())\n", filename="a.py")
        assert findings[0]["severity"] == "High"

    def test_handles_malformed_json_gracefully(self) -> None:
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/bandit"),
            patch("app.agents.static_tools._run_tool", return_value=("garbage", "", 1)),
        ):
            findings = run_bandit("x = 1\n")
        assert findings == []

    def test_empty_results_key_returns_no_findings(self) -> None:
        stdout = json.dumps({"results": [], "metrics": {}})
        with (
            patch("app.agents.static_tools.shutil.which", return_value="/usr/bin/bandit"),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 0)),
        ):
            findings = run_bandit("x = 1\n")
        assert findings == []


# ---------------------------------------------------------------------------
# ESLint
# ---------------------------------------------------------------------------


class TestRunEslint:
    def test_returns_empty_when_eslint_not_installed(self) -> None:
        with patch("app.agents.static_tools.shutil.which", return_value=None):
            findings = run_eslint("var x = 1;\n", filename="a.js")
        assert findings == []

    def test_parses_valid_eslint_output(self) -> None:
        stdout = _eslint_json("no-undef", "'x' is not defined", line=1, severity=2)
        with (
            patch(
                "app.agents.static_tools.shutil.which",
                return_value="/usr/local/bin/eslint",
            ),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 1)),
        ):
            findings = run_eslint("console.log(x);\n", filename="a.js")
        assert len(findings) == 1
        f = findings[0]
        assert "no-undef" in f["title"]
        assert f["source"] == FindingSource.STATIC_ANALYSIS
        assert f["severity"] == "High"  # severity=2 → error → High

    def test_warning_maps_to_medium(self) -> None:
        stdout = _eslint_json("no-unused-vars", "'y' defined but never used", severity=1)
        with (
            patch(
                "app.agents.static_tools.shutil.which",
                return_value="/usr/local/bin/eslint",
            ),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 0)),
        ):
            findings = run_eslint("var y = 2;\n", filename="b.js")
        assert findings[0]["severity"] == "Medium"

    def test_handles_empty_messages(self) -> None:
        stdout = json.dumps([{"filePath": "/tmp/x.js", "messages": [], "errorCount": 0}])
        with (
            patch(
                "app.agents.static_tools.shutil.which",
                return_value="/usr/local/bin/eslint",
            ),
            patch("app.agents.static_tools._run_tool", return_value=(stdout, "", 0)),
        ):
            findings = run_eslint("var x = 1;\n")
        assert findings == []


# ---------------------------------------------------------------------------
# cppcheck
# ---------------------------------------------------------------------------


class TestRunCppcheck:
    def test_returns_empty_when_cppcheck_not_installed(self) -> None:
        with patch("app.agents.static_tools.shutil.which", return_value=None):
            findings = run_cppcheck("int x = 0;\n", filename="a.cpp")
        assert findings == []

    def test_parses_valid_cppcheck_xml(self) -> None:
        xml = _cppcheck_xml("nullPointer", "Null pointer dereference", sev="error", line=5)
        with (
            patch(
                "app.agents.static_tools.shutil.which",
                return_value="/usr/bin/cppcheck",
            ),
            patch("app.agents.static_tools._run_tool", return_value=("", xml, 0)),
        ):
            findings = run_cppcheck("int *p = 0; *p = 1;\n", filename="a.cpp")
        assert len(findings) == 1
        f = findings[0]
        assert "nullPointer" in f["title"]
        assert f["source"] == FindingSource.STATIC_ANALYSIS
        assert f["start_line"] == 5

    def test_handles_malformed_xml(self) -> None:
        with (
            patch(
                "app.agents.static_tools.shutil.which",
                return_value="/usr/bin/cppcheck",
            ),
            patch("app.agents.static_tools._run_tool", return_value=("", "not xml", 0)),
        ):
            findings = run_cppcheck("int x;\n")
        assert findings == []


# ---------------------------------------------------------------------------
# run_static_analysis dispatch
# ---------------------------------------------------------------------------


class TestRunStaticAnalysisDispatch:
    def test_dispatches_to_ruff_and_bandit_for_python(self) -> None:
        with (
            patch("app.agents.static_tools.run_ruff", return_value=[{"id": "ruff-f401"}]) as mock_ruff,
            patch("app.agents.static_tools.run_bandit", return_value=[{"id": "bandit-b106"}]) as mock_bandit,
        ):
            findings = run_static_analysis("x = 1\n", "python", "a.py")
        mock_ruff.assert_called_once()
        mock_bandit.assert_called_once()
        assert len(findings) == 2

    def test_dispatches_to_eslint_for_javascript(self) -> None:
        with patch("app.agents.static_tools.run_eslint", return_value=[{"id": "eslint-no-undef"}]) as mock_eslint:
            findings = run_static_analysis("var x;\n", "javascript", "a.js")
        mock_eslint.assert_called_once()
        assert len(findings) == 1

    def test_dispatches_to_eslint_for_typescript(self) -> None:
        with patch("app.agents.static_tools.run_eslint", return_value=[]) as mock_eslint:
            run_static_analysis("const x: number = 1;\n", "typescript", "a.ts")
        mock_eslint.assert_called_once()

    def test_dispatches_to_cppcheck_for_cpp(self) -> None:
        with patch("app.agents.static_tools.run_cppcheck", return_value=[]) as mock_cpp:
            run_static_analysis("int x;\n", "cpp", "a.cpp")
        mock_cpp.assert_called_once()

    def test_returns_empty_for_unknown_language(self) -> None:
        findings = run_static_analysis("x = 1\n", "cobol", "a.cbl")
        assert findings == []

    def test_never_raises_even_if_tool_raises(self) -> None:
        with patch("app.agents.static_tools.run_ruff", side_effect=RuntimeError("boom")):
            with patch("app.agents.static_tools.run_bandit", return_value=[]):
                findings = run_static_analysis("x = 1\n", "python")
        # Should return empty (or bandit findings); must not propagate exception
        assert isinstance(findings, list)
