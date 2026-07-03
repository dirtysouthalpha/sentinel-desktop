"""Tests for core.workflow_builder — Workflow, WorkflowStep, WorkflowStore."""

from __future__ import annotations

from core.workflow_builder import (
    TEMPLATES,
    StepStatus,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
    WorkflowStore,
    workflow_store,
)

# ─── WorkflowStep ──────────────────────────────────────────────────────────

class TestWorkflowStep:
    """Tests for WorkflowStep dataclass."""

    def test_default_values(self):
        """Step has sensible defaults."""
        step = WorkflowStep()
        assert step.id
        assert step.name == ""
        assert step.action == ""
        assert step.params == {}
        assert step.timeout == 30
        assert step.max_retries == 2
        assert step.condition is None
        assert step.on_failure == "stop"
        assert step.status == StepStatus.PENDING
        assert step.error is None

    def test_to_dict(self):
        """to_dict returns all expected keys."""
        step = WorkflowStep(name="Click OK", action="click", params={"x": 100, "y": 200})
        d = step.to_dict()
        assert d["id"] == step.id
        assert d["name"] == "Click OK"
        assert d["action"] == "click"
        assert d["params"] == {"x": 100, "y": 200}
        assert d["status"] == "pending"
        assert d["error"] is None
        assert "timeout" in d
        assert "max_retries" in d
        assert "condition" in d
        assert "on_failure" in d

    def test_unique_ids(self):
        """Each step gets a unique ID."""
        s1 = WorkflowStep()
        s2 = WorkflowStep()
        assert s1.id != s2.id


# ─── Workflow ─────────────────────────────────────────────────────────────

class TestWorkflow:
    """Tests for Workflow dataclass and methods."""

    def test_default_values(self):
        """Workflow has sensible defaults."""
        wf = Workflow()
        assert wf.id
        assert wf.name == "Untitled Workflow"
        assert wf.description == ""
        assert wf.steps == []
        assert wf.status == WorkflowStatus.DRAFT
        assert wf.variables == {}
        assert wf.current_step_index == 0
        assert wf.run_count == 0
        assert wf.last_run_at is None

    def test_add_step(self):
        """add_step appends a step and updates timestamps."""
        wf = Workflow()
        step = wf.add_step(action="click", name="Click button", params={"text": "OK"})
        assert len(wf.steps) == 1
        assert step.action == "click"
        assert step.name == "Click button"
        assert step.params == {"text": "OK"}

    def test_add_step_default_name(self):
        """add_step uses action as name when name is empty."""
        wf = Workflow()
        step = wf.add_step(action="screenshot")
        assert step.name == "screenshot"

    def test_add_step_with_kwargs(self):
        """add_step forwards extra kwargs to WorkflowStep."""
        wf = Workflow()
        step = wf.add_step(action="click", timeout=60, max_retries=5)
        assert step.timeout == 60
        assert step.max_retries == 5

    def test_insert_step(self):
        """insert_step places a step at the given index."""
        wf = Workflow()
        wf.add_step(action="first")
        wf.add_step(action="third")
        wf.insert_step(1, action="second")
        assert [s.action for s in wf.steps] == ["first", "second", "third"]

    def test_remove_step(self):
        """remove_step removes by ID and returns True."""
        wf = Workflow()
        wf.add_step(action="keep")
        s2 = wf.add_step(action="remove")
        result = wf.remove_step(s2.id)
        assert result is True
        assert len(wf.steps) == 1
        assert wf.steps[0].action == "keep"

    def test_remove_step_not_found(self):
        """remove_step returns False for non-existent ID."""
        wf = Workflow()
        wf.add_step(action="exists")
        result = wf.remove_step("nonexistent-id")
        assert result is False
        assert len(wf.steps) == 1

    def test_reorder_steps(self):
        """reorder_steps reorders steps to match the given ID list."""
        wf = Workflow()
        s1 = wf.add_step(action="a")
        s2 = wf.add_step(action="b")
        s3 = wf.add_step(action="c")
        wf.reorder_steps([s3.id, s1.id, s2.id])
        assert [s.action for s in wf.steps] == ["c", "a", "b"]

    def test_reorder_steps_drops_missing(self):
        """reorder_steps silently drops IDs not in the workflow."""
        wf = Workflow()
        s1 = wf.add_step(action="keep")
        wf.add_step(action="drop")
        wf.reorder_steps([s1.id])
        assert len(wf.steps) == 1
        assert wf.steps[0].action == "keep"

    def test_to_dict(self):
        """to_dict returns all expected keys with serialized steps."""
        wf = Workflow(name="Test WF")
        wf.add_step(action="click", name="Click OK")
        d = wf.to_dict()
        assert d["id"] == wf.id
        assert d["name"] == "Test WF"
        assert d["status"] == "draft"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["action"] == "click"
        assert d["current_step_index"] == 0
        assert d["run_count"] == 0
        assert "created_at" in d
        assert "updated_at" in d
        assert d["last_run_at"] is None


# ─── WorkflowStore ─────────────────────────────────────────────────────────

class TestWorkflowStore:
    """Tests for WorkflowStore CRUD operations."""

    def test_create(self):
        """create returns a new workflow registered in the store."""
        store = WorkflowStore()
        wf = store.create("My WF", "A test workflow")
        assert wf.name == "My WF"
        assert wf.description == "A test workflow"
        assert wf.status == WorkflowStatus.ACTIVE
        assert store.get(wf.id) is wf

    def test_get_not_found(self):
        """get returns None for non-existent ID."""
        store = WorkflowStore()
        assert store.get("nope") is None

    def test_list_all(self):
        """list_all returns all registered workflows."""
        store = WorkflowStore()
        w1 = store.create("WF1")
        w2 = store.create("WF2")
        all_wfs = store.list_all()
        assert len(all_wfs) == 2
        assert w1 in all_wfs
        assert w2 in all_wfs

    def test_delete(self):
        """delete removes a workflow and returns True."""
        store = WorkflowStore()
        wf = store.create("Delete Me")
        result = store.delete(wf.id)
        assert result is True
        assert store.get(wf.id) is None

    def test_delete_not_found(self):
        """delete returns False for non-existent ID."""
        store = WorkflowStore()
        assert store.delete("nope") is False

    def test_duplicate(self):
        """duplicate creates a deep copy with all steps."""
        store = WorkflowStore()
        original = store.create("Original")
        original.add_step(action="click", name="Step 1")
        original.add_step(action="type_text", name="Step 2", params={"text": "hello"})

        dup = store.duplicate(original.id)
        assert dup is not None
        assert dup.name == "Original (Copy)"
        assert len(dup.steps) == 2
        assert dup.steps[0].action == "click"
        assert dup.steps[1].params == {"text": "hello"}
        # Ensure deep copy — step IDs differ
        assert dup.steps[0].id != original.steps[0].id
        # Original unchanged
        assert len(original.steps) == 2

    def test_duplicate_with_custom_name(self):
        """duplicate uses custom name when provided."""
        store = WorkflowStore()
        original = store.create("Original")
        dup = store.duplicate(original.id, new_name="Custom Name")
        assert dup.name == "Custom Name"

    def test_duplicate_not_found(self):
        """duplicate returns None for non-existent ID."""
        store = WorkflowStore()
        assert store.duplicate("nope") is None


# ─── Templates ─────────────────────────────────────────────────────────────

class TestTemplates:
    """Tests for pre-built workflow templates."""

    def test_templates_are_dicts(self):
        """TEMPLATES is a dict with at least one entry."""
        assert isinstance(TEMPLATES, dict)
        assert len(TEMPLATES) > 0

    def test_each_template_has_required_keys(self):
        """Each template has name, description, and steps."""
        for key, tmpl in TEMPLATES.items():
            assert "name" in tmpl, f"Template '{key}' missing 'name'"
            assert "description" in tmpl, f"Template '{key}' missing 'description'"
            assert "steps" in tmpl, f"Template '{key}' missing 'steps'"
            assert isinstance(tmpl["steps"], list)

    def test_each_step_has_action(self):
        """Every step in every template has an action field."""
        for key, tmpl in TEMPLATES.items():
            for i, step in enumerate(tmpl["steps"]):
                assert "action" in step, f"Template '{key}' step {i} missing 'action'"

    def test_singleton_store(self):
        """workflow_store is a WorkflowStore singleton."""
        assert isinstance(workflow_store, WorkflowStore)


# ─── Enums ─────────────────────────────────────────────────────────────────

class TestEnums:
    """Tests for WorkflowStatus and StepStatus enums."""

    def test_workflow_status_values(self):
        """WorkflowStatus has all expected values."""
        expected = {"draft", "active", "running", "paused", "completed", "failed"}
        assert set(e.value for e in WorkflowStatus) == expected

    def test_step_status_values(self):
        """StepStatus has all expected values."""
        expected = {"pending", "running", "done", "skipped", "failed"}
        assert set(e.value for e in StepStatus) == expected

    def test_enums_are_strings(self):
        """Both enums inherit from str for JSON serialization."""
        assert isinstance(WorkflowStatus.ACTIVE, str)
        assert isinstance(StepStatus.DONE, str)
