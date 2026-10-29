# Upstream and dependency review — 2026-10-29

## Repository integration

The working tree was clean before integration. `origin/main` matched local `main`; `upstream/main` contained 238 new commits. Merge `c63d260` incorporates upstream `f90a32f`, preserves the fork's plugin additions, resolves both mdcode dependency-file conflicts, and refreshes TypeScript dependencies. Initial grounding changes are committed through `2bd4f46`; the follow-up repairs below remain local. This review did not push or deploy anything.

Upstream adds semantic-model imports, profiles, SQL dialect translation, graph deployment, and source checks before publishing. It also rejects older source/target representations in favor of GCP resource names; existing external workspaces may need migration. New governance and policy-as-code samples retain their upstream dependency declarations and were not deployed or cloud-tested.

## Local grounding support

Added `knowledge_catalog_lookup_context`, discovery guidance, and [self-learning implementation notes](self-learning-enrichment.md). The tool uses the existing Dataplex SDK and ADC identity. It validates 1–10 full entry names in one location, derives the API request location from those names, returns YAML, and passes the requested soft character budget to the API. Empty context is preserved. Authentication and permission failures have explicit diagnostics.

A live regional lookup exposed the initial hardcoded `global` parent: Google rejected it with `Resource location should be the same as the request location.` The follow-up fixes this and rejects mixed-location batches before calling Google. The local tool then retrieved nonempty context for RBA's `truthguard.feed_subscriptions` entry in `us-central1`; a requested 1,000-character soft budget returned 12,339 characters, confirming it must not be treated as a hard limit.

The portable plugin launcher now selects Python 3.13. Attempting DuckDB 1.5.6 under the host's Python 3.15 triggered a source build that failed against the macOS SDK (`ERA` macro collision). Python 3.13 installed a wheel and passed the plugin tests.

## Dependencies

- Plugin lock: DuckDB 1.5.6, Dataplex 2.21.0, MCP 1.30.0, plus compatible transitive updates.
- OKF: ADK requirement raised to 2.13.0 and BigQuery to 3.46.2; refreshed the local lock.
- TypeScript: ADK/devtools 2.4.0, MCP SDK 1.32.2, Inspector 2.13.0, Bun/types 1.4.4, plus compatible library updates. Polyglot SQL stays within the existing 0.9 line (resolved 0.9.2).
- ADK 2.4 was checked with the existing cleanup patches against a real local stdio MCP server: manual toolset close, successful runner completion, and runner failure all closed their sessions. Native session-manager bookkeeping exists in both ADK 1.6 and 2.4; it is not a newly introduced incompatibility.
- Inspector's CLI help and positional server forwarding remain supported. No application code migration was needed for these major updates.

Both final npm registry audits report zero findings across all severities. Enrichment overrides MSAL Node to `^7.1.2` to fix the [authorization-code disclosure advisory](https://github.com/advisories/GHSA-xcx6-jx8p-x3h5). Azure Identity 4.14.0 still requests MSAL `^6.0.0`; neither its latest stable nor preview release supplied a supported parent fix at review time. The [MSAL 7 major change](https://github.com/AzureAD/microsoft-authentication-library-for-js/releases/tag/msal-node-v7.0.0) removes interactive `responseMode`; Azure Identity does not set that option. The override is backed by a durable offline test using real Azure Identity/MSAL implementations and synthetic HTTP responses for client-secret success, authorization-code success, and rejected authorization-code propagation. Live Azure authentication remains untested. Revisit the override when Azure Identity supports patched MSAL directly.

## Verification

- Plugin: 13 tests passed, including three new context tests and the stdio MCP handshake.
- OKF: 39 tests passed after updating ADK and BigQuery requirements and resolving dependencies. Its lockfile remains locally ignored by the existing repository policy.
- mdcode: compilation, library emission, and standalone CLI build passed. Final repository test groups: 2,640 passed, zero failed (25 scenarios, two layouts, 20 GCP, 2,137 semantic, 456 tool tests). Run the groups in separate Bun processes as the package scripts specify: scenario tests mock `node:fs` globally.
- Fixed all nine inherited failures. Sort semantic-model glob matches before indexing to stabilize warnings and deployment diagnostics. Canonicalize temporary fixture roots so `/tmp` aliases match `/private/tmp` read spies on macOS. Use the existing memfs dependency to preserve case-only filename pairs in the collision fixture on case-insensitive hosts. Existing assertions and validation remain intact.
- Enrichment: TypeScript compilation and both standalone binaries built. Existing direct imports of `long`, `protobufjs`, and `zod` are now declared dependencies instead of relying on transitive installation.
- Enrichment auth regression: one Bun test covers three offline grant paths and passes. ADK's real local stdio lifecycle check also passes after the dependency repair.

## RBA integration and plugin activation

RBA's Codex configuration enables Google's remote Knowledge Catalog MCP with `search_entries`, `lookup_context`, and `lookup_entry`. Its legacy local Toolbox server and standalone Knowledge Catalog plugin are disabled. DAK remains the canonical plugin; the separately configured remote server is its currently available fallback. A bounded live search followed by regional `lookup_context` succeeded against project `truthguard-488000`. No reinstall of this fork is required for that remote capability.

RBA's `tools/knowledge-catalog/` resolves `KNOWLEDGE_CATALOG_TOOLBOX_ROOT` to this sibling checkout by default. Its compatibility check confirmed the rebuilt `kcmd`, `kcagent`, `md-fileset`, OKF Python, and RBA's migrated OKF core exist. RBA's planning tools remain repo-native; enrichment is proposal/review-only. These local builds do not update Google's remote service or configure managed self-learning.

From RBA, the bounded check that succeeded was:

```bash
bun tools/knowledge-catalog/bin/knowledge-catalog-tools.ts toolbox-compat-check
```

The Nx check could not start because RBA's `node_modules/nx` is absent. Dependencies were not installed over the user's unrelated lockfile changes. Once workspace dependencies are restored, use the existing `knowledge-catalog:toolbox-compat-check`, `knowledge-catalog:okf-check`, `knowledge-catalog:enrichment-propose`, and `knowledge-catalog:enrichment-review` targets. Do not run the upstream enrichment CLI's publishing behavior from RBA.

A separately installed cached copy of this fork would need an update/refresh and MCP process restart to load changed code and tool schemas; editing this checkout does not update that cache. A server launched directly from this checkout needs a restart. RBA's existing remote server needs neither for these local repairs. No plugin enablement or client configuration was changed.

Gemini responses, publication, IAM changes, preview access, live Azure authentication, and end-to-end cloud workflows were not tested. Managed self-learning requires project-specific configuration and review of approved data sources.
