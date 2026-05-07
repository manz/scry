"""HTTP client behaviour: error decoding, pagination."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from scry.client import SonarApiError, SonarClient


@respx.mock
def test_get_json_payload(client: SonarClient) -> None:
    route = respx.get("http://sonar.test/api/system/status").mock(return_value=Response(200, json={"status": "UP"}))
    payload = client.get("/api/system/status")
    assert route.called
    assert payload == {"status": "UP"}


@respx.mock
def test_error_decodes_message(client: SonarClient) -> None:
    respx.get("http://sonar.test/api/projects/search").mock(
        return_value=Response(403, json={"errors": [{"msg": "Insufficient privileges"}]})
    )
    with pytest.raises(SonarApiError) as excinfo:
        client.get("/api/projects/search", projects="x")
    assert excinfo.value.status == 403
    assert "Insufficient privileges" in str(excinfo.value)


@respx.mock
def test_paginate_walks_pages(client: SonarClient) -> None:
    page1 = {
        "issues": [{"key": "1"}, {"key": "2"}],
        "paging": {"total": 3, "pageIndex": 1, "pageSize": 2},
    }
    page2 = {
        "issues": [{"key": "3"}],
        "paging": {"total": 3, "pageIndex": 2, "pageSize": 2},
    }
    route = respx.get("http://sonar.test/api/issues/search").mock(
        side_effect=[Response(200, json=page1), Response(200, json=page2)],
    )
    keys = [item["key"] for item in client.paginate("/api/issues/search", items_key="issues", page_size=2)]
    assert keys == ["1", "2", "3"]
    assert route.call_count == 2


@respx.mock
def test_paginate_stops_on_empty_page(client: SonarClient) -> None:
    respx.get("http://sonar.test/api/issues/search").mock(
        return_value=Response(200, json={"issues": [], "paging": {"total": 0}})
    )
    items = list(client.paginate("/api/issues/search", items_key="issues"))
    assert items == []


@respx.mock
def test_post_sends_form_data(client: SonarClient) -> None:
    route = respx.post("http://sonar.test/api/projects/create").mock(return_value=Response(200, json={}))
    client.post("/api/projects/create", project="manz_a816", name="a816")
    assert route.called
    request_body = route.calls.last.request.content.decode()
    assert "project=manz_a816" in request_body
    assert "name=a816" in request_body
