"""Tests for core/approval_gate.py — action approval workflow."""

import threading

from core.approval_gate import ApprovalDecision, ApprovalGate, ApprovalRequest


class TestApprovalRequest:
    def test_initial_state(self):
        req = ApprovalRequest({"action": "click"}, step_num=1)
        assert req.decision is None
        assert req.modified_action is None
        assert req.resolved is False

    def test_respond_sets_decision(self):
        req = ApprovalRequest({"action": "click"}, step_num=1)
        req.respond(ApprovalDecision.APPROVE)
        assert req.decision == ApprovalDecision.APPROVE
        assert req.resolved is True

    def test_respond_with_modified_action(self):
        req = ApprovalRequest({"action": "click"}, step_num=1)
        modified = {"action": "click", "x": 200}
        req.respond(ApprovalDecision.MODIFY, modified)
        assert req.modified_action == modified

    def test_wait_blocks_until_respond(self):
        req = ApprovalRequest({"action": "click"}, step_num=1)

        def respond_later():
            import time

            time.sleep(0.05)
            req.respond(ApprovalDecision.APPROVE)

        t = threading.Thread(target=respond_later, daemon=True)
        t.start()
        result = req.wait(timeout=2)
        assert result is True
        assert req.decision == ApprovalDecision.APPROVE

    def test_wait_timeout(self):
        req = ApprovalRequest({"action": "click"}, step_num=1)
        result = req.wait(timeout=0.05)
        assert result is False


class TestApprovalGate:
    def test_disabled_auto_approves(self):
        gate = ApprovalGate(enabled=False)
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.APPROVE
        assert action == {"action": "click"}

    def test_safe_actions_auto_approved(self):
        gate = ApprovalGate(enabled=True)
        for safe in ["screenshot", "wait", "read_text", "list_controls"]:
            decision, action = gate.evaluate({"action": safe}, step_num=1)
            assert decision == ApprovalDecision.APPROVE

    def test_risky_action_blocks_for_approval(self):
        gate = ApprovalGate(enabled=True)

        def auto_approve():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.APPROVE)

        t = threading.Thread(target=auto_approve, daemon=True)
        t.start()
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.APPROVE

    def test_skip_returns_none_action(self):
        gate = ApprovalGate(enabled=True)

        def skip_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.SKIP)

        t = threading.Thread(target=skip_later, daemon=True)
        t.start()
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.SKIP
        assert action is None

    def test_abort_returns_none_action(self):
        gate = ApprovalGate(enabled=True)

        def abort_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.ABORT)

        t = threading.Thread(target=abort_later, daemon=True)
        t.start()
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.ABORT
        assert action is None

    def test_stats_tracking(self):
        gate = ApprovalGate(enabled=True)
        for safe in ["screenshot", "wait"]:
            gate.evaluate({"action": safe}, step_num=1)
        # Safe actions are auto-approved but not tracked in stats when gate is enabled.
        # Stats only count actions that go through the approval flow.
        stats = gate.get_stats()
        assert isinstance(stats, dict)
        assert "approved" in stats

    def test_reset_stats(self):
        gate = ApprovalGate(enabled=False)
        gate.evaluate({"action": "click"}, step_num=1)
        gate.reset_stats()
        assert gate.get_stats()["approved"] == 0

    def test_callback_called(self):
        gate = ApprovalGate(enabled=True)
        callback_called = threading.Event()
        gate.set_callback(lambda req: callback_called.set())

        def approve_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.APPROVE)

        t = threading.Thread(target=approve_later, daemon=True)
        t.start()
        gate.evaluate({"action": "click"}, step_num=1)
        assert callback_called.is_set()

    def test_modify_returns_modified_action(self):
        gate = ApprovalGate(enabled=True)
        original = {"action": "click", "x": 100}
        modified = {"action": "click", "x": 200}

        def modify_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.MODIFY, modified)

        t = threading.Thread(target=modify_later, daemon=True)
        t.start()
        decision, action = gate.evaluate(original, step_num=1)
        assert decision == ApprovalDecision.MODIFY
        assert action == modified

    def test_timeout_auto_approves(self):
        import unittest.mock

        gate = ApprovalGate(enabled=True)
        with unittest.mock.patch.object(ApprovalRequest, "wait", return_value=False):
            decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.APPROVE
        assert action == {"action": "click"}

    def test_stats_approved_increments(self):
        gate = ApprovalGate(enabled=True)

        def approve_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.APPROVE)

        t = threading.Thread(target=approve_later, daemon=True)
        t.start()
        gate.evaluate({"action": "click"}, step_num=1)
        assert gate.get_stats()["approved"] == 1

    def test_stats_skipped_increments(self):
        gate = ApprovalGate(enabled=True)

        def skip_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.SKIP)

        t = threading.Thread(target=skip_later, daemon=True)
        t.start()
        gate.evaluate({"action": "click"}, step_num=1)
        assert gate.get_stats()["skipped"] == 1

    def test_stats_aborted_increments(self):
        gate = ApprovalGate(enabled=True)

        def abort_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.ABORT)

        t = threading.Thread(target=abort_later, daemon=True)
        t.start()
        gate.evaluate({"action": "click"}, step_num=1)
        assert gate.get_stats()["aborted"] == 1

    def test_stats_modified_increments(self):
        gate = ApprovalGate(enabled=True)

        def modify_later():
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.MODIFY, {"action": "click", "x": 50})

        t = threading.Thread(target=modify_later, daemon=True)
        t.start()
        gate.evaluate({"action": "click"}, step_num=1)
        assert gate.get_stats()["modified"] == 1

    def test_pending_request_property(self):
        gate = ApprovalGate(enabled=True)
        assert gate.pending_request is None
