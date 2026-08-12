from __future__ import annotations

import pytest
from knowledge_catalog_plugin.extensions import configure_extension, extension_status
from knowledge_catalog_plugin.state import DuckDBState


def test_memory_recall_and_non_destructive_supersession(tmp_path) -> None:
    state = DuckDBState(tmp_path / "state.duckdb")
    prior = state.remember(
        "Use root plugin.json for the portable Agent Plugins manifest.",
        kind="decision",
        scope="knowledge-catalog",
        tags=["plugin", "spec"],
    )
    replacement = state.remember(
        "Use root plugin.json and root mcp.json with matching v1.0.0 schemas.",
        kind="correction",
        scope="knowledge-catalog",
        tags=["plugin", "spec"],
        supersedes=prior["memory_id"],
    )

    recalled = state.recall("root mcp schema", scope="knowledge-catalog")
    assert recalled["search_mode"] == "lexical"
    assert [item["memory_id"] for item in recalled["items"]] == [replacement["memory_id"]]
    assert state.recall("", scope="knowledge-catalog")["items"][0]["active"] is True
    with pytest.raises(ValueError, match="is no longer active"):
        state.remember("Conflicting correction", supersedes=prior["memory_id"])


def test_work_items_enforce_dependencies_and_keep_events(tmp_path) -> None:
    state = DuckDBState(tmp_path / "state.duckdb")
    prerequisite = state.create_work_item("Validate manifests", priority=10)
    dependent = state.create_work_item(
        "Smoke MCP server", depends_on=[prerequisite["work_id"]]
    )

    assert state.list_work_items(runnable_only=True)[0]["work_id"] == prerequisite["work_id"]
    with pytest.raises(ValueError, match="unresolved dependencies"):
        state.update_work_item(dependent["work_id"], status="done")
    with pytest.raises(ValueError, match="note must not be empty"):
        state.update_work_item(prerequisite["work_id"], note="   ")

    state.update_work_item(prerequisite["work_id"], status="done", note="schemas pass")
    assert state.list_work_items(runnable_only=True, limit=1)[0]["work_id"] == dependent["work_id"]
    state.update_work_item(dependent["work_id"], status="done")
    with pytest.raises(ValueError, match="cannot reopen work item"):
        state.update_work_item(prerequisite["work_id"], status="todo")
    summary = state.workflow_summary()
    assert summary["counts"]["done"] == 2
    assert len(summary["recent_events"]) >= 4


def test_work_item_and_audit_event_rollback_together(tmp_path, monkeypatch) -> None:
    state = DuckDBState(tmp_path / "state.duckdb")

    def fail_event(*_args, **_kwargs):
        raise RuntimeError("event failure")

    monkeypatch.setattr(state, "_record_event", fail_event)
    with pytest.raises(RuntimeError, match="event failure"):
        state.create_work_item("Must be atomic")
    assert state.list_work_items() == []


def test_extension_registry_is_closed_and_community_requires_acknowledgement(tmp_path) -> None:
    state = DuckDBState(tmp_path / "state.duckdb")
    status = extension_status(state)
    assert status["unsigned_extensions_allowed"] is False
    assert status["arbitrary_extensions_allowed"] is False
    agent_data = next(
        item for item in status["extensions"] if item["name"] == "agent_data"
    )
    assert agent_data["host_approved"] is False
    assert agent_data["effective_enabled"] is False
    with pytest.raises(ValueError, match="closed registry"):
        configure_extension(state, "shellfs", True, True)
    with pytest.raises(ValueError, match="not approved by the host"):
        configure_extension(state, "agent_data", True, True)
    with pytest.raises(ValueError, match="third-party code"):
        configure_extension(state, "agent_data", True, False, {"agent_data"})
    with pytest.raises(ValueError, match="not supported"):
        configure_extension(state, "duckdb_mcp", True, True)


def test_agent_history_is_unavailable_until_opted_in(tmp_path) -> None:
    state = DuckDBState(tmp_path / "state.duckdb")
    with pytest.raises(ValueError, match="agent_data is disabled"):
        state.search_agent_history("portable manifest")
