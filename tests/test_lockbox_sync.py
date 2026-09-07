import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.config import Settings
from app.lock_scope import bind_lock_scope, reset_lock_scope
from app.lockbox_sync import (
    chaster_lock_snapshot,
    remaining_seconds_from_lock,
)
from app.rad_lockbox import RadLockboxClient


def _end_in(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class RemainingFromLockTests(unittest.TestCase):
    def test_reads_end_date_on_new_session(self) -> None:
        rem = remaining_seconds_from_lock(
            {"status": "locked", "endDate": _end_in(3600)}
        )
        self.assertIsNotNone(rem)
        self.assertGreater(rem or 0, 3500)
        self.assertLess(rem or 0, 3700)

    def test_missing_end_date_is_none(self) -> None:
        self.assertIsNone(remaining_seconds_from_lock({"status": "locked"}))


class SnapshotUsesThisLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_current_lock_over_stale_env(self) -> None:
        settings = Settings(chaster_lock_id="old-lock")
        chaster = MagicMock()
        chaster.configured = True
        chaster.settings = settings

        async def get_lock(lid: str):
            if lid == "old-lock":
                return {"_id": "old-lock", "status": "archived"}
            if lid == "new-lock":
                return {
                    "_id": "new-lock",
                    "status": "locked",
                    "endDate": _end_in(7200),
                    "isFrozen": False,
                    "displayRemainingTime": True,
                }
            return None

        chaster.get_lock = AsyncMock(side_effect=get_lock)
        chaster.search_extension_sessions = AsyncMock(return_value=[])
        token = bind_lock_scope(lock_id="new-lock")
        try:
            snap = await chaster_lock_snapshot(chaster)
        finally:
            reset_lock_scope(token)
        self.assertIsNotNone(snap)
        self.assertEqual(snap and snap.get("status"), "locked")
        self.assertGreater(int((snap or {}).get("remaining") or 0), 7000)

    async def test_explicit_lock_id_wins(self) -> None:
        settings = Settings(chaster_lock_id="old-lock")
        chaster = MagicMock()
        chaster.configured = True
        chaster.settings = settings
        chaster.get_lock = AsyncMock(
            return_value={
                "_id": "fresh",
                "status": "locked",
                "endDate": _end_in(120),
                "isFrozen": False,
                "displayRemainingTime": True,
            }
        )
        chaster.search_extension_sessions = AsyncMock(return_value=[])
        snap = await chaster_lock_snapshot(chaster, lock_id="fresh")
        self.assertGreater(int((snap or {}).get("remaining") or 0), 60)


class RealLockStartTests(unittest.IsolatedAsyncioTestCase):
    async def test_lock_sends_real_lock_and_token_keyholder(self) -> None:
        settings = Settings(
            rad_api_token="tok",
            rad_lock_settings_id=9,
            rad_is_test_lock=False,
        )
        client = RadLockboxClient(settings)
        client.token_user_id = AsyncMock(return_value=42)  # type: ignore[method-assign]
        client._request = AsyncMock(return_value={"ok": True})  # type: ignore[method-assign]
        await client.lock()
        args, kwargs = client._request.await_args
        self.assertEqual(args[0], "POST")
        body = kwargs["json_body"]
        self.assertEqual(body["action"], "lock")
        self.assertFalse(body["isTestLock"])
        self.assertEqual(body["keyholderIds"], [42])


if __name__ == "__main__":
    unittest.main()
