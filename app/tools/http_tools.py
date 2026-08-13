from __future__ import annotations

import json
from typing import Any

import httpx

from app.tools.base import Tool, ToolRegistry


async def http_get(args: dict[str, Any]) -> str:
    """Generic GET request — useful for wiring public APIs quickly."""
    url = args["url"]
    headers = args.get("headers") or {}
    params = args.get("params") or {}
    timeout = float(args.get("timeout", 20))

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url, headers=headers, params=params)
        content_type = response.headers.get("content-type", "")
        body: Any
        if "application/json" in content_type:
            body = response.json()
        else:
            body = response.text[:8000]
        return json.dumps(
            {
                "status_code": response.status_code,
                "url": str(response.url),
                "body": body,
            },
            default=str,
        )


async def http_post(args: dict[str, Any]) -> str:
    """Generic POST request for JSON APIs."""
    url = args["url"]
    headers = args.get("headers") or {}
    json_body = args.get("json")
    timeout = float(args.get("timeout", 20))

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.post(url, headers=headers, json=json_body)
        content_type = response.headers.get("content-type", "")
        body: Any
        if "application/json" in content_type:
            body = response.json()
        else:
            body = response.text[:8000]
        return json.dumps(
            {
                "status_code": response.status_code,
                "url": str(response.url),
                "body": body,
            },
            default=str,
        )


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="http_get",
            description=(
                "Perform an HTTP GET request to a public URL or API endpoint. "
                "Use for fetching JSON or text from the web."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to request"},
                    "headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Optional request headers",
                    },
                    "params": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Optional query parameters",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default 20)",
                    },
                },
                "required": ["url"],
            },
            handler=http_get,
        )
    )
    registry.register(
        Tool(
            name="http_post",
            description=(
                "Perform an HTTP POST request with an optional JSON body. "
                "Use for calling APIs that require POST."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to request"},
                    "headers": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Optional request headers",
                    },
                    "json": {
                        "type": "object",
                        "description": "Optional JSON body",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default 20)",
                    },
                },
                "required": ["url"],
            },
            handler=http_post,
        )
    )
    return registry
