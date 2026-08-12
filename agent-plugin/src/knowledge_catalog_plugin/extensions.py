"""Closed DuckDB extension registry and trust policy."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import asdict, dataclass
from typing import Any

from .state import DuckDBState


@dataclass(frozen=True)
class ExtensionSpec:
    name: str
    repository: str
    maintained_by: str
    purpose: str
    supported: bool
    reason: str


EXTENSIONS = {
    "fts": ExtensionSpec(
        name="fts",
        repository="core",
        maintained_by="DuckDB",
        purpose="BM25 ranking for curated memory recall",
        supported=True,
        reason="Core extension with lexical fallback when unavailable.",
    ),
    "agent_data": ExtensionSpec(
        name="agent_data",
        repository="community",
        maintained_by="axsaucedo/agent_data_duckdb",
        purpose="Read-only search over local Codex session JSONL",
        supported=True,
        reason="Useful bridge from raw sessions to curated memory; explicit opt-in only.",
    ),
    "duckorch": ExtensionSpec(
        name="duckorch",
        repository="community",
        maintained_by="community",
        purpose="SQL DAG execution and lineage",
        supported=False,
        reason="SQL asset orchestration is not the general agent work-item contract.",
    ),
    "duckdb_mcp": ExtensionSpec(
        name="duckdb_mcp",
        repository="community",
        maintained_by="teaguesterling/duckdb_mcp",
        purpose="Expose DuckDB through MCP",
        supported=False,
        reason="Redundant with this server and would widen the SQL/tool boundary.",
    ),
    "markdown": ExtensionSpec(
        name="markdown",
        repository="community",
        maintained_by="community",
        purpose="Parse Markdown inside DuckDB",
        supported=False,
        reason="No current workflow requires in-database Markdown parsing.",
    ),
    "json_schema": ExtensionSpec(
        name="json_schema",
        repository="community",
        maintained_by="community",
        purpose="Validate JSON inside DuckDB",
        supported=False,
        reason="Application schemas already validate tool inputs without third-party code.",
    ),
}


def extension_status(
    state: DuckDBState,
    host_allowed_community_extensions: Collection[str] = (),
) -> dict[str, Any]:
    runtime = state.extension_runtime_status(list(EXTENSIONS))
    policy = state.extension_policy()
    entries = []
    for name, spec in EXTENSIONS.items():
        entry = asdict(spec)
        entry.update(runtime.get(name, {"installed": False, "loaded": False}))
        entry["enabled"] = policy.get(name, {}).get("enabled", False)
        entry["acknowledged_at"] = policy.get(name, {}).get("acknowledged_at")
        entry["host_approved"] = (
            spec.repository != "community"
            or name in host_allowed_community_extensions
        )
        entry["effective_enabled"] = entry["enabled"] and entry["host_approved"]
        entries.append(entry)
    return {
        "unsigned_extensions_allowed": False,
        "arbitrary_extensions_allowed": False,
        "extensions": entries,
    }


def configure_extension(
    state: DuckDBState,
    name: str,
    enabled: bool,
    acknowledge_third_party_code: bool = False,
    host_allowed_community_extensions: Collection[str] = (),
) -> dict[str, Any]:
    spec = EXTENSIONS.get(name)
    if spec is None:
        raise ValueError(f"extension {name!r} is not in the closed registry")
    if not spec.supported:
        raise ValueError(f"extension {name!r} is not supported: {spec.reason}")
    if not enabled:
        state.set_extension_policy(name, spec.repository, False, acknowledged=False)
        return extension_status(state, host_allowed_community_extensions)
    if spec.repository == "community":
        if name not in host_allowed_community_extensions:
            raise ValueError(
                f"community extension {name!r} is not approved by the host; set "
                "KNOWLEDGE_CATALOG_ALLOWED_COMMUNITY_EXTENSIONS before server startup"
            )
        if not acknowledge_third_party_code:
            raise ValueError(
                "community extensions execute third-party code with this process's "
                "privileges; set acknowledge_third_party_code=true after explicit user approval"
            )
    state.install_and_enable_extension(
        name,
        spec.repository,
        acknowledged=acknowledge_third_party_code,
    )
    return extension_status(state, host_allowed_community_extensions)
