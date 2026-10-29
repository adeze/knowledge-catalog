from types import SimpleNamespace

import pytest
from google.api_core.exceptions import PermissionDenied
from google.auth.exceptions import DefaultCredentialsError

from knowledge_catalog_plugin import catalog
from knowledge_catalog_plugin.server import build_server


ENTRY = "projects/p/locations/us/entryGroups/@bigquery/entries/bigquery.googleapis.com/projects/p/datasets/d/tables/t"


def test_lookup_context_request_and_empty_result(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "consumer")
    responses = iter(["schema: orders", ""])

    class FakeClient:
        def lookup_context(self, request):
            # Construct the SDK request too, so mocks cannot hide invalid fields.
            parsed = catalog.dataplex_v1.LookupContextRequest(**request)
            assert parsed.name == "projects/consumer/locations/global"
            assert list(parsed.resources) == [ENTRY]
            assert dict(parsed.options) == {"format": "yaml", "context_budget": "12000"}
            return SimpleNamespace(context=next(responses))

    monkeypatch.setattr(catalog.dataplex_v1, "CatalogServiceClient", lambda **_: FakeClient())
    server = build_server(tmp_path / "state.duckdb")
    tool = server._tool_manager.get_tool("knowledge_catalog_lookup_context")
    assert tool.fn([ENTRY]) == {
        "consumer_project": "consumer", "context": "schema: orders"
    }
    assert catalog.lookup_context([ENTRY])["context"] == ""


def test_lookup_context_rejects_invalid_input_before_client_creation(monkeypatch):
    def unexpected_client(**_):
        pytest.fail("invalid input must not reach Google Cloud")

    monkeypatch.setattr(catalog.dataplex_v1, "CatalogServiceClient", unexpected_client)
    for resources, budget in [([], 1), ([ENTRY] * 11, 1), (["table"], 1), ([ENTRY], 0)]:
        with pytest.raises(ValueError):
            catalog.lookup_context(resources, "consumer", budget)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(ValueError, match="project_id is required"):
        catalog.lookup_context([ENTRY])


def test_lookup_context_reports_authentication_and_permission_failures(monkeypatch):
    class DeniedClient:
        def lookup_context(self, request):
            raise PermissionDenied("denied")

    monkeypatch.setattr(catalog.dataplex_v1, "CatalogServiceClient", lambda **_: DeniedClient())
    with pytest.raises(RuntimeError, match="catalog and source-resource access"):
        catalog.lookup_context([ENTRY], "consumer")

    def missing_credentials(**_):
        raise DefaultCredentialsError("missing")

    monkeypatch.setattr(catalog.dataplex_v1, "CatalogServiceClient", missing_credentials)
    with pytest.raises(RuntimeError, match="configure ADC"):
        catalog.lookup_context([ENTRY], "consumer")
