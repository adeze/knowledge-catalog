# Knowledge Catalog

Google Cloud's Knowledge Catalog (formerly Dataplex) tools, agents, and samples — a knowledge graph/metadata platform for grounding AI agents. Not an official Google product (see [README.md](README.md)).

## Structure
- `plugin.json`, `mcp.json`, `skills/` — portable Agent Plugins v1.0.0 surface. `agent-plugin/` implements the stdio MCP server and stores durable runtime state only under `PLUGIN_DATA`.
- `okf/` — Open Knowledge Format: a vendor-neutral spec (markdown + YAML frontmatter) for representing catalog knowledge. See `okf/SPEC.md`. Contains the `reference-agent` Python package (`okf/src`, `okf/pyproject.toml`) that produces OKF bundles, plus example bundles in `okf/bundles/` (ga4, stackoverflow, crypto_bitcoin) each with a `viz.html` graph viewer.
- `toolbox/` — `mdcode` (metadata-as-code sync) and `enrichment` (agent harness for generating/maintaining catalog metadata).
- `samples/` — `discovery` (search/discovery agent over Catalog Search APIs) and `enrichment` (doc-generation agent) demos.

## Conventions
- `okf/` is a Python package: `requires-python >= 3.11`, uses `google-adk`, `google-cloud-bigquery`, `pydantic`, `pyyaml`. Use `uv` for Python env/deps, not `pip`.
- Tests: `pytest` (see `okf/pyproject.toml` `[tool.pytest.ini_options]`).
- OKF is the core contribution — when touching `okf/`, changes to bundle output shape should stay consistent with `okf/SPEC.md`.
- Agent Plugin changes must preserve the closed root manifest schemas, fixed `skills/` and `mcp.json` locations, `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` portability, and the explicit opt-in boundary for community DuckDB extensions.
