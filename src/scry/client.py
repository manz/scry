"""HTTP client for SonarQube / SonarCloud Web APIs.

The `SonarClient` is the same base for both backends; the per-backend
specifics (organization scoping, project-create permissions) live in
`scry.backends`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from scry.config import Profile


class SonarApiError(RuntimeError):
    """Raised when the server returns a non-2xx response we can't paper over."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status


class SonarClient:
    """Thin wrapper over `httpx.Client` doing token auth + JSON decode."""

    def __init__(self, profile: Profile, *, timeout: float = 30.0) -> None:
        self.profile = profile
        self._http = httpx.Client(
            base_url=profile.host_url_str,
            auth=(profile.token, ""),
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def __enter__(self) -> SonarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # raw GET / POST helpers
    # ------------------------------------------------------------------

    def get(self, path: str, **params: Any) -> Any:
        response = self._http.get(path, params=_clean(params))
        return _decode(response)

    def post(self, path: str, **data: Any) -> Any:
        response = self._http.post(path, data=_clean(data))
        return _decode(response)

    # ------------------------------------------------------------------
    # paginated helpers
    # ------------------------------------------------------------------

    def paginate(self, path: str, *, items_key: str, page_size: int = 200, **params: Any) -> Iterable[dict[str, Any]]:
        """Yield items across all pages. `items_key` is the JSON field that holds the page list."""
        page = 1
        while True:
            payload = self.get(path, **params, p=page, ps=page_size)
            items = payload.get(items_key, []) or []
            yield from items
            paging = payload.get("paging") or {}
            total = int(paging.get("total", len(items)))
            seen = page * page_size
            if seen >= total or not items:
                return
            page += 1


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None}


def _decode(response: httpx.Response) -> Any:
    if response.is_success:
        if not response.content:
            return {}
        return response.json()
    try:
        payload = response.json()
        message = "; ".join(err.get("msg", "") for err in payload.get("errors", []) or [])
    except Exception:
        message = response.text or response.reason_phrase
    raise SonarApiError(response.status_code, message or "request failed")
