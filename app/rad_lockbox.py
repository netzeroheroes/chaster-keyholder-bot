"""Research & Desire Lockbox Dashboard API client (no AI).

Docs: https://dev.researchanddesire.com/
Base: https://dashboard.researchanddesire.com/api/v1
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
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
        kh = list(keyholder_ids if keyholder_ids is not None else self.keyholder_ids)
        if not kh:
            me = await self.token_user_id()
            if me is not None:
                kh = [me]
        if kh:
            body["keyholderIds"] = [int(x) for x in kh]
        test = bool(self.is_test_lock if is_test_lock is None else is_test_lock)
        # Always send this so a test-lock template cannot silently start a test session.
        body["isTestLock"] = test
        return await self._request("POST", "/lkbx/session/current", json_body=body)

    async def unlock(self, *, target_user_id: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"action": "unlock"}
        tid = target_user_id if target_user_id is not None else self.target_user_id
        if tid is not None:
            body["targetUserId"] = int(tid)
        kh = list(self.keyholder_ids)
        if not kh:
            me = await self.token_user_id()
            if me is not None:
                kh = [me]
        if kh:
            body["keyholderIds"] = [int(x) for x in kh]
        try:
            return await self._request("POST", "/lkbx/session/current", json_body=body)
        except RuntimeError as exc:
            if is_unlock_permission_error(str(exc)):
                raise RuntimeError(unlock_permission_hint()) from exc
            raise

    async def token_user_id(self) -> int | None:
        """R+D user id for the API token (the keyholder on real locks)."""
        for path in ("/users/me", "/me"):
            try:
                data = await self._request("GET", path)
            except Exception:  # noqa: BLE001
                continue
            user = data.get("data")
            if isinstance(user, dict) and user.get("id"):
                try:
                    return int(user["id"])
                except (TypeError, ValueError):
                    continue
        try:
            users = await self.list_users()
        except Exception:  # noqa: BLE001
            return None
        for user in users:
            if user.get("isSelf") or user.get("isCurrent") or user.get("isMe"):
                try:
                    return int(user["id"])
                except (TypeError, ValueError):
                    continue
        if len(users) == 1 and users[0].get("id"):
            try:
                return int(users[0]["id"])
            except (TypeError, ValueError):
                return None
        return None

    async def set_duration(
        self,
        duration_seconds: int,
        *,
        target_user_id: int | None = None,
    ) -> dict[str, Any]:
        """Set remaining time on the active session (Chaster remaining → R+D).

        R+D's PATCH ``duration`` is total lock length from ``startDate``, not
        remaining. Dashboard shows ``endDate - now`` (= start + duration - now).
        So we convert: duration_total = remaining + elapsed_since_start.
        """
        remaining = max(30, int(duration_seconds))
        session = await self.get_active_session(target_user_id=target_user_id)
        total = remaining
        if isinstance(session, dict) and session.get("startDate"):
            try:
                start = datetime.fromisoformat(
                    str(session["startDate"]).replace("Z", "+00:00")
                )
                elapsed = max(
                    0, int((datetime.now(timezone.utc) - start).total_seconds())
                )
                # API hard-cap ~10y on duration field
                total = min(315_360_000, remaining + elapsed)
            except (TypeError, ValueError):
                total = remaining
        body: dict[str, Any] = {"duration": max(30, int(total))}
        tid = target_user_id if target_user_id is not None else self.target_user_id
        params: dict[str, Any] = {}
        if tid is not None:
            params["targetUserId"] = int(tid)
        return await self._request(
            "PATCH",
            "/lkbx/session/current",
            json_body=body,
            params=params or None,
        )

    @staticmethod
    def remaining_from_session(session: dict[str, Any] | None) -> int | None:
        """Dashboard-visible remaining seconds from endDate (not the duration field)."""
        if not isinstance(session, dict):
            return None
        end_raw = session.get("endDate")
        if not end_raw:
            return None
        try:
            end = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00"))
            rem = int((end - datetime.now(timezone.utc)).total_seconds())
            return rem if rem > 0 else 0
        except (TypeError, ValueError):
            return None

    async def status_snapshot(self) -> dict[str, Any]:
        """Safe status for UI / /api/meta (never includes the token)."""
        out: dict[str, Any] = {
            "configured": self.configured,
            "sync_ready": self.sync_ready or self.configured,
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
            "manual_only": bool(
                getattr(self.settings, "rad_manual_only", False)
            ),
            "time_source": (
                "manual"
                if getattr(self.settings, "rad_manual_only", False)
                else "chaster"
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


UNLOCK_PERMISSION_HINT = (
    "R+D will not unlock this real lock from this API token. "
    "Use the keyholder's Ultra token, set RAD_TARGET_USER_ID to the lockee, "
    "and RAD_KEYHOLDER_IDS to the keyholder's R+D user id "
    "(or leave it empty so the token owner is the keyholder). "
    "Linked Chaster accounts can also unlock if that link is active on this session."
)


def is_unlock_permission_error(err: str) -> bool:
    text = (err or "").lower()
    return "only keyholders" in text or "linked chaster" in text or (
        "test lock" in text and "unlock" in text
    )


def unlock_permission_hint() -> str:
    return UNLOCK_PERMISSION_HINT


def session_is_test_lock(session: dict[str, Any] | None) -> bool | None:
    if not isinstance(session, dict):
        return None
    for key in ("isTestLock", "testLock", "is_test_lock"):
        if key in session:
            return bool(session.get(key))
    return None


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


def summarize_lockbox(snap: dict[str, Any] | None) -> dict[str, Any]:
    """Short UI/model view: is the physical box locked?"""
    data = snap if isinstance(snap, dict) else {}
    configured = bool(data.get("configured"))
    sess = data.get("session") if isinstance(data.get("session"), dict) else None
    state = str((sess or {}).get("lockState") or "").lower()
    active = bool((sess or {}).get("isActive"))
    open_states = {
        "unlocked",
        "completed",
        "abandoned",
        "open",
        "idle",
    }
    if not configured:
        label = "not configured"
        locked = None
    elif not sess:
        label = "no session"
        locked = None
    elif active and state not in open_states and state:
        label = "LOCKED"
        locked = True
    else:
        label = "OPEN"
        locked = False
    return {
        "configured": configured,
        "locked": locked,
        "lock_state": state or "unknown",
        "active": active,
        "label": label,
        "error": data.get("error"),
    }


def get_rad_client() -> RadLockboxClient | None:
    return _RAD
