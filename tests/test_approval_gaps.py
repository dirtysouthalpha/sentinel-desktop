"""Gap tests for approval_gate.py — callback exception and unknown decision."""

import threading

from core.approval_gate import ApprovalDecision, ApprovalGate, ApprovalRequest


class TestCallbackException:
    """Callback raising exception is caught and logged."""

    def test_callback_exception_does_not_crash(self) -> None:
        gate = ApprovalGate(enabled=True)

        def bad_callback(_req: ApprovalRequest) -> None:
            raise RuntimeError("callback broke")

        gate.set_callback(bad_callback)

        def approve_later() -> None:
            import time

            time.sleep(0.05)
            gate.respond_current(ApprovalDecision.APPROVE)

        t = threading.Thread(target=approve_later, daemon=True)
        t.start()
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.APPROVE


class TestUnknownDecisionFallback:
    """Unknown decision value falls through to APPROVE."""

    def test_unknown_decision_returns_approve(self) -> None:
        gate = ApprovalGate(enabled=True)

        def respond_unknown() -> None:
            import time

            time.sleep(0.05)
            # Directly set an invalid decision on the pending request
            gate._current_request.decision = "bogus"  # type: ignore[assignment]
            gate._current_request._event.set()

        t = threading.Thread(target=respond_unknown, daemon=True)
        t.start()
        decision, action = gate.evaluate({"action": "click"}, step_num=1)
        assert decision == ApprovalDecision.APPROVE
        assert action == {"action": "click"}
