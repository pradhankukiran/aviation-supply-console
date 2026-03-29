from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import httpx

from aviation_supply_console.core.config import get_settings


def maybe_decompress(content: bytes) -> bytes:
    if content[:2] == b"\x1f\x8b":
        return gzip.decompress(content)
    return content


def fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> bytes:
    settings = get_settings()
    with httpx.Client(timeout=settings.api_timeout_seconds, follow_redirects=True) as client:
        response = client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.content


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = maybe_decompress(fetch_bytes(url, headers=headers, params=params))
    return json.loads(payload.decode("utf-8"))


def fetch_text(url: str, headers: dict[str, str] | None = None) -> str:
    payload = maybe_decompress(fetch_bytes(url, headers=headers))
    return payload.decode("utf-8")


def post_form_json(
    url: str,
    *,
    data: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=settings.api_timeout_seconds, follow_redirects=True) as client:
        response = client.post(url, data=data, headers=headers)
        response.raise_for_status()
        return response.json()


def persist_raw(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
