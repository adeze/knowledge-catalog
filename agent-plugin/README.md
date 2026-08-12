# Agent Plugin server

This package backs the portable root `mcp.json`. It exposes read-only Knowledge Catalog discovery plus a curated DuckDB memory/work-item store under `PLUGIN_DATA`.

The server does not replace client-native memory and does not execute stored work items automatically. Compatible clients must load the plugin and invoke its MCP tools; `skills/local-workflow-memory/SKILL.md` supplies the usage policy.

## Development

```bash
uv lock --project agent-plugin
uv run --project agent-plugin --locked --group dev pytest agent-plugin/tests
```

For a direct stdio launch, use a disposable state path:

```bash
KNOWLEDGE_CATALOG_STATE=/tmp/knowledge-catalog.duckdb \
  uv run --project agent-plugin --locked knowledge-catalog-agent-plugin
```

Knowledge Catalog search requires Application Default Credentials, `GOOGLE_CLOUD_PROJECT` unless a tool call supplies `project_id`, and `dataplex.projects.search` permission.

## DuckDB extensions

No community extension loads by default. `duckdb_extension_configure` has a closed allowlist:

- `fts` — DuckDB core; optional BM25 recall, with lexical fallback.
- `agent_data` — community; read-only lookup over local Codex session files.

Enabling a community extension downloads and executes signed third-party code with the MCP process's privileges. The tool requires explicit acknowledgement and records the decision in DuckDB. Unsigned and arbitrary extensions are never accepted.

Community loading has two gates. Before starting the MCP server, the human/operator must set `KNOWLEDGE_CATALOG_ALLOWED_COMMUNITY_EXTENSIONS=agent_data` in the host environment or client configuration. A tool call must then pass `acknowledge_third_party_code=true`. The portable `mcp.json` grants no community extension by default, and a running server cannot widen its startup allowlist.
