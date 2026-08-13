"""Research & Desire Lockbox Dashboard API client (no AI).

Docs: https://dev.researchanddesire.com/
Base: https://dashboard.researchanddesire.com/api/v1
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://dashboard.researchanddesire.com/api/v1"


class RadLockboxClient:
    """Thin connector to R+D Lockbox session endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = (
            (getattr(settings, "rad_api_base_url", None) or DEFAULT_BASE)
            .rstrip("/")
        )
        self.token = (getattr(settings, "rad_api_token", None) or "").strip()
        self.target_user_id = self._optional_int(
            getattr(settings, "rad_target_user_id", None)
        )
        self.lock_settings_id = self._optional_int(
            getattr(settings, "rad_lock_settings_id", None)
        )
        self.keyholder_ids = self._parse_ids(
            getattr(settings, "rad_keyholder_ids", None) or ""
        )
        self.is_test_lock = bool(getattr(settings, "rad_is_test_lock", False))

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "" or value == 0:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_ids(raw: str) -> list[int]:
        out: list[int] = []
        for part in str(raw or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                continue
        return out

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def sync_ready(self) -> bool:
        """Token + template id required to re-lock after hygiene."""
        return self.configured and self.lock_settings_id is not None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise RuntimeError("RAD_API_TOKEN is not set")
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params or None,
            )
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            payload = {"ok": False, "error": resp.text[:500]}
        if not isinstance(payload, dict):
            payload = {"ok": False, "error": "Unexpected response", "raw": payload}
        if resp.status_code >= 400 or payload.get("ok") is False:
            err = payload.get("error") or resp.text[:300] or f"HTTP {resp.status_code}"
            raise RuntimeError(f"R+D API {method} {path} failed: {err}")
        return payload

    async def list_users(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/users")
        return _unwrap_list(data.get("data"))

    async def list_devices(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/lkbx/devices")
        return _unwrap_list(data.get("data"))

    async def list_templates(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/lkbx/templates")
        return _unwrap_list(data.get("data"))

    async def get_active_session(
        self, *, target_user_id: int | None = None
    ) -> dict[str, Any] | None:
        params: dict[str, Any] = {}
        tid = target_user_id if target_user_id is not None else self.target_user_id
        if tid is not None:
            params["targetUserId"] = tid
        data = await self._request("GET", "/lkbx/session/current", params=params)
        session = data.get("data")
        return session if isinstance(session, dict) else None

    async def lock(
        self,
        *,
        lock_settings_id: int | None = None,
        target_user_id: int | None = None,
        keyholder_ids: list[int] | None = None,
        is_test_lock: bool | None = None,
    ) -> dict[str, Any]:
        lid = lock_settings_id if lock_settings_id is not None else self.lock_settings_id
        if lid is None:
            raise RuntimeError("RAD_LOCK_SETTINGS_ID (lock template id) is required to lock")
        body: dict[str, Any] = {
            "action": "lock",
            "lockSettingsId": int(lid),
        }
        tid = target_user_id if target_user_id is not None else self.target_user_id
        if tid is not None:
            body["targetUserId"] = int(tid)
        kh = keyholder_ids if keyholder_ids is not None else self.keyholder_ids
        if kh:
            body["keyholderIds"] = [int(x) for x in kh]
        test = self.is_test_lock if is_test_lock is None else is_test_lock
        if test:
            body["isTestLock"] = True
        return await self._request("POST", "/lkbx/session/current", json_body=body)

    async def unlock(self, *, target_user_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"action": "unlock"}
        tid = target_user_id if target_user_id is not None else self.target_user_id
        if tid is not None:
            body["targetUserId"] = int(tid)
        return await self._request("POST", "/lkbx/session/current", json_body=body)

    async def status_snapshot(self) -> dict[str, Any]:
        """Safe status for UI / /api/meta (never includes the token)."""
        out: dict[str, Any] = {
            "configured": self.configured,
            "sync_ready": self.sync_ready,
            "sync_enabled": bool(
                getattr(self.settings, "rad_lockbox_sync_enabled", False)
            ),
            "target_user_id": self.target_user_id,
            "lock_settings_id": self.lock_settings_id,
            "keyholder_ids": list(self.keyholder_ids),
            "is_test_lock": self.is_test_lock,
            "hygiene_unlock": bool(
                getattr(self.settings, "rad_sync_hygiene", True)
            ),
            "session_sync": bool(
                getattr(self.settings, "rad_sync_session_lock", False)
            ),
            "session": None,
            "error": None,
        }
        if not self.configured:
            out["error"] = "RAD_API_TOKEN not set"
            return out
        try:
            out["session"] = await self.get_active_session()
        except Exception as exc:  # noqa: BLE001
            out["error"] = str(exc)
            log.warning("R+D status fetch failed: %s", exc)
        return out


def _unwrap_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


_RAD: RadLockboxClient | None = None


def init_rad_client(settings: Settings) -> RadLockboxClient:
    global _RAD
    _RAD = RadLockboxClient(settings)
    return _RAD


def get_rad_client() -> RadLockboxClient | None:
    return _RAD
