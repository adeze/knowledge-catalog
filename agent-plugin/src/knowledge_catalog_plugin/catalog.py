"""Read-only Google Cloud Knowledge Catalog discovery."""

from __future__ import annotations

import os
from typing import Any

from google.api_core.exceptions import PermissionDenied
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import dataplex_v1


def search_entries(
    query: str,
    project_id: str | None = None,
    page_size: int = 20,
    semantic_search: bool = True,
) -> dict[str, Any]:
    """Search Knowledge Catalog using the caller's Application Default Credentials."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be empty")
    if not 1 <= page_size <= 50:
        raise ValueError("page_size must be between 1 and 50")

    consumer_project = (project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip()
    if not consumer_project:
        raise ValueError(
            "project_id is required when GOOGLE_CLOUD_PROJECT is not set"
        )

    try:
        client = dataplex_v1.CatalogServiceClient(
            client_options={"api_endpoint": "dataplex.googleapis.com"}
        )
        response = client.search_entries(
            request={
                "name": f"projects/{consumer_project}/locations/global",
                "query": normalized_query,
                "page_size": page_size,
                "semantic_search": semantic_search,
            }
        )
        entries = []
        for result in response.results:
            entry = result.dataplex_entry
            source = entry.entry_source
            entries.append(
                {
                    "entry_name": entry.name,
                    "display_name": source.display_name,
                    "resource": source.resource,
                    "system": str(source.system),
                    "description": source.description,
                }
            )
        return {
            "consumer_project": consumer_project,
            "query": normalized_query,
            "semantic_search": semantic_search,
            "results": entries,
        }
    except DefaultCredentialsError as error:
        raise RuntimeError(
            "Application Default Credentials are unavailable; configure ADC before "
            "searching Knowledge Catalog"
        ) from error
    except PermissionDenied as error:
        raise RuntimeError(
            "Permission denied; the caller needs dataplex.projects.search on the "
            f"consumer project {consumer_project}"
        ) from error
