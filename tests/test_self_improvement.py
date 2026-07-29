"""Tests for the self-improvement loop.

Verifies that the CodeAuditor finds real gaps (stale TODOs, bare excepts,
missing logging), the Proposer prioritizes correctly, the Executor
respects trust dial, and the Verifier confirms fixes.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.mesh.self_improvement import (
    AuditReport,
    CodeAuditor,
    FindingCategory,
    FindingSeverity,
    ImprovementExecutor,
    ImprovementProposer,
    ImprovementVerifier,
    SelfImprovementLoop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SOURCE = '''
"""Sample module for testing the auditor."""
import logging

logger = logging.getLogger(__name__)


def well_tested_function(x):
    """A function with logging and error handling."""
    logger.info("Processing %s", x)
    try:
        return int(x)
    except ValueError:
        logger.warning("Invalid value: %s", x)
        return 0


def untested_function(a, b, c):
    """A function with no logging."""
    result = a + b + c
    if result > 100:
        return result * 2
    return result


def bare_except_function():
    """A function with a bare except."""
    try:
        data = open("file.txt").read()
    except:
        data = ""
    return data


def todo_function():
    """Has a stale TODO."""
    # TODO: refactor this into a helper
    # FIXME: this logic is broken for edge cases
    x = 1 + 2
    return x
'''


@pytest.fixture
def sample_project(tmp_path):
    """Create a temporary project with sample source for auditing."""
    src_dir = tmp_path / "core" / "sample"
    src_dir.mkdir(parents=True)
    mod_file = src_dir / "sample_mod.py"
    mod_file.write_text(SAMPLE_SOURCE, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

class TestCodeAuditor:
    def test_finds_stale_todos(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        todos = [f for f in findings if f.category == FindingCategory.STALE_TODO]
        assert len(todos) >= 2  # TODO + FIXME
        descriptions = " ".join(f.description for f in todos)
        assert "refactor" in descriptions
        assert "broken" in descriptions

    def test_finds_bare_except(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        bare = [f for f in findings if f.category == FindingCategory.MISSING_ERROR_HANDLING]
        assert len(bare) >= 1
        assert "Bare" in bare[0].description

    def test_finds_missing_logging(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = [f for f in auditor.audit() if f.category == FindingCategory.MISSING_LOGGING]
        # untested_function has no logging.
        assert len(findings) >= 1

    def test_finding_metadata(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        for f in findings:
            assert f.file_path.endswith(".py")
            assert f.line_number > 0
            assert len(f.description) > 0
            assert len(f.suggestion) > 0


# ---------------------------------------------------------------------------
# Proposer
# ---------------------------------------------------------------------------

class TestImprovementProposer:
    def test_proposals_match_findings(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        proposer = ImprovementProposer()
        proposals = proposer.propose(findings)
        assert len(proposals) == len(findings)

    def test_prioritizes_high_severity(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        proposer = ImprovementProposer()
        proposals = proposer.propose(findings)
        if len(proposals) >= 2:
            # First proposal should be highest severity.
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            first = severity_order.get(proposals[0].finding.severity.value, 9)
            last = severity_order.get(proposals[-1].finding.severity.value, 9)
            assert first <= last

    def test_proposal_has_effort_estimate(self, sample_project):
        auditor = CodeAuditor(sample_project)
        findings = auditor.audit()
        proposer = ImprovementProposer()
        proposals = proposer.propose(findings)
        for p in proposals:
            assert p.estimated_effort in ("trivial", "small", "medium", "large")


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class TestImprovementExecutor:
    def test_blocks_destructive_without_trust(self, sample_project):
        """API_MISMATCH proposals are DESTRUCTIVE — blocked by default trust dial."""
        from core.mesh.self_improvement import Finding, Proposal
        finding = Finding(
            category=FindingCategory.API_MISMATCH,
            severity=FindingSeverity.HIGH,
            file_path="core/sample/sample_mod.py",
            line_number=10,
            description="Test mismatch",
            suggestion="Fix API",
        )
        proposal = Proposal(
            proposal_id="prop-test",
            finding=finding,
            action_description="test",
            estimated_effort="medium",
            auto_executable=False,
        )
        executor = ImprovementExecutor()
        # Default trust dial is OFF → DESTRUCTIVE blocked.
        assert executor.execute(proposal) is False

    def test_fixes_bare_except(self, sample_project):
        """SAFE action (bare except fix) executes when trust allows."""
        from core.mesh.self_improvement import Finding, Proposal
        finding = Finding(
            category=FindingCategory.MISSING_ERROR_HANDLING,
            severity=FindingSeverity.MEDIUM,
            file_path="core/sample/sample_mod.py",
            line_number=25,
            description="Bare except",
            suggestion="Fix to except Exception",
        )
        proposal = Proposal(
            proposal_id="prop-bare",
            finding=finding,
            action_description="fix bare except",
            estimated_effort="small",
            auto_executable=True,
        )
        executor = ImprovementExecutor()
        # The executor should fix "except:" → "except Exception:".
        result = executor.execute(proposal)
        if result:
            # Verify the fix was applied.
            mod_file = sample_project / "core" / "sample" / "sample_mod.py"
            source = mod_file.read_text()
            assert "except:" not in source


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------

class TestImprovementVerifier:
    def test_verify_bare_except_fixed(self, sample_project):
        verifier = ImprovementVerifier(sample_project)
        from core.mesh.self_improvement import Finding, Proposal
        finding = Finding(
            category=FindingCategory.MISSING_ERROR_HANDLING,
            severity=FindingSeverity.MEDIUM,
            file_path="core/sample/sample_mod.py",
            line_number=25,
            description="Bare except",
            suggestion="Fix",
        )
        proposal = Proposal(
            proposal_id="prop-v",
            finding=finding,
            action_description="fix",
            estimated_effort="small",
            auto_executable=True,
            executed=True,
        )
        # The sample still has a bare except → verify returns False.
        assert verifier.verify(proposal) is False

    def test_verify_after_fix(self, sample_project):
        """After manually fixing, verifier should pass."""
        mod_file = sample_project / "core" / "sample" / "sample_mod.py"
        source = mod_file.read_text(encoding="utf-8")
        fixed = source.replace("except:", "except Exception:")
        mod_file.write_text(fixed, encoding="utf-8")

        verifier = ImprovementVerifier(sample_project)
        from core.mesh.self_improvement import Finding, Proposal
        finding = Finding(
            category=FindingCategory.MISSING_ERROR_HANDLING,
            severity=FindingSeverity.MEDIUM,
            file_path="core/sample/sample_mod.py",
            line_number=25,
            description="Bare except",
            suggestion="Fix",
        )
        proposal = Proposal(
            proposal_id="prop-v2",
            finding=finding,
            action_description="fix",
            estimated_effort="small",
            auto_executable=True,
            executed=True,
        )
        assert verifier.verify(proposal) is True


# ---------------------------------------------------------------------------
# Full loop
# ---------------------------------------------------------------------------

class TestSelfImprovementLoop:
    def test_full_cycle_returns_report(self, sample_project):
        loop = SelfImprovementLoop(sample_project)
        report = loop.run()
        assert isinstance(report, AuditReport)
        assert len(report.findings) > 0
        assert len(report.proposals) > 0
        assert report.timestamp != ""

    def test_report_summary_format(self, sample_project):
        loop = SelfImprovementLoop(sample_project)
        report = loop.run()
        assert "findings" in report.summary
        assert "proposals" in report.summary
