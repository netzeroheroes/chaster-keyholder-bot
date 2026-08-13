"""Push local CHASTER_ACCESS_TOKEN to Render (requires RENDER_API_KEY)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
API = "https://api.render.com/v1"


def _env_value(name: str) -> str:
    if os.environ.get(name, "").strip():
        return os.environ[name].strip()
    if not ENV_PATH.is_file():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def main() -> int:
    api_key = _env_value("RENDER_API_KEY")
    token = _env_value("CHASTER_ACCESS_TOKEN")
    if not api_key:
        print("MISSING_RENDER_API_KEY")
        print("Create one at https://dashboard.render.com/u/settings#api-keys")
        print("Then: set RENDER_API_KEY=... in .env (or the environment) and re-run.")
        return 2
    if not token:
        print("MISSING_CHASTER_ACCESS_TOKEN")
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=45.0, headers=headers) as client:
        services = client.get(f"{API}/services?limit=50").json()
        if not isinstance(services, list):
            print("BAD_SERVICES", services)
            return 1

        service_id = ""
        service_name = ""
        for item in services:
            svc = item.get("service") if isinstance(item, dict) else item
            if not isinstance(svc, dict):
                continue
            name = str(svc.get("name") or "")
            if "chaster" in name.lower() or "keyholder" in name.lower():
                service_id = str(svc.get("id") or "")
                service_name = name
                break
        if not service_id:
            print("NO_SERVICE matching chaster/keyholder")
            return 1

        print("SERVICE", service_name, service_id)
        r = client.put(
            f"{API}/services/{service_id}/env-vars/CHASTER_ACCESS_TOKEN",
            json={"value": token},
        )
        print("UPSERT", r.status_code, r.text[:240])
        if r.status_code >= 400:
            return 1

        d = client.post(f"{API}/services/{service_id}/deploys", json={})
        print("DEPLOY", d.status_code, d.text[:200])
        if d.status_code >= 400:
            return 1

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
