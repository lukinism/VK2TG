from __future__ import annotations

import ssl

import certifi
import httpx


def create_ssl_context() -> ssl.SSLContext:
    try:
        return ssl.create_default_context()
    except FileNotFoundError:
        return ssl.create_default_context(cafile=certifi.where())


def build_async_client(**kwargs) -> httpx.AsyncClient:
    client_kwargs = dict(kwargs)
    client_kwargs.setdefault("verify", create_ssl_context())
    return httpx.AsyncClient(**client_kwargs)
