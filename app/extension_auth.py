"""Chaster partner-extension session auth (mainToken / config token)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Literal

from app.chaster import ChasterClient

log = logging.getLogger(__name__)

ExtRole = Literal["wearer", "keyholder", "unknown"]


@dataclass
class ExtSession:
    main_token: str
    role: ExtRole
    user_id: str
    session_id: str
    lock_id: str
    wearer_username: str
    keyholder_username: str
    config: dict[str, Any]
    fetched_at: float

    @property
    def app_role(self) -> Literal["domme", "sub"]:
        return "domme" if self.role == "keyholder" else "sub"


class ExtensionAuthCache:
    """Short-lived cache so we don't hit Chaster on every poll."""

    def __init__(self, ttl_seconds: int = 120) -> None:
        self.ttl = ttl_seconds
        self._lock = Lock()
        self._by_token: dict[str, ExtSession] = {}

    def get(self, main_token: str) -> ExtSession | None:
        with self._lock:
            sess = self._by_token.get(main_token)
            if not sess:
                return None
            if time.time() - sess.fetched_at > self.ttl:
                self._by_token.pop(main_token, None)
                return None
            return sess

    def put(self, sess: ExtSession) -> None:
        with self._lock:
            self._by_token[sess.main_token] = sess


def parse_ext_role(raw: str | None) -> ExtRole:
    r = (raw or "").strip().lower()
    if r in ("wearer", "keyholder"):
        return r  # type: ignore[return-value]
    return "unknown"


async def resolve_main_token(
    chaster: ChasterClient,
    main_token: str,
    *,
    cache: ExtensionAuthCache,
) -> ExtSession:
    token = (main_token or "").strip()
    if not token:
        raise ValueError("mainToken missing")
    cached = cache.get(token)
    if cached:
        return cached

    data = await chaster.exchange_main_token(token)
    if not isinstance(data, dict):
        raise RuntimeError("Invalid mainToken response")

    session = data.get("session") or {}
    lock = session.get("lock") or {}
    user = lock.get("user") or {}
    kh = lock.get("keyholder") or {}
    sess = ExtSession(
        main_token=token,
        role=parse_ext_role(str(data.get("role") or "")),
        user_id=str(data.get("userId") or ""),
        session_id=str(session.get("_id") or session.get("sessionId") or ""),
        lock_id=str(lock.get("_id") or lock.get("id") or ""),
        wearer_username=str(user.get("username") or ""),
        keyholder_username=str(kh.get("username") or ""),
        config=dict(session.get("config") or {}),
        fetched_at=time.time(),
    )
    if sess.role == "unknown":
        raise RuntimeError("mainToken role unknown — open from Chaster")
    cache.put(sess)
    log.info(
        "Ext session role=%s lock=%s wearer=%s",
        sess.role,
        sess.lock_id,
        sess.wearer_username,
    )
    return sess


def public_session_view(sess: ExtSession) -> dict[str, Any]:
    return {
        "role": sess.role,
        "app_role": sess.app_role,
        "wearer_username": sess.wearer_username,
        "keyholder_username": sess.keyholder_username,
        "lock_id": sess.lock_id,
        "session_id": sess.session_id,
        "config": sess.config,
    }
