# Upstream and dependency review — 2026-10-29

## Repository integration

The working tree was clean before integration. `origin/main` matched local `main`; `upstream/main` contained 238 new commits. Merge `c63d260` incorporates upstream `f90a32f`, preserves the fork's plugin additions, resolves both mdcode dependency-file conflicts, and refreshes TypeScript dependencies. Subsequent plugin and dependency changes remain in the working tree. Nothing was pushed or deployed.

Upstream adds semantic-model imports, profiles, SQL dialect translation, graph deployment, and source checks before publishing. It also rejects older source/target representations in favor of GCP resource names; existing external workspaces may need migration. New governance and policy-as-code samples retain their upstream dependency declarations and were not deployed or cloud-tested.

## Local grounding support

Added `knowledge_catalog_lookup_context`, discovery guidance, and [self-learning implementation notes](self-learning-enrichment.md). The tool uses the existing Dataplex SDK and ADC identity. It validates 1–10 full entry names, returns YAML, and passes the requested soft character budget to the API. Empty context is preserved. Authentication and permission failures have explicit diagnostics.

The portable plugin launcher now selects Python 3.13. Attempting DuckDB 1.5.6 under the host's Python 3.15 triggered a source build that failed against the macOS SDK (`ERA` macro collision). Python 3.13 installed a wheel and passed the plugin tests.

## Dependencies

- Plugin lock: DuckDB 1.5.6, Dataplex 2.21.0, MCP 1.30.0, plus compatible transitive updates.
- OKF: ADK requirement raised to 2.13.0 and BigQuery to 3.46.2; refreshed the local lock.
- TypeScript: ADK/devtools 2.4.0, MCP SDK 1.32.2, Inspector 2.13.0, Bun/types 1.4.4, plus compatible library updates. Polyglot SQL stays within the existing 0.9 line (resolved 0.9.2).
- ADK 2.4 was checked with the existing cleanup patches against a real local stdio MCP server: manual toolset close, successful runner completion, and runner failure all closed their sessions. Native session-manager bookkeeping exists in both ADK 1.6 and 2.4; it is not a newly introduced incompatibility.
- Inspector's CLI help and positional server forwarding remain supported. No application code migration was needed for these major updates.

Final npm registry audit: mdcode has zero findings; enrichment has two high findings, representing Azure Identity 4.14.0 and its MSAL Node 6.0.1 dependency. The underlying [MSAL authorization-code disclosure advisory](https://github.com/advisories/GHSA-xcx6-jx8p-x3h5) is fixed in 7.1.0. Azure Identity requests MSAL `^6.0.0`, so a compatible lockfile refresh cannot apply the fix. No forced cross-major override was added. Applicability to this application's Google-only workflow was not established; the dependency remains affected.

## Verification

- Plugin: 13 tests passed, including three new context tests and the stdio MCP handshake.
- OKF: 39 tests passed after updating ADK and BigQuery requirements and resolving dependencies. Its lockfile remains locally ignored by the existing repository policy.
- mdcode: compilation and standalone CLI build passed. Full offline run: 2,606 passed, nine failed across 2,615 tests. All nine failures also reproduce in an isolated checkout of untouched upstream with its own dependency lock; that baseline had 2,605 passed, ten failed, and one reported error.
- Inherited mdcode failures involve warning/message ordering, profile-file read spies, and case-only filename collisions. They remain unresolved; the suite is not green.
- Enrichment: TypeScript compilation and both standalone binaries built. Existing direct imports of `long`, `protobufjs`, and `zod` are now declared dependencies instead of relying on transitive installation.

Live catalog retrieval, Gemini responses, publication, IAM, preview access, and end-to-end cloud workflows were not tested. Managed self-learning requires project-specific configuration and review of approved data sources.
