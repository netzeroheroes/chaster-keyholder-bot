import unittest
from unittest.mock import AsyncMock

from app.chaster import ChasterClient
from app.config import Settings
from app.lock_scope import (
    bind_lock_scope,
    current_lock_scope,
    display_key,
    lock_scope_id,
    reset_lock_scope,
    session_id_for,
)
from app.sessions import DisplayMessage, SessionStore


class LockScopeSessionIdTests(unittest.TestCase):
    def tearDown(self) -> None:
        bind_lock_scope(lock_id="", session_id="")

    def test_different_locks_get_different_session_ids(self) -> None:
        a = session_id_for("private", "lockAAA")
        b = session_id_for("private", "lockBBB")
        self.assertNotEqual(a, b)
        self.assertEqual(a, "lock:lockAAA:room:private")
        self.assertEqual(b, "lock:lockBBB:room:private")
        self.assertNotEqual(
            session_id_for("group", "lockAAA"),
            session_id_for("group", "lockBBB"),
        )

    def test_unscoped_keeps_legacy_id(self) -> None:
        self.assertEqual(session_id_for("group"), "room:group")
        self.assertEqual(session_id_for("private"), "room:private")
        self.assertEqual(session_id_for("lockee"), "room:lockee")

    def test_bound_scope_used_when_lock_id_omitted(self) -> None:
        token = bind_lock_scope(lock_id="abc123")
        try:
            self.assertEqual(current_lock_scope(), "abc123")
            self.assertEqual(session_id_for("lockee"), "lock:abc123:room:lockee")
            self.assertEqual(display_key("private"), "lock:abc123:private")
        finally:
            reset_lock_scope(token)

    def test_session_id_fallback_when_lock_id_missing(self) -> None:
        self.assertEqual(lock_scope_id(session_id="_rV6xyz"), "sid-_rV6xyz")
        self.assertNotEqual(
            lock_scope_id(session_id="sessA"),
            lock_scope_id(session_id="sessB"),
        )
        self.assertEqual(lock_scope_id(lock_id="", session_id="dev"), "")


class DisplayIsolationTests(unittest.TestCase):
    def tearDown(self) -> None:
        bind_lock_scope(lock_id="", session_id="")

    def test_two_locks_do_not_share_history(self) -> None:
        store = SessionStore()
        first = bind_lock_scope(lock_id="lock1")
        store.append_display(
            DisplayMessage(
                speaker="Bot", content="hi lock1", room="group", from_bot=True
            )
        )
        store.append(
            session_id_for("group"),
            {"role": "assistant", "content": "hi lock1"},
        )
        reset_lock_scope(first)

        second = bind_lock_scope(lock_id="lock2")
        store.append_display(
            DisplayMessage(
                speaker="Bot", content="hi lock2", room="group", from_bot=True
            )
        )
        msgs2 = store.get_display("group")
        self.assertEqual([m["content"] for m in msgs2], ["hi lock2"])
        self.assertEqual(
            store.get(session_id_for("group")),
            [],
        )
        counts2 = store.display_counts()
        self.assertEqual(counts2.get("group"), 1)
        reset_lock_scope(second)

        again = bind_lock_scope(lock_id="lock1")
        msgs1 = store.get_display("group")
        self.assertEqual([m["content"] for m in msgs1], ["hi lock1"])
        history = store.get(session_id_for("group"))
        self.assertEqual(history[-1]["content"], "hi lock1")
        reset_lock_scope(again)


class ResolveSessionIdTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, *, lock_id: str = "") -> ChasterClient:
        settings = Settings(chaster_lock_id=lock_id)
        return ChasterClient(settings)

    async def test_never_returns_another_locks_session(self) -> None:
        client = self._client()
        client.search_extension_sessions = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"sessionId": "sid-other", "lock": {"_id": "lock-other"}},
                {"sessionId": "sid-mine", "lock": {"_id": "lock-mine"}},
            ]
        )
        sid = await client.resolve_session_id("lock-mine")
        self.assertEqual(sid, "sid-mine")
        with self.assertRaises(RuntimeError) as ctx:
            await client.resolve_session_id("lock-missing")
        self.assertIn("lock-missing", str(ctx.exception))
        self.assertNotIn("sid-other", str(ctx.exception))

    async def test_env_lock_id_does_not_fall_through(self) -> None:
        client = self._client(lock_id="lock-env")
        client.search_extension_sessions = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"sessionId": "sid-other", "lock": {"_id": "lock-other"}},
            ]
        )
        with self.assertRaises(RuntimeError):
            await client.resolve_session_id()

    async def test_no_lock_id_refuses_when_multiple_sessions(self) -> None:
        client = self._client()
        client.search_extension_sessions = AsyncMock(  # type: ignore[method-assign]
            return_value=[
                {"sessionId": "sid-a", "lock": {"_id": "a"}},
                {"sessionId": "sid-b", "lock": {"_id": "b"}},
            ]
        )
        with self.assertRaises(RuntimeError) as ctx:
            await client.resolve_session_id()
        self.assertIn("Multiple", str(ctx.exception))

    async def test_single_session_ok_without_lock_id(self) -> None:
        client = self._client()
        client.search_extension_sessions = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"sessionId": "only-one", "lock": {"_id": "a"}}]
        )
        self.assertEqual(await client.resolve_session_id(), "only-one")


if __name__ == "__main__":
    unittest.main()
