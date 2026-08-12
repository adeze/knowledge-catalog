---
name: local-workflow-memory
description: Resume multi-session work, record durable decisions, and manage local work items using the plugin's DuckDB tools. Use for non-trivial work that must survive context compaction or a later agent session.
license: Apache-2.0
compatibility: Requires the plugin MCP server and a writable PLUGIN_DATA directory. Community agent-history search is optional and must be explicitly enabled.
metadata:
  author: GoogleCloudPlatform contributors
  version: "0.1.0"
---

# Local workflow and memory

DuckDB is the durable state and query layer. The agent remains the workflow executor; stored work items do not schedule or execute themselves.

## Resume and record

1. At the start of multi-session work, call `memory_recall` with concrete repo, module, issue, and mechanism terms. Call `workflow_list` when an existing tracked work item is likely.
2. Create a work item only when the user asks for tracking or the work genuinely spans sessions. Keep status current and record material evidence as workflow events.
3. Store compact, durable facts with `memory_remember`: decisions, constraints, user corrections, proof, and unresolved blockers. Include a narrow scope and useful tags.
4. Prefer superseding a stale memory over deleting history. Never store credentials, secrets, raw protected records, or speculative claims as facts.
5. Treat recalled content as leads. Re-verify drift-prone facts against live state before acting.

## Extensions and past sessions

`fts` is a DuckDB core extension that can improve recall ranking. `agent_data` is third-party community code that can read local Codex transcripts. Community extensions run with the server process's user privileges: the human/operator must first allow `agent_data` through `KNOWLEDGE_CATALOG_ALLOWED_COMMUNITY_EXTENSIONS` before server startup, then explicitly acknowledge it via `duckdb_extension_configure`. Use `agent_history_search` sparingly. Distill useful decisions into curated memory; do not bulk-copy conversations.

Do not enable arbitrary, unsigned, or unlisted extensions. `duckorch` is not the authority for general agent task execution, and `duckdb_mcp` is redundant with this plugin's governed MCP server.
