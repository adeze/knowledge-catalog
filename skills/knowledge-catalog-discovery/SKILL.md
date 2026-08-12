---
name: knowledge-catalog-discovery
description: Search and rank Google Cloud Knowledge Catalog entries. Use when a user needs to discover datasets, tables, files, models, or other governed data assets in Dataplex.
license: Apache-2.0
compatibility: Requires the plugin MCP server, Google Cloud Application Default Credentials, GOOGLE_CLOUD_PROJECT or an explicit project ID, and dataplex.projects.search permission.
metadata:
  author: GoogleCloudPlatform contributors
  version: "0.1.0"
---

# Knowledge Catalog discovery

Use `knowledge_catalog_search` to find data assets that can answer the user's question. This is discovery: return relevant entries, not invented statistics from data you have not queried.

## Search

1. Preserve explicit Knowledge Catalog predicates such as `projectid=`, `type=`, `system=`, `name:`, and `parent=`.
2. Run the user's wording as the baseline query.
3. For complex questions, add at most three distinct variations: direct synonyms, likely storage terminology, and the broader business domain. Batch independent calls when the client supports it.
4. `project_id` selects the consumer project used in the API parent. A `projectid=` predicate filters assets. They are different; retain both when both are required.
5. Deduplicate by full entry name, rank by the user's intent, and return only the most relevant results with their full entry names.

Do not call write APIs. If authentication or permission fails, report the exact missing prerequisite rather than weakening the query.
