# Applying self-learning enrichment

Reviewed 2026-10-29: [Google's demonstration](https://youtu.be/qeWzgLGSkls) and [launch explanation](https://cloud.google.com/blog/products/data-analytics/knowledge-catalog-self-learning-context-enrichment-for-ai-agents).

The demonstration shows valid SQL producing the wrong answer because a business definition is missing. Personal agent memory can preserve a correction for one client, but shared learning requires an authoritative, reusable catalog definition. Google's performance figures are internal benchmarks, not measured improvements in this repository.

## Implemented locally

The plugin now supports discovery followed by read-only `knowledge_catalog_lookup_context`. It requests YAML context for 1–10 full entry names in one location, using ADC and a soft character budget. The request location follows those entry names. The discovery skill instructs agents to retrieve context before reasoning about definitions, schemas, or joins, and to preserve citations and uncertainty. An empty response can indicate insufficient permissions.

The implementation follows the [LookupContext REST contract](https://docs.cloud.google.com/knowledge-catalog/docs/reference/rest/v1/projects.locations/lookupContext), including `options.context_budget`, and the installed Dataplex SDK. See [context retrieval](https://docs.cloud.google.com/knowledge-catalog/docs/retrieve-data-context) for supported metadata and access behavior.

## Next implementation: configure managed enrichment

Knowledge Studio, context sets, and self-learning require [gated preview access](https://docs.cloud.google.com/knowledge-catalog/docs/context-sets). No project, preview entitlement, execution identity, or approved telemetry source has been selected here. These are deployment prerequisites, not features a local dependency update enables.

1. Select a domain and its authoritative documents, tables, and definitions; configure the context set and least-privilege identities.
2. Prepare representative evaluation questions with expected definitions and answers. Record baseline quality before enrichment.
3. Configure an [enrichment task](https://docs.cloud.google.com/knowledge-catalog/docs/create-enrichment-tasks) with approved sources. Keep auto-publishing disabled initially. Review citations, confidence, conflicts, and proposed diffs before accepting changes.
4. If self-learning is enabled, configure approved interaction traces with scoped access and redaction. Do not ingest private chat histories merely because the local history extension exists.
5. Evaluate proposed updates against the baseline, publish approved changes, and confirm downstream agents retrieve the updated context. Keep audit provenance and a rollback path.

For a custom offline experiment, reuse OKF's existing `sources`, `verified`, and staleness mechanisms rather than introducing a parallel trust model. A model confidence score alone is insufficient evidence to promote a business definition. A review queue, trace ingestion, scheduled enrichment, cloud configuration, and automatic publication are not implemented by this local change.
