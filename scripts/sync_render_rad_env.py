"""Push local RAD_* Lockbox env vars to Render and trigger a deploy."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CLI_YAML = Path.home() / ".render" / "cli.yaml"
API = "https://api.render.com/v1"

RAD_KEYS = (
    "RAD_API_TOKEN",
    "RAD_LOCKBOX_SYNC_ENABLED",
    "RAD_SYNC_HYGIENE",
    "RAD_SYNC_SESSION_LOCK",
    "RAD_MANUAL_ONLY",
    "RAD_TARGET_USER_ID",
    "RAD_LOCK_SETTINGS_ID",
    "RAD_KEYHOLDER_IDS",
    "RAD_IS_TEST_LOCK",
)


def _dotenv(name: str) -> str:
    if not ENV_PATH.is_file():
        return ""
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _render_api_key() -> str:
    if not CLI_YAML.is_file():
        return ""
    for line in CLI_YAML.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("key:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def main() -> int:
    api_key = _render_api_key()
    if not api_key:
        print("MISSING_RENDER_API_KEY")
        return 2

    values = {k: _dotenv(k) for k in RAD_KEYS}
    if not values["RAD_API_TOKEN"]:
        print("MISSING_RAD_API_TOKEN in .env")
        return 2

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60.0, headers=headers) as client:
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
        for key, value in values.items():
            if value == "":
                print("SKIP", key, "(empty — leave unset)")
                continue
            r = client.put(
                f"{API}/services/{service_id}/env-vars/{key}",
                json={"value": value},
            )
            shown = "***" if "TOKEN" in key else value
            print("UPSERT", key, r.status_code, shown)
            if r.status_code >= 400:
                print(r.text[:400])
                return 1

        d = client.post(f"{API}/services/{service_id}/deploys", json={})
        print("DEPLOY", d.status_code)
        if d.status_code >= 400:
            print(d.text[:400])
            return 1
        body = d.json() if "application/json" in d.headers.get("content-type", "") else {}
        deploy = body.get("deploy") if isinstance(body, dict) else None
        if isinstance(deploy, dict):
            print("DEPLOY_ID", deploy.get("id"), deploy.get("status"))

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
