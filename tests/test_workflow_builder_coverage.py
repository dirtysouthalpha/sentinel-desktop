"""Additional coverage tests for workflow_builder.py — edge cases and gap paths."""

from datetime import datetime, timezone

from core.workflow_builder import (
    TEMPLATES,
    StepStatus,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStore,
)

# ---------------------------------------------------------------------------
# WorkflowStep edge cases
# ---------------------------------------------------------------------------


class TestWorkflowStepEdgeCases:
    """WorkflowStep with non-default values."""

    def test_custom_status(self) -> None:
        """Step with DONE status."""
        step = WorkflowStep(status=StepStatus.DONE)
        assert step.status == StepStatus.DONE
        assert step.to_dict()["status"] == "done"

    def test_condition_set(self) -> None:
        """Step with a condition expression."""
        step = WorkflowStep(condition="variables.retry == True")
        assert step.condition == "variables.retry == True"
        assert step.to_dict()["condition"] == "variables.retry == True"

    def test_error_set(self) -> None:
        """Step with an error message."""
        step = WorkflowStep(error="click target not found")
        assert step.error == "click target not found"
        assert step.to_dict()["error"] == "click target not found"

    def test_timestamps(self) -> None:
        """Step with started_at and completed_at."""
        now = datetime.now(timezone.utc)
        step = WorkflowStep(started_at=now, completed_at=now)
        assert step.started_at == now
        assert step.completed_at == now

    def test_on_failure_continue(self) -> None:
        """Step with on_failure='continue' policy."""
        step = WorkflowStep(on_failure="continue")
        assert step.on_failure == "continue"
        assert step.to_dict()["on_failure"] == "continue"

    def test_retry_count(self) -> None:
        """Step with retry_count > 0."""
        step = WorkflowStep(retry_count=1, max_retries=3)
        assert step.retry_count == 1
        assert step.max_retries == 3

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict returns every expected key."""
        step = WorkflowStep(
            name="test",
            action="click",
            params={"x": 1},
            timeout=60,
            max_retries=5,
            condition="True",
            on_failure="skip",
            status=StepStatus.FAILED,
            error="timeout",
        )
        d = step.to_dict()
        assert set(d.keys()) >= {
            "id",
            "name",
            "action",
            "params",
            "timeout",
            "max_retries",
            "condition",
            "on_failure",
            "status",
            "error",
        }


# ---------------------------------------------------------------------------
# Workflow edge cases
# ---------------------------------------------------------------------------


class TestWorkflowEdgeCases:
    """Workflow with non-default configurations."""

    def test_add_step_params_none(self) -> None:
        """add_step with params=None uses empty dict."""
        wf = Workflow()
        step = wf.add_step(action="click", params=None)
        assert step.params == {}

    def test_insert_step_with_name(self) -> None:
        """insert_step uses custom name when provided."""
        wf = Workflow()
        wf.add_step(action="first")
        step = wf.insert_step(0, action="new_first", name="Custom Name")
        assert step.name == "Custom Name"
        assert wf.steps[0].name == "Custom Name"

    def test_to_dict_with_last_run_at(self) -> None:
        """to_dict serializes last_run_at when set."""
        now = datetime.now(timezone.utc)
        wf = Workflow(last_run_at=now)
        d = wf.to_dict()
        assert d["last_run_at"] is not None
        assert d["last_run_at"] == now.isoformat()

    def test_to_dict_with_steps_having_various_statuses(self) -> None:
        """to_dict serializes steps with different statuses."""
        wf = Workflow()
        s1 = wf.add_step(action="a")
        s1.status = StepStatus.DONE
        s2 = wf.add_step(action="b")
        s2.status = StepStatus.FAILED
        s2.error = "timeout"
        d = wf.to_dict()
        assert d["steps"][0]["status"] == "done"
        assert d["steps"][1]["status"] == "failed"
        assert d["steps"][1]["error"] == "timeout"

    def test_variables(self) -> None:
        """Workflow with custom variables."""
        wf = Workflow(variables={"username": "admin", "count": 3})
        d = wf.to_dict()
        assert d["variables"]["username"] == "admin"
        assert d["variables"]["count"] == 3

    def test_current_step_index(self) -> None:
        """Workflow with non-zero current_step_index."""
        wf = Workflow(current_step_index=5)
        assert wf.to_dict()["current_step_index"] == 5

    def test_run_count(self) -> None:
        """Workflow with run_count > 0."""
        wf = Workflow(run_count=10)
        assert wf.to_dict()["run_count"] == 10

    def test_workflow_status_transitions(self) -> None:
        """Workflow can have different statuses."""
        for status in WorkflowStatus:
            wf = Workflow(status=status)
            assert wf.status == status
            assert wf.to_dict()["status"] == status.value


# ---------------------------------------------------------------------------
# WorkflowStore edge cases
# ---------------------------------------------------------------------------


class TestWorkflowStoreEdgeCases:
    """WorkflowStore with edge case operations."""

    def test_create_with_empty_description(self) -> None:
        """Create with default empty description."""
        store = WorkflowStore()
        wf = store.create("Test")
        assert wf.description == ""

    def test_list_all_empty(self) -> None:
        """list_all on empty store returns empty list."""
        store = WorkflowStore()
        assert store.list_all() == []

    def test_duplicate_copies_condition_and_on_failure(self) -> None:
        """duplicate copies condition and on_failure from source steps."""
        store = WorkflowStore()
        original = store.create("Original")
        original.add_step(
            action="click",
            condition="variables.debug",
            on_failure="skip",
            max_retries=5,
        )
        dup = store.duplicate(original.id, new_name="Copy")
        assert dup is not None
        assert dup.steps[0].condition == "variables.debug"
        assert dup.steps[0].on_failure == "skip"
        assert dup.steps[0].max_retries == 5

    def test_multiple_deletes(self) -> None:
        """Deleting same workflow twice returns False on second call."""
        store = WorkflowStore()
        wf = store.create("To Delete")
        assert store.delete(wf.id) is True
        assert store.delete(wf.id) is False

    def test_create_and_get_round_trip(self) -> None:
        """Created workflow is retrievable by ID."""
        store = WorkflowStore()
        wf = store.create("Round Trip")
        retrieved = store.get(wf.id)
        assert retrieved is wf
        assert retrieved.name == "Round Trip"

    def test_list_all_returns_correct_count(self) -> None:
        """list_all returns exactly the number of created workflows."""
        store = WorkflowStore()
        store.create("A")
        store.create("B")
        store.create("C")
        assert len(store.list_all()) == 3


# ---------------------------------------------------------------------------
# Templates validation
# ---------------------------------------------------------------------------


class TestTemplatesDetailed:
    """Deeper template structure validation."""

    def test_expected_template_keys(self) -> None:
        """All expected template keys exist."""
        expected = {"daily_standup", "incident_response", "password_reset", "new_user_onboard"}
        assert expected.issubset(set(TEMPLATES.keys()))

    def test_template_steps_have_name(self) -> None:
        """Every template step has a name field."""
        for key, tmpl in TEMPLATES.items():
            for i, step in enumerate(tmpl["steps"]):
                assert "name" in step, f"Template '{key}' step {i} missing 'name'"

    def test_template_steps_have_params(self) -> None:
        """Every template step has a params field."""
        for key, tmpl in TEMPLATES.items():
            for i, step in enumerate(tmpl["steps"]):
                assert "params" in step, f"Template '{key}' step {i} missing 'params'"

    def test_password_reset_has_six_steps(self) -> None:
        """Password reset template has expected step count."""
        assert len(TEMPLATES["password_reset"]["steps"]) == 6

    def test_daily_standup_has_five_steps(self) -> None:
        """Daily standup template has expected step count."""
        assert len(TEMPLATES["daily_standup"]["steps"]) == 5

    def test_new_user_onboard_has_seven_steps(self) -> None:
        """New user onboarding template has expected step count."""
        assert len(TEMPLATES["new_user_onboard"]["steps"]) == 7

    def test_incident_response_has_four_steps(self) -> None:
        """Incident response template has expected step count."""
        assert len(TEMPLATES["incident_response"]["steps"]) == 4
