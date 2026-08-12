from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from knowledge_catalog_plugin import catalog
from knowledge_catalog_plugin.catalog import search_entries
from knowledge_catalog_plugin.server import build_server
from knowledge_catalog_plugin.state import DuckDBState
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp.exceptions import ToolError
from pydantic_settings.sources.utils import IncompleteFieldDefinitionWarning

ROOT = Path(__file__).resolve().parents[2]


def _expand(value: str, plugin_data: Path) -> str:
    return value.replace("${PLUGIN_ROOT}", str(ROOT)).replace(
        "${PLUGIN_DATA}", str(plugin_data)
    )


def test_catalog_search_uses_read_only_semantic_search_request(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ValueError, match="project_id is required"):
        search_entries("sales tables")

    captured = {}

    class FakeClient:
        def search_entries(self, request):
            captured.update(request)
            source = SimpleNamespace(
                display_name="Orders",
                resource="//bigquery.googleapis.com/projects/p/datasets/d/tables/orders",
                system="BIGQUERY",
                description="Governed orders table",
            )
            entry = SimpleNamespace(name="projects/p/entries/orders", entry_source=source)
            return SimpleNamespace(results=[SimpleNamespace(dataplex_entry=entry)])

    monkeypatch.setattr(
        catalog.dataplex_v1,
        "CatalogServiceClient",
        lambda **_kwargs: FakeClient(),
    )
    result = search_entries("type=table orders", project_id="consumer", page_size=3)

    assert captured == {
        "name": "projects/consumer/locations/global",
        "query": "type=table orders",
        "page_size": 3,
        "semantic_search": True,
    }
    assert result["results"][0]["display_name"] == "Orders"


def test_stdio_mcp_handshake_lists_governed_tools(tmp_path) -> None:
    async def run() -> None:
        server = json.loads((ROOT / "mcp.json").read_text())["mcpServers"][
            "knowledge-catalog-local"
        ]
        environment = os.environ.copy()
        environment.update(
            {key: _expand(value, tmp_path) for key, value in server["env"].items()}
        )
        parameters = StdioServerParameters(
            command=server["command"],
            args=[_expand(value, tmp_path) for value in server["args"]],
            env=environment,
            cwd=_expand(server["cwd"], tmp_path),
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
        assert {
            "knowledge_catalog_search",
            "memory_remember",
            "memory_recall",
            "workflow_create",
            "workflow_update",
            "duckdb_extension_configure",
            "agent_history_search",
        }.issubset(tools)

    anyio.run(run)


def test_agent_history_denial_is_persistent_and_startup_allowlist_is_frozen(
    tmp_path,
) -> None:
    state_path = tmp_path / "state.duckdb"
    state = DuckDBState(state_path)
    state.set_extension_policy("agent_data", "community", True, acknowledged=True)
    approvals: set[str] = set()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", IncompleteFieldDefinitionWarning)
        server = build_server(state_path, allowed_community_extensions=approvals)
    approvals.add("agent_data")
    history_tool = server._tool_manager.get_tool("agent_history_search")

    with pytest.raises(ToolError, match="not approved by this server instance"):
        anyio.run(history_tool.run, {"query": "portable manifest"})
