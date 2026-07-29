"""Self-improvement loop for the fleet mesh.

The fleet audits its own code, finds gaps, proposes upgrades, and
executes them (within trust dial). Four stages:

  1. Auditor   — scans codebase for quality gaps (untested paths, stale
                 TODOs, missing error handling, API mismatches).
  2. Proposer  — converts findings into prioritized task proposals.
  3. Executor  — implements proposals (SAFE actions auto-execute;
                 DESTRUCTIVE/IRREVERSIBLE propose only).
  4. Verifier  — runs tests to confirm the fix closed the gap.

Designed to be called from a scheduled task (daily) or on-demand.
"""
from __future__ import annotations

import ast
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from core.mesh.trust_dial import ActionType, TrustDial, TrustLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingCategory(str, Enum):
    UNTESTED = "untested"
    STALE_TODO = "stale_todo"
    MISSING_ERROR_HANDLING = "missing_error_handling"
    API_MISMATCH = "api_mismatch"
    DEAD_CODE = "dead_code"
    MISSING_LOGGING = "missing_logging"


@dataclass
class Finding:
    """A single audit finding."""
    category: FindingCategory
    severity: FindingSeverity
    file_path: str
    line_number: int
    description: str
    suggestion: str
    confidence: float = 1.0  # 0.0–1.0


@dataclass
class Proposal:
    """A proposed improvement derived from a finding."""
    proposal_id: str
    finding: Finding
    action_description: str
    estimated_effort: str  # "trivial" | "small" | "medium" | "large"
    auto_executable: bool  # SAFE trust level → can auto-execute
    executed: bool = False
    verified: bool = False


@dataclass
class AuditReport:
    """Full audit result."""
    timestamp: str
    findings: list[Finding] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# 1. Auditor
# ---------------------------------------------------------------------------

class CodeAuditor:
    """Scans the codebase for quality gaps."""

    def __init__(self, root_dir: str | os.PathLike[str]) -> None:
        self.root_dir = Path(root_dir)
        self._trust_dial = TrustDial()

    def audit(self) -> list[Finding]:
        """Run all audit checks and return findings."""
        findings: list[Finding] = []

        py_files = self._find_python_files()
        for fpath in py_files:
            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(fpath))
            except (SyntaxError, UnicodeDecodeError):
                continue

            rel = str(fpath.relative_to(self.root_dir))
            findings.extend(self._check_stale_todos(source, rel))
            findings.extend(self._check_missing_error_handling(tree, rel))
            findings.extend(self._check_missing_logging(tree, rel))
            findings.extend(self._check_api_mismatches(source, rel))

        return findings

    def _find_python_files(self) -> list[Path]:
        """Find all .py files under root, excluding .venv and __pycache__."""
        results = []
        for root, dirs, files in os.walk(self.root_dir):
            # Skip virtualenvs, caches, hidden dirs.
            dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", ".git", "node_modules"}]
            for f in files:
                if f.endswith(".py"):
                    results.append(Path(root) / f)
        return results

    def _check_stale_todos(self, source: str, rel_path: str) -> list[Finding]:
        """Find TODO/FIXME comments — flag if no linked issue or stale."""
        findings = []
        todo_pattern = re.compile(r"#\s*(TODO|FIXME|XXX|HACK)\s*[:\s]*(.+)", re.IGNORECASE)
        for i, line in enumerate(source.splitlines(), 1):
            m = todo_pattern.search(line)
            if m:
                tag, note = m.group(1).upper(), m.group(2).strip()
                # High severity for FIXME/XXX, medium for TODO.
                severity = FindingSeverity.HIGH if tag in ("FIXME", "XXX") else FindingSeverity.MEDIUM
                findings.append(Finding(
                    category=FindingCategory.STALE_TODO,
                    severity=severity,
                    file_path=rel_path,
                    line_number=i,
                    description=f"{tag}: {note}",
                    suggestion=f"Resolve or ticket: {note}",
                ))
        return findings

    def _check_missing_error_handling(self, tree: ast.AST, rel_path: str) -> list[Finding]:
        """Find bare except clauses or functions with no error handling that call risky operations."""
        findings = []
        for node in ast.walk(tree):
            # Bare except: `except:` with no type.
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(Finding(
                    category=FindingCategory.MISSING_ERROR_HANDLING,
                    severity=FindingSeverity.MEDIUM,
                    file_path=rel_path,
                    line_number=node.lineno,
                    description="Bare 'except:' clause catches SystemExit/KeyboardInterrupt",
                    suggestion="Use 'except Exception:' or a specific exception type",
                ))
        return findings

    def _check_missing_logging(self, tree: ast.AST, rel_path: str) -> list[Finding]:
        """Find public functions that have no logging calls at all."""
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private/single-line functions.
                if node.name.startswith("_") or len(node.body) < 3:
                    continue
                # Check if any call in the function body is a logging call.
                has_logging = False
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        func = child.func
                        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                            if func.value.id == "logger" and func.attr in ("info", "warning", "error", "debug"):
                                has_logging = True
                                break
                if not has_logging:
                    findings.append(Finding(
                        category=FindingCategory.MISSING_LOGGING,
                        severity=FindingSeverity.LOW,
                        file_path=rel_path,
                        line_number=node.lineno,
                        description=f"Public function '{node.name}' has no logging calls",
                        suggestion=f"Add logging to '{node.name}' for observability",
                    ))
        return findings

    def _check_api_mismatches(self, source: str, rel_path: str) -> list[Finding]:
        """Find potential API mismatches like calling methods that don't exist on a class."""
        findings = []
        # Look for patterns like `.publish_sync(`, `.get_leader(`, `.register_node(`
        # which were found to be missing in Phase 6 testing.
        mismatch_patterns = [
            (r"\.publish_sync\(", "Method '.publish_sync()' may not exist (use asyncio.run or helper)"),
            (r"\.get_leader\(", "Method '.get_leader()' may not exist (use 'current_leader' property)"),
            (r"\.register_node\(", "Method '.register_node()' may not exist (use 'elect_leader()')"),
        ]
        for i, line in enumerate(source.splitlines(), 1):
            for pattern, desc in mismatch_patterns:
                if re.search(pattern, line):
                    # Only flag in non-test files (tests may intentionally test wrong APIs).
                    if "/tests/" not in rel_path:
                        findings.append(Finding(
                            category=FindingCategory.API_MISMATCH,
                            severity=FindingSeverity.HIGH,
                            file_path=rel_path,
                            line_number=i,
                            description=desc,
                            suggestion=f"Verify API exists; {desc}",
                        ))
        return findings


# ---------------------------------------------------------------------------
# 2. Proposer
# ---------------------------------------------------------------------------

class ImprovementProposer:
    """Converts findings into actionable proposals."""

    def __init__(self) -> None:
        self._trust_dial = TrustDial()

    def propose(self, findings: list[Finding]) -> list[Proposal]:
        """Generate proposals from findings, prioritized by severity."""
        proposals = []
        for i, finding in enumerate(findings):
            effort = self._estimate_effort(finding)
            auto_exec = finding.severity in (FindingSeverity.LOW, FindingSeverity.MEDIUM)
            proposals.append(Proposal(
                proposal_id=f"prop-{i:04d}",
                finding=finding,
                action_description=f"[{finding.category.value}] {finding.description} → {finding.suggestion}",
                estimated_effort=effort,
                auto_executable=auto_exec,
            ))

        # Sort: HIGH/CRITICAL first, then by confidence descending.
        severity_order = {FindingSeverity.CRITICAL: 0, FindingSeverity.HIGH: 1, FindingSeverity.MEDIUM: 2, FindingSeverity.LOW: 3}
        proposals.sort(key=lambda p: (severity_order.get(p.finding.severity, 9), -p.finding.confidence))
        return proposals

    def _estimate_effort(self, finding: Finding) -> str:
        if finding.category == FindingCategory.STALE_TODO:
            return "trivial"
        if finding.category == FindingCategory.MISSING_ERROR_HANDLING:
            return "small"
        if finding.category == FindingCategory.API_MISMATCH:
            return "medium"
        if finding.category == FindingCategory.DEAD_CODE:
            return "medium"
        return "small"


# ---------------------------------------------------------------------------
# 3. Executor (trust-dial-gated)
# ---------------------------------------------------------------------------

class ImprovementExecutor:
    """Executes proposals within trust dial constraints."""

    def __init__(self) -> None:
        self._trust_dial = TrustDial()

    def execute(self, proposal: Proposal) -> bool:
        """Attempt to execute a proposal. Returns True if executed."""
        # Map category to action type.
        action_type = self._classify(proposal.finding.category)

        if not self._trust_dial.can_execute(action_type):
            logger.info("Proposal %s blocked by trust dial (type=%s)", proposal.proposal_id, action_type.value)
            return False

        # For now, only auto-fix trivial categories.
        if proposal.finding.category == FindingCategory.STALE_TODO:
            # Don't auto-resolve TODOs — they need human judgment.
            return False

        if proposal.finding.category == FindingCategory.MISSING_ERROR_HANDLING:
            return self._fix_bare_except(proposal)

        logger.info("Proposal %s: no auto-fix available", proposal.proposal_id)
        return False

    def _classify(self, category: FindingCategory) -> ActionType:
        if category in (FindingCategory.STALE_TODO, FindingCategory.MISSING_LOGGING):
            return ActionType.SAFE
        if category == FindingCategory.MISSING_ERROR_HANDLING:
            return ActionType.SAFE
        if category == FindingCategory.API_MISMATCH:
            return ActionType.DESTRUCTIVE
        return ActionType.SAFE

    def _fix_bare_except(self, proposal: Proposal) -> bool:
        """Replace 'except:' with 'except Exception:' in the target file."""
        fpath = Path(self._resolve_path(proposal.finding.file_path))
        if not fpath.exists():
            return False
        try:
            source = fpath.read_text(encoding="utf-8")
            original = source
            source = re.sub(r"(\s*)except\s*:", r"\1except Exception:", source)
            if source != original:
                fpath.write_text(source, encoding="utf-8")
                logger.info("Fixed bare except in %s", fpath)
                return True
        except Exception:
            logger.exception("Failed to fix bare except in %s", fpath)
        return False

    def _resolve_path(self, rel_path: str) -> str:
        """Resolve relative path against the project root."""
        # Walk up from this file to find the project root.
        here = Path(__file__).resolve()
        # core/mesh/self_improvement.py → root is two levels up.
        root = here.parent.parent.parent
        return str(root / rel_path)


# ---------------------------------------------------------------------------
# 4. Verifier
# ---------------------------------------------------------------------------

class ImprovementVerifier:
    """Verifies that executed proposals actually fixed the gap."""

    def __init__(self, project_root: str | os.PathLike[str]) -> None:
        self.project_root = Path(project_root)

    def verify(self, proposal: Proposal) -> bool:
        """Run verification for a proposal."""
        if proposal.finding.category == FindingCategory.MISSING_ERROR_HANDLING:
            return self._verify_no_bare_except(proposal)
        # Default: run the test suite and check it still passes.
        return self._run_tests()

    def _verify_no_bare_except(self, proposal: Proposal) -> bool:
        fpath = self.project_root / proposal.finding.file_path
        if not fpath.exists():
            return False
        source = fpath.read_text(encoding="utf-8")
        return "except:" not in source and "except :" not in source

    def _run_tests(self) -> bool:
        """Run pytest and return True if all pass."""
        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "tests/", "-q", "--timeout=30"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=180,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class SelfImprovementLoop:
    """Runs the full audit → propose → execute → verify cycle."""

    def __init__(self, project_root: str | os.PathLike[str]) -> None:
        self.project_root = Path(project_root)
        self.auditor = CodeAuditor(self.project_root)
        self.proposer = ImprovementProposer()
        self.executor = ImprovementExecutor()
        self.verifier = ImprovementVerifier(self.project_root)

    def run(self) -> AuditReport:
        """Run one full self-improvement cycle."""
        logger.info("Self-improvement audit starting...")
        report = AuditReport(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        # Stage 1: Audit.
        report.findings = self.auditor.audit()
        logger.info("Audit complete: %d findings", len(report.findings))

        # Stage 2: Propose.
        report.proposals = self.proposer.propose(report.findings)
        logger.info("Proposals generated: %d", len(report.proposals))

        # Stage 3: Execute (trust-dial-gated).
        for proposal in report.proposals:
            if proposal.auto_executable:
                if self.executor.execute(proposal):
                    proposal.executed = True
                    report.executed.append(proposal.proposal_id)

        # Stage 4: Verify.
        for proposal in report.proposals:
            if proposal.executed:
                if self.verifier.verify(proposal):
                    proposal.verified = True
                    report.verified.append(proposal.proposal_id)

        # Summary.
        report.summary = (
            f"Audit: {len(report.findings)} findings, {len(report.proposals)} proposals, "
            f"{len(report.executed)} executed, {len(report.verified)} verified"
        )
        logger.info("Self-improvement cycle complete: %s", report.summary)
        return report
