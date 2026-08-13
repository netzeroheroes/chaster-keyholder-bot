from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOKEN_PATH = DATA_DIR / "chaster_token.json"

AUTH_URL = "https://sso.chaster.app/auth/realms/app/protocol/openid-connect/auth"
TOKEN_URL = "https://sso.chaster.app/auth/realms/app/protocol/openid-connect/token"
API_BASE = "https://api.chaster.app"

DEFAULT_SCOPES = "profile locks keyholder"


class ChasterClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.chaster_client_id
            and self.settings.chaster_client_secret
        ) or bool(self.settings.chaster_access_token)

    def authorization_url(self, state: str | None = None) -> tuple[str, str]:
        state = state or secrets.token_urlsafe(24)
        params = {
            "client_id": self.settings.chaster_client_id,
            "redirect_uri": self.settings.chaster_redirect_uri,
            "response_type": "code",
            "scope": self.settings.chaster_scopes or DEFAULT_SCOPES,
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}", state

    def _load_token(self) -> dict[str, Any]:
        if self.settings.chaster_access_token:
            return {
                "access_token": self.settings.chaster_access_token,
                "expires_at": time.time() + 3600,
                "source": "env",
            }
        if not TOKEN_PATH.is_file():
            return {}
        try:
            return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_token(self, data: dict[str, Any]) -> None:
        expires_in = int(data.get("expires_in") or 300)
        payload = {
            "access_token": data.get("access_token"),
            "refresh_token": data.get("refresh_token"),
            "expires_at": time.time() + max(30, expires_in - 30),
            "scope": data.get("scope"),
            "token_type": data.get("token_type", "bearer"),
        }
        TOKEN_PATH.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

    async def exchange_code(self, code: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.settings.chaster_client_id,
                    "client_secret": self.settings.chaster_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.chaster_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Chaster token exchange failed ({response.status_code}): {response.text[:400]}"
            )
        data = response.json()
        self._save_token(data)
        return data

    async def _refresh(self, refresh_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TOKEN_URL,
                data={
                    "client_id": self.settings.chaster_client_id,
                    "client_secret": self.settings.chaster_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Chaster refresh failed ({response.status_code}): {response.text[:400]}"
            )
        data = response.json()
        self._save_token(data)
        return data

    async def get_access_token(self) -> str:
        tok = self._load_token()
        access = tok.get("access_token")
        if not access:
            raise RuntimeError(
                "Chaster not linked. Open /api/chaster/login as Domme, "
                "or set CHASTER_ACCESS_TOKEN (developer token)."
            )
        if tok.get("source") == "env":
            return str(access)
        if float(tok.get("expires_at") or 0) > time.time():
            return str(access)
        refresh = tok.get("refresh_token")
        if not refresh:
            raise RuntimeError("Chaster token expired — login again via /api/chaster/login")
        data = await self._refresh(str(refresh))
        return str(data["access_token"])

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        token = await self.get_access_token()
        url = f"{API_BASE}{path}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.request(
                method, url, headers=headers, json=json_body
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"Chaster {method} {path} failed ({response.status_code}): {response.text[:500]}"
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def status(self) -> dict[str, Any]:
        tok = self._load_token()
        linked = bool(tok.get("access_token"))
        out: dict[str, Any] = {
            "configured": self.configured,
            "linked": linked,
            "redirect_uri": self.settings.chaster_redirect_uri,
            "scopes": self.settings.chaster_scopes or DEFAULT_SCOPES,
            "client_id": self.settings.chaster_client_id,
        }
        if not linked:
            return out
        try:
            me = await self._request("GET", "/auth/profile")
            out["profile"] = {
                "username": (me or {}).get("username"),
                "id": (me or {}).get("_id") or (me or {}).get("id"),
            }
        except Exception as exc:  # noqa: BLE001
            out["profile_error"] = str(exc)
        try:
            lock_id = (self.settings.chaster_lock_id or "").strip()
            lock = await self.get_lock(lock_id) if lock_id else None
            if not lock:
                sessions = await self.search_extension_sessions()
                if sessions:
                    lock = (sessions[0].get("lock") or None)
                    if isinstance(lock, dict) and lock.get("_id"):
                        lock = await self.get_lock(str(lock["_id"])) or lock
            if lock:
                kh = lock.get("keyholder") or {}
                wearer = lock.get("user") or {}
                out["lock"] = {
                    "lock_id": lock.get("_id") or lock.get("id"),
                    "status": lock.get("status"),
                    "is_frozen": lock.get("isFrozen"),
                    "display_remaining_time": lock.get("displayRemainingTime"),
                    "end_date": lock.get("endDate"),
                    "wearer_username": wearer.get("username"),
                    "keyholder_username": kh.get("username"),
                    "keyholder_id": kh.get("_id") or kh.get("id"),
                }
                out["domme_username"] = kh.get("username") or ""
                out["sub_username"] = wearer.get("username") or ""
        except Exception as exc:  # noqa: BLE001
            out["lock_error"] = str(exc)
        return out

    async def set_keyholder_note(self, lock_id: str, content: str) -> None:
        await self._request(
            "PUT",
            f"/keyholder/notes/lock/{lock_id}",
            json_body={"content": (content or "").strip()[:10000]},
        )

    async def get_user_profile_overview(self, username: str) -> dict[str, Any]:
        """Public profile: gender, sexuality, pronouns, kink profile, etc."""
        handle = (username or "").strip().lstrip("@")
        if not handle:
            return {}
        data = await self._request("GET", f"/user-profile/{handle}/overview")
        if not isinstance(data, dict):
            return {}
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        kink = data.get("kinkProfile") if isinstance(data.get("kinkProfile"), dict) else {}
        return {
            "username": str(user.get("username") or handle),
            "gender": str(user.get("gender") or "").strip(),
            "sexual_orientation": str(user.get("sexualOrientation") or "").strip(),
            "pronouns": str(user.get("pronouns") or "").strip(),
            "chaster_role": str(user.get("role") or "").strip(),
            "age": user.get("age"),
            "description": str(user.get("description") or "").strip(),
            "kinkProfile": dict(kink),
        }

    async def get_user_kink_profile(self, username: str) -> dict[str, Any]:
        """Kink/toys list; prefers overview endpoint, falls back to legacy details."""
        handle = (username or "").strip().lstrip("@")
        if not handle:
            return {}
        try:
            overview = await self.get_user_profile_overview(handle)
            kink = overview.get("kinkProfile") if isinstance(overview, dict) else None
            if isinstance(kink, dict) and (kink.get("kinks") or kink.get("toys") or kink.get("bio")):
                return dict(kink)
        except Exception:  # noqa: BLE001
            log.debug("Overview kink fetch failed for %s; trying legacy", handle, exc_info=True)
        data = await self._request("GET", f"/users/profile/{handle}/details")
        if not isinstance(data, dict):
            return {}
        return dict(data.get("kinkProfile") or {})

    async def search_wearers(self, *, status: str = "locked", limit: int = 20) -> dict:
        return await self._request(
            "POST",
            "/keyholder/locks/search",
            json_body={"status": status, "page": 0, "limit": limit},
        )

    async def list_own_locks(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/locks")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.get("locks") or [])
        return []

    async def get_lock(self, lock_id: str) -> dict[str, Any] | None:
        data = await self._request("GET", f"/locks/{lock_id}")
        return data if isinstance(data, dict) else None

    async def search_extension_sessions(
        self,
        *,
        extension_slug: str | None = None,
        status: str = "locked",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        slug = (extension_slug or self.settings.chaster_extension_slug or "").strip()
        if not slug:
            return []
        data = await self._request(
            "POST",
            "/api/extensions/sessions/search",
            json_body={
                "extensionSlug": slug,
                "status": status,
                "limit": limit,
            },
        )
        if isinstance(data, dict):
            return list(data.get("results") or [])
        return []

    async def resolve_session_id(self, lock_id: str | None = None) -> str:
        preferred_lock = (lock_id or self.settings.chaster_lock_id or "").strip()
        sessions = await self.search_extension_sessions()
        if preferred_lock:
            for session in sessions:
                lock = session.get("lock") or {}
                if str(lock.get("_id") or lock.get("id") or "") == preferred_lock:
                    sid = session.get("sessionId")
                    if sid:
                        return str(sid)
        for session in sessions:
            sid = session.get("sessionId")
            if sid:
                return str(sid)
        raise RuntimeError(
            "No Duo Domme extension session found. "
            "Is the extension on an active lock?"
        )

    async def session_action(
        self,
        name: str,
        params: Any = None,
        *,
        session_id: str | None = None,
        lock_id: str | None = None,
    ) -> None:
        sid = session_id or await self.resolve_session_id(lock_id)
        action: dict[str, Any] = {"name": name}
        if params is not None:
            action["params"] = params
        await self._request(
            "POST",
            f"/api/extensions/sessions/{sid}/action",
            json_body={"action": action},
        )

    async def update_time(self, lock_id: str, duration_seconds: int) -> None:
        """Add/remove time via Duo Domme partner extension (required for this lock)."""
        seconds = int(duration_seconds)
        if seconds == 0:
            return
        if seconds > 0:
            await self.session_action("add_time", seconds, lock_id=lock_id)
        else:
            await self.session_action("remove_time", abs(seconds), lock_id=lock_id)

    async def set_freeze(self, lock_id: str, is_frozen: bool) -> None:
        await self.session_action(
            "freeze" if is_frozen else "unfreeze",
            lock_id=lock_id,
        )

    async def set_display_remaining_time(self, lock_id: str, display: bool) -> None:
        await self.session_action(
            "set_display_remaining_time",
            bool(display),
            lock_id=lock_id,
        )

    async def pillory(
        self,
        lock_id: str,
        *,
        duration_seconds: int = 300,
        reason: str = "",
    ) -> None:
        params: dict[str, Any] = {
            "duration": max(300, min(int(duration_seconds), 86400)),
        }
        if reason:
            params["reason"] = reason[:500]
        await self.session_action("pillory", params, lock_id=lock_id)

    async def get_temporary_opening_status(self, lock_id: str) -> dict[str, Any]:
        lid = (lock_id or "").strip()
        data = await self._request("GET", f"/extensions/temporary-opening/{lid}")
        return data if isinstance(data, dict) else {}

    async def open_temporary_opening(
        self, lock_id: str, *, actor: str = "keyholder"
    ) -> None:
        """Hygiene opening — requires temporary-opening on the lock."""
        sid = await self.resolve_session_id(lock_id)
        role = actor if actor in ("wearer", "keyholder", "extension") else "keyholder"
        await self._request(
            "POST",
            f"/api/extensions/sessions/{sid}/temporary-opening/open",
            json_body={"actor": role},
        )

    async def request_verification_picture(
        self, lock_id: str, *, actor: str = "keyholder"
    ) -> None:
        """Request verification picture — requires verification-picture on the lock."""
        sid = await self.resolve_session_id(lock_id)
        role = actor if actor in ("wearer", "keyholder", "extension") else "keyholder"
        await self._request(
            "POST",
            f"/api/extensions/sessions/{sid}/verification-picture/request",
            json_body={"actor": role},
        )

    async def assign_task(
        self,
        lock_id: str,
        *,
        task: str,
        points: int = 1,
        verification_required: bool = False,
        duration: int = 0,
        actor: str = "keyholder",
    ) -> None:
        """Assign a Tasks-extension task — requires tasks on the lock."""
        sid = await self.resolve_session_id(lock_id)
        role = actor if actor in ("wearer", "keyholder", "extension") else "keyholder"
        item: dict[str, Any] = {
            "task": (task or "").strip()[:500],
            "points": max(0, int(points)),
        }
        if verification_required:
            item["verificationRequired"] = True
        if duration and int(duration) >= 60:
            item["duration"] = int(duration)
        await self._request(
            "POST",
            f"/api/extensions/sessions/{sid}/tasks/assign",
            json_body={"task": item, "actor": role},
        )

    async def update_extension_config(
        self,
        lock_id: str,
        slug: str,
        config_updates: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Merge config updates into one extension; keep all others (incl. duo-domme)."""
        lid = (lock_id or "").strip()
        want = (slug or "").strip()
        current = await self.list_lock_extensions(lid)
        body: list[dict[str, Any]] = []
        found = False
        for e in current:
            cfg = dict(e.get("config") or {})
            if str(e.get("slug") or "") == want:
                cfg.update(config_updates)
                found = True
            body.append(
                {
                    "slug": e.get("slug"),
                    "config": cfg,
                    "mode": e.get("mode") or "unlimited",
                    "regularity": e.get("regularity") or 3600,
                }
            )
        if not found:
            raise RuntimeError(
                f"Extension `{want}` is not on the lock — activate it first."
            )
        await self.replace_lock_extensions(lid, body)
        return await self.list_lock_extensions(lid)

    async def exchange_main_token(self, main_token: str) -> dict[str, Any]:
        """Validate iframe mainToken → role + session (partner extension)."""
        token = (main_token or "").strip()
        if not token:
            raise RuntimeError("mainToken missing")
        data = await self._request(
            "GET", f"/api/extensions/auth/sessions/{token}"
        )
        return data if isinstance(data, dict) else {}

    async def get_partner_configuration(self, configuration_token: str) -> dict[str, Any]:
        token = (configuration_token or "").strip()
        if not token:
            raise RuntimeError("partnerConfigurationToken missing")
        data = await self._request(
            "GET", f"/api/extensions/configurations/{token}"
        )
        return data if isinstance(data, dict) else {}

    async def put_partner_configuration(
        self, configuration_token: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        token = (configuration_token or "").strip()
        if not token:
            raise RuntimeError("partnerConfigurationToken missing")
        data = await self._request(
            "PUT",
            f"/api/extensions/configurations/{token}",
            json_body={"config": config},
        )
        return data if isinstance(data, dict) else {"config": config}

    async def patch_extension_session(
        self, session_id: str, *, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update a running extension session's config (keyholder session settings)."""
        sid = (session_id or "").strip()
        if not sid:
            raise RuntimeError("sessionId missing")
        data = await self._request(
            "PATCH",
            f"/api/extensions/sessions/{sid}",
            json_body={"config": config},
        )
        return data if isinstance(data, dict) else {"config": config}

    async def post_custom_log(
        self,
        *,
        title: str,
        description: str = "",
        role: str = "keyholder",
        icon: str = "comment",
        color: str = "#e08763",
        lock_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Post to lock history via Duo Domme session (often push-notifies the lockee)."""
        sid = session_id or await self.resolve_session_id(lock_id)
        body: dict[str, Any] = {
            "title": (title or "Message").strip()[:200],
            "role": role if role in ("wearer", "keyholder", "extension") else "keyholder",
        }
        desc = (description or "").strip()
        if desc:
            body["description"] = desc[:2000]
        if icon:
            body["icon"] = icon.strip()[:80]
        if color:
            body["color"] = color.strip()[:20]
        await self._request(
            "POST",
            f"/api/extensions/sessions/{sid}/logs/custom",
            json_body=body,
        )

    async def get_lock_history(
        self, lock_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Recent lock action log (time changes, freezes, extensions, share opens…)."""
        lid = (lock_id or "").strip()
        if not lid:
            return []
        data = await self._request(
            "POST",
            f"/locks/{lid}/history",
            json_body={"limit": max(1, min(50, int(limit)))},
        )
        if isinstance(data, dict):
            return list(data.get("results") or [])
        if isinstance(data, list):
            return data
        return []

    async def list_lock_extensions(self, lock_id: str | None = None) -> list[dict[str, Any]]:
        """Extensions currently on the lock (Duo Domme, Jigsaw, Hygiene Opening, …)."""
        lid = (lock_id or self.settings.chaster_lock_id or "").strip()
        lock = await self.get_lock(lid) if lid else None
        if not lock:
            return []
        out: list[dict[str, Any]] = []
        for ext in lock.get("extensions") or []:
            if not isinstance(ext, dict):
                continue
            out.append(
                {
                    "id": ext.get("_id") or ext.get("id"),
                    "slug": ext.get("slug") or ext.get("name"),
                    "mode": ext.get("mode"),
                    "regularity": ext.get("regularity"),
                    "display_name": ext.get("displayName")
                    or ext.get("name")
                    or ext.get("slug"),
                    "config": ext.get("config") or {},
                }
            )
        return out

    async def replace_lock_extensions(
        self,
        lock_id: str,
        extensions: list[dict[str, Any]],
    ) -> None:
        """
        Replace the lock's extension list (trusted keyholder).
        ALWAYS include duo-domme or the bot loses control.
        Body items: slug, config, mode, regularity — no _id.
        """
        lid = (lock_id or "").strip()
        if not lid:
            raise RuntimeError("lock_id required")
        clean: list[dict[str, Any]] = []
        for ext in extensions:
            if not isinstance(ext, dict):
                continue
            slug = str(ext.get("slug") or "").strip()
            if not slug:
                continue
            clean.append(
                {
                    "slug": slug,
                    "config": ext.get("config")
                    if isinstance(ext.get("config"), dict)
                    else {},
                    "mode": str(ext.get("mode") or "unlimited"),
                    "regularity": int(ext.get("regularity") or 3600),
                }
            )
        if not any(e["slug"] == "duo-domme" for e in clean):
            clean.insert(
                0,
                {
                    "slug": "duo-domme",
                    "config": {},
                    "mode": "unlimited",
                    "regularity": 3600,
                },
            )
        await self._request(
            "POST",
            f"/locks/{lid}/extensions",
            json_body={"extensions": clean},
        )

    async def activate_extension(
        self,
        lock_id: str,
        slug: str,
        *,
        config: dict[str, Any] | None = None,
        mode: str | None = None,
        regularity: int | None = None,
    ) -> list[dict[str, Any]]:
        """Add an extension if missing; never drop duo-domme or existing plugins."""
        lid = (lock_id or "").strip()
        want = (slug or "").strip()
        if not lid or not want:
            raise RuntimeError("lock_id and slug required")
        current = await self.list_lock_extensions(lid)
        if any(str(e.get("slug") or "") == want for e in current):
            return current
        # Prefer catalog defaults when available
        default_config: dict[str, Any] = {}
        default_mode = mode or "unlimited"
        default_reg = regularity or 3600
        try:
            catalog = await self._request("GET", "/extensions")
            if isinstance(catalog, list):
                for item in catalog:
                    if isinstance(item, dict) and item.get("slug") == want:
                        if isinstance(item.get("defaultConfig"), dict):
                            default_config = dict(item["defaultConfig"])
                        modes = item.get("availableModes") or []
                        if modes and not mode:
                            default_mode = str(modes[0])
                        if item.get("defaultRegularity") and not regularity:
                            default_reg = int(item["defaultRegularity"])
                        break
        except Exception:  # noqa: BLE001
            log.exception("Extension catalog lookup failed for %s", want)
        body = [
            {
                "slug": e.get("slug"),
                "config": e.get("config") or {},
                "mode": e.get("mode") or "unlimited",
                "regularity": e.get("regularity") or 3600,
            }
            for e in current
        ]
        body.append(
            {
                "slug": want,
                "config": config if isinstance(config, dict) else default_config,
                "mode": default_mode,
                "regularity": int(default_reg),
            }
        )
        await self.replace_lock_extensions(lid, body)
        return await self.list_lock_extensions(lid)

    def summarize_locks(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        from datetime import datetime, timezone

        if isinstance(payload, list):
            locks = payload
        else:
            locks = payload.get("locks") or []
        summary = []
        now = datetime.now(timezone.utc)
        for lock in locks:
            user = lock.get("user") or {}
            rem = None
            end = lock.get("endDate")
            if end:
                end_dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                rem = int((end_dt - now).total_seconds())
            summary.append(
                {
                    "lock_id": lock.get("_id") or lock.get("id"),
                    "status": lock.get("status"),
                    "is_frozen": lock.get("isFrozen"),
                    "username": user.get("username"),
                    "user_id": user.get("_id") or user.get("id"),
                    "title": lock.get("title") or lock.get("sharedLockName"),
                    "end_date": end,
                    "remaining_seconds": rem,
                }
            )
        return summary
