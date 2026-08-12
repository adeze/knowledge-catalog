"""Portable stdio MCP server."""

from __future__ import annotations

import os
from collections.abc import Collection
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .catalog import search_entries
from .extensions import configure_extension, extension_status
from .state import DuckDBState


def build_server(
    state_path: str | Path,
    codex_data_path: str | Path | None = None,
    allowed_community_extensions: Collection[str] | None = None,
) -> FastMCP:
    state = DuckDBState(state_path)
    if allowed_community_extensions is None:
        allowed_community_extensions = {
            name.strip()
            for name in os.getenv(
                "KNOWLEDGE_CATALOG_ALLOWED_COMMUNITY_EXTENSIONS", ""
            ).split(",")
            if name.strip()
        }
    host_allowed_community_extensions = frozenset(allowed_community_extensions)
    server = FastMCP(
        "Knowledge Catalog Local",
        instructions=(
            "Use Knowledge Catalog search read-only. DuckDB work items are durable "
            "state, not an automatic executor. Store curated facts only; never secrets."
        ),
    )

    @server.tool()
    def knowledge_catalog_search(
        query: str,
        project_id: str | None = None,
        page_size: int = 20,
        semantic_search: bool = True,
    ) -> dict[str, Any]:
        """Search Google Cloud Knowledge Catalog. This tool never modifies catalog data."""
        return search_entries(query, project_id, page_size, semantic_search)

    @server.tool()
    def memory_remember(
        content: str,
        kind: str = "note",
        scope: str = "global",
        tags: list[str] | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Store one curated decision, constraint, correction, item of evidence, or note."""
        return state.remember(
            content, kind, scope, tags, source, metadata, supersedes
        )

    @server.tool()
    def memory_recall(
        query: str,
        scope: str | None = None,
        kinds: list[str] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Recall active curated memories. Re-verify facts that may have drifted."""
        return state.recall(query, scope, kinds, limit)

    @server.tool()
    def workflow_create(
        title: str,
        details: str = "",
        priority: int = 0,
        status: str = "todo",
        parent_id: str | None = None,
        depends_on: list[str] | None = None,
        tags: list[str] | None = None,
        due_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a durable work item. Creation does not schedule or execute it."""
        return state.create_work_item(
            title,
            details,
            priority,
            status,
            parent_id,
            depends_on,
            tags,
            due_at,
            metadata,
        )

    @server.tool()
    def workflow_update(
        work_id: str,
        status: str | None = None,
        title: str | None = None,
        details: str | None = None,
        priority: int | None = None,
        tags: list[str] | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Update a work item and append an audit event."""
        return state.update_work_item(
            work_id, status, title, details, priority, tags, note
        )

    @server.tool()
    def workflow_list(
        status: str | None = None,
        runnable_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List work items, optionally restricting results to dependency-ready work."""
        return state.list_work_items(status, runnable_only, limit)

    @server.tool()
    def workflow_record_event(
        event_type: str,
        summary: str,
        work_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append evidence or a lifecycle event without changing execution state."""
        return state.record_event(event_type, summary, work_id, payload)

    @server.tool()
    def workflow_summary(recent_event_limit: int = 10) -> dict[str, Any]:
        """Summarize work-item status counts and recent audit events."""
        return state.workflow_summary(recent_event_limit)

    @server.tool()
    def duckdb_extension_status() -> dict[str, Any]:
        """Show the closed DuckDB extension registry, runtime state, and trust policy."""
        return extension_status(state, host_allowed_community_extensions)

    @server.tool()
    def duckdb_extension_configure(
        name: str,
        enabled: bool,
        acknowledge_third_party_code: bool = False,
    ) -> dict[str, Any]:
        """Enable or disable an allowlisted extension; community code needs approval."""
        return configure_extension(
            state,
            name,
            enabled,
            acknowledge_third_party_code,
            host_allowed_community_extensions,
        )

    @server.tool()
    def agent_history_search(
        query: str,
        limit: int = 20,
        project_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search local Codex transcripts read-only through opt-in community agent_data."""
        if "agent_data" not in host_allowed_community_extensions:
            raise ValueError(
                "agent_data is not approved by this server instance; restart with "
                "KNOWLEDGE_CATALOG_ALLOWED_COMMUNITY_EXTENSIONS=agent_data"
            )
        return state.search_agent_history(
            query,
            limit=limit,
            project_path=project_path,
            codex_data_path=codex_data_path,
        )

    return server


def main() -> None:
    state_path = os.getenv("KNOWLEDGE_CATALOG_STATE")
    if not state_path:
        plugin_data = os.getenv("PLUGIN_DATA")
        if not plugin_data:
            raise RuntimeError(
                "KNOWLEDGE_CATALOG_STATE or Agent Plugins PLUGIN_DATA is required"
            )
        state_path = str(Path(plugin_data) / "knowledge-catalog.duckdb")
    build_server(state_path).run(transport="stdio")


if __name__ == "__main__":
    main()
