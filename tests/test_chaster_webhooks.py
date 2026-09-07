import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.chaster_webhooks import (
    action_log_matches_lock,
    extract_lock_id,
    handle_chaster_webhook,
    parse_webhook_body,
)
from app.config import Settings
from app.lock_watch import (
    _load_state,
    _should_react,
    fetch_new_events,
    mark_history_events_seen,
    watched_lock_ids,
)


def _official_action_log_body(
    *,
    lock: str | dict,
    lock_type: str = "time_changed",
    prefix: str = "default",
    session_id: str = "sess-new",
    event_id: str = "evt-1",
) -> dict:
    return {
        "payload": {
            "event": "action_log.created",
            "requestId": "req-1",
            "data": {
                "sessionId": session_id,
                "actionLog": {
                    "_id": event_id,
                    "type": lock_type,
                    "prefix": prefix,
                    "lock": lock,
                    "role": "keyholder",
                    "title": "Time changed",
                    "description": "+1 hour",
                    "payload": {"duration": 3600},
                    "createdAt": "2026-09-07T00:00:00.000Z",
                },
            },
        }
    }


class ExtractLockIdTests(unittest.TestCase):
    def test_string_lock(self) -> None:
        self.assertEqual(extract_lock_id("lock-abc"), "lock-abc")

    def test_dict_lock_underscore_id(self) -> None:
        self.assertEqual(extract_lock_id({"_id": "lock-dict"}), "lock-dict")

    def test_dict_lock_id_field(self) -> None:
        self.assertEqual(extract_lock_id({"id": "lock-id"}), "lock-id")

    def test_nested_lock_preferred_over_event_id(self) -> None:
        self.assertEqual(
            extract_lock_id({"_id": "event-id", "lock": "real-lock"}),
            "real-lock",
        )

    def test_empty(self) -> None:
        self.assertEqual(extract_lock_id(None), "")
        self.assertEqual(extract_lock_id({}), "")


class ParseWebhookTests(unittest.TestCase):
    def test_official_payload_unwrap(self) -> None:
        parsed = parse_webhook_body(
            _official_action_log_body(lock="new-lock", lock_type="default.time_changed")
        )
        self.assertEqual(parsed["event"], "action_log.created")
        self.assertEqual(parsed["session_id"], "sess-new")
        self.assertEqual(parsed["lock_id"], "new-lock")
        self.assertEqual(parsed["action_log"]["type"], "default.time_changed")

    def test_dict_lock_on_action_log(self) -> None:
        parsed = parse_webhook_body(
            _official_action_log_body(lock={"_id": "obj-lock", "status": "locked"})
        )
        self.assertEqual(parsed["lock_id"], "obj-lock")

    def test_session_updated_nested_lock(self) -> None:
        parsed = parse_webhook_body(
            {
                "payload": {
                    "event": "extension_session.updated",
                    "data": {
                        "sessionId": "sess-2",
                        "session": {"lock": {"_id": "from-session"}},
                    },
                }
            }
        )
        self.assertEqual(parsed["event"], "extension_session.updated")
        self.assertEqual(parsed["lock_id"], "from-session")
        self.assertEqual(parsed["session_id"], "sess-2")


class MatchLockTests(unittest.TestCase):
    def test_new_lock_not_ignored_when_env_is_stale(self) -> None:
        self.assertTrue(
            action_log_matches_lock({"lock": "brand-new"}, lock_id="old-env-lock")
        )
        self.assertTrue(
            action_log_matches_lock(
                {"lock": {"_id": "brand-new"}}, lock_id="old-env-lock"
            )
        )


class ShouldReactTests(unittest.TestCase):
    def test_prefixed_time_changed(self) -> None:
        self.assertTrue(
            _should_react(
                {
                    "type": "default.time_changed",
                    "prefix": "default",
                    "role": "keyholder",
                }
            )
        )

    def test_plain_time_changed(self) -> None:
        self.assertTrue(
            _should_react({"type": "time_changed", "role": "keyholder"})
        )

    def test_freeze(self) -> None:
        self.assertTrue(
            _should_react({"type": "default.lock_frozen", "prefix": "default"})
        )


class HandleWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_action_log_on_new_lock_queues_react(self) -> None:
        settings = Settings(chaster_lock_id="old-lock")
        agent = MagicMock()
        store = MagicMock()
        scene = MagicMock()
        memory = MagicMock()
        chaster = MagicMock()
        react = AsyncMock()
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch(
                "app.lock_store.lock_data_dir",
                side_effect=lambda scope: Path(tmp) / scope,
            ),
            patch("app.lock_watch.react_to_lock_events", react),
        ):
            out = await handle_chaster_webhook(
                settings=settings,
                body=_official_action_log_body(
                    lock="brand-new-lock",
                    lock_type="default.time_changed",
                    session_id="sess-brand",
                ),
                chaster=chaster,
                rad=None,
                agent=agent,
                store=store,
                scene=scene,
                memory=memory,
            )
            await asyncio.sleep(0)
        self.assertTrue(out["ok"])
        self.assertEqual(out["lock_id"], "brand-new-lock")
        self.assertEqual(out["action_type"], "time_changed")
        self.assertIn("ai_react_queued", out["handled"])
        self.assertNotIn("ignored_other_lock", out["handled"])
        react.assert_awaited()
        events = react.await_args.kwargs["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["lock"], "brand-new-lock")

    async def test_session_updated_fetches_history(self) -> None:
        settings = Settings(chaster_lock_id="old-lock")
        agent = MagicMock()
        store = MagicMock()
        scene = MagicMock()
        memory = MagicMock()
        chaster = MagicMock()
        history = [
            {
                "_id": "hist-2",
                "type": "time_changed",
                "lock": "live-lock",
                "role": "keyholder",
            }
        ]
        fetch = AsyncMock(return_value=history)
        react = AsyncMock()
        with (
            patch("app.lock_watch.fetch_new_events", fetch),
            patch("app.lock_watch.react_to_lock_events", react),
        ):
            out = await handle_chaster_webhook(
                settings=settings,
                body={
                    "payload": {
                        "event": "extension_session.updated",
                        "data": {
                            "sessionId": "sess-live",
                            "lock": {"_id": "live-lock"},
                        },
                    }
                },
                chaster=chaster,
                rad=None,
                agent=agent,
                store=store,
                scene=scene,
                memory=memory,
            )
            await asyncio.sleep(0)
        self.assertIn("session_event", out["handled"])
        self.assertIn("ai_react_queued", out["handled"])
        self.assertEqual(out["lock_id"], "live-lock")
        fetch.assert_awaited()
        self.assertEqual(fetch.await_args.kwargs.get("lock_id"), "live-lock")
        react.assert_awaited()


class WatchStateTests(unittest.TestCase):
    def test_per_lock_watermarks_do_not_collide(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def fake_dir(scope: str) -> Path:
                path = Path(tmp) / scope
                path.mkdir(parents=True, exist_ok=True)
                return path

            with patch("app.lock_store.lock_data_dir", side_effect=fake_dir):
                mark_history_events_seen(
                    [{"_id": "aaa111", "lock": "L1"}], lock_id="L1"
                )
                mark_history_events_seen(
                    [{"_id": "bbb222", "lock": "L2"}], lock_id="L2"
                )
                self.assertEqual(_load_state("L1").get("last_id"), "aaa111")
                self.assertEqual(_load_state("L2").get("last_id"), "bbb222")
                self.assertNotEqual(_load_state("L1"), _load_state("L2"))


class WatchedLockIdsTests(unittest.IsolatedAsyncioTestCase):
    async def test_includes_session_locks_not_just_env(self) -> None:
        settings = Settings(chaster_lock_id="old-lock")
        chaster = MagicMock()
        chaster.settings = settings
        chaster.search_extension_sessions = AsyncMock(
            return_value=[
                {"sessionId": "s1", "lock": {"_id": "new-lock"}},
                {"sessionId": "s2", "lock": "other-lock"},
            ]
        )
        ids = await watched_lock_ids(chaster)
        self.assertIn("new-lock", ids)
        self.assertIn("other-lock", ids)
        self.assertIn("old-lock", ids)


class FetchNewEventsTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_requested_lock_not_env(self) -> None:
        settings = Settings(chaster_lock_id="env-lock")
        chaster = MagicMock()
        chaster.settings = settings
        chaster.get_lock_history = AsyncMock(
            return_value=[{"_id": "tip", "type": "time_changed", "lock": "asked"}]
        )
        with tempfile.TemporaryDirectory() as tmp:
            def fake_dir(scope: str) -> Path:
                path = Path(tmp) / scope
                path.mkdir(parents=True, exist_ok=True)
                return path

            with patch("app.lock_store.lock_data_dir", side_effect=fake_dir):
                first = await fetch_new_events(chaster, lock_id="asked")
                self.assertEqual(first, [])
                chaster.get_lock_history.assert_awaited()
                self.assertEqual(chaster.get_lock_history.await_args.args[0], "asked")
                chaster.get_lock_history = AsyncMock(
                    return_value=[
                        {"_id": "newer", "type": "time_changed", "lock": "asked"},
                        {"_id": "tip", "type": "locked", "lock": "asked"},
                    ]
                )
                second = await fetch_new_events(chaster, lock_id="asked")
        self.assertEqual([ev["_id"] for ev in second], ["newer"])


if __name__ == "__main__":
    unittest.main()
