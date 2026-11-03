"""Static analysis tool runners.

This module runs deterministic static-analysis tools against submitted code and
converts their output to :class:`~app.llm.schemas.Finding` dicts.

Key design decisions
--------------------
* The submitted code is written to a **temporary file** that is deleted
  immediately after the tool exits. Nothing is imported or executed.
* If a tool is not installed (``which`` / ``shutil.which`` returns ``None``)
  the runner returns an empty list and logs an info message. It never lies and
  claims a tool ran when it did not.
* Tool output is parsed line-by-line; lines that don't match the expected
  format are skipped silently.
* Every finding produced here carries ``source = FindingSource.STATIC_ANALYSIS``
  because a real, deterministic tool emitted it.
* Timeouts are enforced per tool (default 30 s). If the process times out the
  runner returns an empty list and logs a warning.

Supported tools
---------------
Python
  * **Ruff** (``ruff check --output-format=json``)
  * **Bandit** (``bandit -f json``)
JavaScript / TypeScript
  * **ESLint** (``eslint --format=json``)
C++ (cpp, c)
  * **cppcheck** (``cppcheck --output-format=xml``) when installed, else skipped.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from app.llm.schemas import Finding, FindingSource, Severity

logger = logging.getLogger(__name__)

# Per-tool subprocess timeout (seconds)
_TOOL_TIMEOUT: float = float(os.getenv("STATIC_TOOL_TIMEOUT", "30"))

# Maximum number of tool findings returned per run (prevents flooding)
_MAX_FINDINGS: int = 50

# Map Ruff / Bandit / ESLint severities to our Severity enum
_RUFF_SEVERITY: dict[str, Severity] = {
    "E": Severity.MEDIUM,   # pycodestyle errors
    "W": Severity.LOW,      # pycodestyle warnings
    "F": Severity.HIGH,     # pyflakes
    "B": Severity.HIGH,     # flake8-bugbear
    "S": Severity.HIGH,     # bandit-like rules in ruff
    "C": Severity.MEDIUM,
    "N": Severity.LOW,
    "D": Severity.LOW,
}

_BANDIT_SEVERITY: dict[str, Severity] = {
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
}

_ESLINT_SEVERITY: dict[int, Severity] = {
    2: Severity.HIGH,   # error
    1: Severity.MEDIUM, # warning
}

_CPPCHECK_SEVERITY: dict[str, Severity] = {
    "error": Severity.HIGH,
    "warning": Severity.MEDIUM,
    "style": Severity.LOW,
    "performance": Severity.MEDIUM,
    "portability": Severity.LOW,
    "information": Severity.INFO,
}

# Language → file extension for temp files
_LANG_EXT: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "cpp": ".cpp",
    "c": ".c",
}


def _make_tempfile(code: str, language: str) -> Path:
    """Write *code* to a secure temporary file and return its path."""
    suffix = _LANG_EXT.get(language.lower(), ".txt")
    fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="codeguard_")
    try:
        os.write(fd, code.encode("utf-8", errors="replace"))
    finally:
        os.close(fd)
    return Path(tmp_path)


def _run_tool(
    cmd: list[str],
    *,
    cwd: str | None = None,
    timeout: float = _TOOL_TIMEOUT,
) -> tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, returncode).

    Returns empty strings and returncode=-1 on timeout or OS error.
    Never raises.
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        logger.warning("Static tool timed out after %ss: %s", timeout, cmd[0])
        return "", "", -1
    except FileNotFoundError:
        # Tool not installed; handled by the caller via shutil.which
        return "", "", -1
    except OSError as exc:
        logger.warning("Static tool OS error (%s): %s", cmd[0], exc)
        return "", "", -1


# ---------------------------------------------------------------------------
# Ruff
# ---------------------------------------------------------------------------

def run_ruff(code: str, filename: str | None = None) -> list[dict[str, Any]]:
    """Run Ruff on *code* and return a list of finding dicts.

    Returns an empty list if Ruff is not installed or finds nothing.
    """
    if not shutil.which("ruff"):
        logger.info("Ruff is not installed; skipping Python static analysis.")
        return []

    tmp = _make_tempfile(code, "python")
    try:
        stdout, stderr, rc = _run_tool(
            ["ruff", "check", "--output-format=json", str(tmp)]
        )
        if not stdout.strip():
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Ruff returned non-JSON output; skipping.")
            return []

        findings: list[dict[str, Any]] = []
        display_name = filename or "submitted_code"

        for item in data[:_MAX_FINDINGS]:
            code_id: str = item.get("code") or "RUFF"
            message: str = item.get("message") or "Ruff issue"
            loc: dict = item.get("location") or {}
            start_line: int = max(1, int(loc.get("row", 1)))
            end_loc: dict = item.get("end_location") or {}
            end_line: int = max(start_line, int(end_loc.get("row", start_line)))

            prefix = code_id[:1].upper() if code_id else "E"
            severity = _RUFF_SEVERITY.get(prefix, Severity.MEDIUM)

            slug = re.sub(r"[^a-z0-9-]", "-", f"ruff-{code_id}".lower())[:64]
            try:
                f = Finding(
                    id=slug,
                    title=f"[Ruff {code_id}] {message[:120]}",
                    description=message,
                    severity=severity,
                    category="quality",
                    file=display_name,
                    start_line=start_line,
                    end_line=end_line,
                    suggested_fix=f"Fix the Ruff violation {code_id}. See https://docs.astral.sh/ruff/rules/{code_id.lower()}/",
                    confidence=0.95,
                    explanation=(
                        f"Ruff ({code_id}) flagged this line. Ruff is a deterministic "
                        "linter; this is not an AI inference."
                    ),
                    source=FindingSource.STATIC_ANALYSIS,
                )
                findings.append(f.model_dump())
            except Exception:  # noqa: BLE001
                logger.debug("Skipped invalid Ruff finding for %s", code_id)

        return findings
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Bandit
# ---------------------------------------------------------------------------

def run_bandit(code: str, filename: str | None = None) -> list[dict[str, Any]]:
    """Run Bandit on *code* and return a list of finding dicts.

    Returns an empty list if Bandit is not installed or finds nothing.
    """
    if not shutil.which("bandit"):
        logger.info("Bandit is not installed; skipping Python security analysis.")
        return []

    tmp = _make_tempfile(code, "python")
    try:
        stdout, stderr, rc = _run_tool(
            ["bandit", "-f", "json", "-q", str(tmp)]
        )
        if not stdout.strip():
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("Bandit returned non-JSON output; skipping.")
            return []

        results = data.get("results") or []
        findings: list[dict[str, Any]] = []
        display_name = filename or "submitted_code"

        for item in results[:_MAX_FINDINGS]:
            test_id: str = item.get("test_id") or "B000"
            test_name: str = item.get("test_name") or "bandit_check"
            issue_text: str = item.get("issue_text") or "Security issue"
            issue_sev: str = (item.get("issue_severity") or "MEDIUM").upper()
            line_no: int = max(1, int(item.get("line_number") or 1))
            line_range: list = item.get("line_range") or [line_no]
            end_line: int = max(line_no, max(line_range))
            confidence_str: str = (item.get("issue_confidence") or "MEDIUM").upper()
            conf_map = {"HIGH": 0.9, "MEDIUM": 0.7, "LOW": 0.5}
            confidence: float = conf_map.get(confidence_str, 0.7)
            severity = _BANDIT_SEVERITY.get(issue_sev, Severity.MEDIUM)

            slug = re.sub(r"[^a-z0-9-]", "-", f"bandit-{test_id}".lower())[:64]
            try:
                f = Finding(
                    id=slug,
                    title=f"[Bandit {test_id}] {test_name.replace('_', ' ').title()}",
                    description=issue_text,
                    severity=severity,
                    category="security",
                    file=display_name,
                    start_line=line_no,
                    end_line=end_line,
                    suggested_fix=(
                        f"Address the Bandit {test_id} ({test_name}) finding. "
                        "See https://bandit.readthedocs.io/en/latest/plugins/"
                        f"{test_name}.html"
                    ),
                    confidence=confidence,
                    explanation=(
                        f"Bandit ({test_id} — {test_name}) detected this security issue. "
                        "Bandit is a deterministic AST-based security linter; "
                        "this is not an AI inference."
                    ),
                    source=FindingSource.STATIC_ANALYSIS,
                )
                findings.append(f.model_dump())
            except Exception:  # noqa: BLE001
                logger.debug("Skipped invalid Bandit finding for %s", test_id)

        return findings
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# ESLint
# ---------------------------------------------------------------------------

def run_eslint(code: str, filename: str | None = None) -> list[dict[str, Any]]:
    """Run ESLint on *code* and return a list of finding dicts.

    ESLint requires a config file in the project directory. If ESLint is not
    installed or no config is present this returns an empty list. ESLint's
    ``--no-eslintrc`` flag is used so that only built-in rules are enforced
    when no config can be found.

    Returns an empty list if ESLint is not installed or finds nothing.
    """
    eslint_bin = shutil.which("eslint")
    if not eslint_bin:
        logger.info("ESLint is not installed; skipping JavaScript static analysis.")
        return []

    tmp = _make_tempfile(code, "javascript")
    try:
        stdout, stderr, rc = _run_tool(
            [
                eslint_bin,
                "--format=json",
                "--no-eslintrc",
                "--rule", '{"no-undef": "error", "no-unused-vars": "warn"}',
                str(tmp),
            ]
        )
        if not stdout.strip():
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            logger.warning("ESLint returned non-JSON output; skipping.")
            return []

        findings: list[dict[str, Any]] = []
        display_name = filename or "submitted_code"

        for file_result in data:
            messages = file_result.get("messages") or []
            for msg in messages[:_MAX_FINDINGS]:
                rule_id: str = msg.get("ruleId") or "eslint"
                message: str = msg.get("message") or "ESLint issue"
                sev_int: int = int(msg.get("severity") or 1)
                line_no: int = max(1, int(msg.get("line") or 1))
                end_line_no: int = max(line_no, int(msg.get("endLine") or line_no))
                severity = _ESLINT_SEVERITY.get(sev_int, Severity.MEDIUM)

                slug = re.sub(r"[^a-z0-9-]", "-", f"eslint-{rule_id}".lower())[:64]
                try:
                    f = Finding(
                        id=slug,
                        title=f"[ESLint {rule_id}] {message[:120]}",
                        description=message,
                        severity=severity,
                        category="quality",
                        file=display_name,
                        start_line=line_no,
                        end_line=end_line_no,
                        suggested_fix=(
                            f"Fix the ESLint {rule_id} violation. "
                            f"See https://eslint.org/docs/rules/{rule_id}"
                        ),
                        confidence=0.95,
                        explanation=(
                            f"ESLint ({rule_id}) flagged this line. "
                            "This is a deterministic lint rule result."
                        ),
                        source=FindingSource.STATIC_ANALYSIS,
                    )
                    findings.append(f.model_dump())
                except Exception:  # noqa: BLE001
                    logger.debug("Skipped invalid ESLint finding for %s", rule_id)

        return findings
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# cppcheck (C / C++)
# ---------------------------------------------------------------------------

def run_cppcheck(code: str, filename: str | None = None) -> list[dict[str, Any]]:
    """Run cppcheck on *code* and return a list of finding dicts.

    Returns an empty list if cppcheck is not installed or finds nothing.
    The XML output format is used for reliable parsing.
    """
    if not shutil.which("cppcheck"):
        logger.info("cppcheck is not installed; skipping C/C++ static analysis.")
        return []

    lang = "c++" if (filename or "").endswith((".cpp", ".cxx", ".cc")) else "c"
    tmp = _make_tempfile(code, "cpp")
    try:
        stdout, stderr, rc = _run_tool(
            [
                "cppcheck",
                f"--language={lang}",
                "--xml",
                "--enable=all",
                "--suppress=missingIncludeSystem",
                str(tmp),
            ]
        )
        # cppcheck writes XML to stderr
        xml_text = stderr.strip() or stdout.strip()
        if not xml_text:
            return []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("cppcheck returned invalid XML; skipping.")
            return []

        findings: list[dict[str, Any]] = []
        display_name = filename or "submitted_code"

        for error in root.iter("error"):
            error_id: str = error.get("id") or "cppcheck"
            msg: str = error.get("msg") or "cppcheck issue"
            sev_str: str = (error.get("severity") or "warning").lower()
            severity = _CPPCHECK_SEVERITY.get(sev_str, Severity.MEDIUM)

            # Location
            location = error.find("location")
            line_no = 1
            if location is not None:
                try:
                    line_no = max(1, int(location.get("line") or 1))
                except ValueError:
                    line_no = 1

            slug = re.sub(r"[^a-z0-9-]", "-", f"cppcheck-{error_id}".lower())[:64]
            try:
                f = Finding(
                    id=slug,
                    title=f"[cppcheck {error_id}] {msg[:120]}",
                    description=msg,
                    severity=severity,
                    category="bug" if sev_str == "error" else "quality",
                    file=display_name,
                    start_line=line_no,
                    end_line=line_no,
                    suggested_fix=(
                        f"Fix the cppcheck {error_id} finding. "
                        "See https://cppcheck.sourceforge.io/"
                    ),
                    confidence=0.9,
                    explanation=(
                        f"cppcheck ({error_id}) detected this issue. "
                        "cppcheck is a deterministic static analyzer; "
                        "this is not an AI inference."
                    ),
                    source=FindingSource.STATIC_ANALYSIS,
                )
                findings.append(f.model_dump())
            except Exception:  # noqa: BLE001
                logger.debug("Skipped invalid cppcheck finding for %s", error_id)

            if len(findings) >= _MAX_FINDINGS:
                break

        return findings
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Public dispatch function
# ---------------------------------------------------------------------------

def run_static_analysis(
    code: str,
    language: str,
    filename: str | None = None,
) -> list[dict[str, Any]]:
    """Run all applicable static tools for *language* and return combined findings.

    Each finding has ``source = "static_analysis"`` and a ``confidence`` of
    0.9–0.95 because a real tool produced it. Returns an empty list when no
    tool is installed for the given language.

    This function never raises; individual tool failures are logged and produce
    an empty contribution.
    """
    lang = language.strip().lower()
    results: list[dict[str, Any]] = []

    try:
        if lang == "python":
            results.extend(run_ruff(code, filename))
            results.extend(run_bandit(code, filename))
        elif lang in ("javascript", "typescript"):
            results.extend(run_eslint(code, filename))
        elif lang in ("cpp", "c"):
            results.extend(run_cppcheck(code, filename))
        else:
            logger.debug(
                "No static analysis tool configured for language: %s", language
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Static analysis failed for language %s: %s", language, exc
        )

    return results
