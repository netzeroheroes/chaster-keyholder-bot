from __future__ import annotations

import json
import logging
from pathlib import Path

from openai.types.chat import ChatCompletionMessageParam

from app.roles import is_bot_display_speaker
from app.scene import SceneState
from app.sessions import DisplayMessage, SessionStore

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCENE_PATH = DATA_DIR / "scene.json"
SESSIONS_PATH = DATA_DIR / "sessions.json"


def save_scene(scene: SceneState, path: Path = SCENE_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(scene.snapshot(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_scene(path: Path = SCENE_PATH) -> SceneState:
    """Load scene. Persona prompts always come from code defaults so updates ship;
    only the active plan and session kit are restored from disk if present.
    """
    from app.scene import DEFAULT_ACTIVE_PLAN, DEFAULT_GROUP_PROMPT, DEFAULT_PRIVATE_PROMPT

    scene = SceneState(
        private_prompt=DEFAULT_PRIVATE_PROMPT,
        group_prompt=DEFAULT_GROUP_PROMPT,
        secret_directives=DEFAULT_ACTIVE_PLAN,
    )
    if not path.is_file():
        save_scene(scene, path)
        return scene
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Failed to load scene")
        save_scene(scene, path)
        return scene
    # Keep Domme-edited plan + kit; refresh persona prompts from latest defaults
    updates: dict = {}
    if raw.get("secret_directives"):
        updates["secret_directives"] = raw["secret_directives"]
    if isinstance(raw.get("session_kinks"), list):
        updates["session_kinks"] = raw["session_kinks"]
    if isinstance(raw.get("session_toys"), list):
        updates["session_toys"] = raw["session_toys"]
    if raw.get("session_mode"):
        updates["session_mode"] = raw["session_mode"]
    if isinstance(raw.get("scene_interview"), dict):
        updates["scene_interview"] = raw["scene_interview"]
    if updates:
        scene.update(**updates)
    save_scene(scene, path)
    return scene


def save_sessions(store: SessionStore, path: Path = SESSIONS_PATH) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(store.export_state(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_sessions(store: SessionStore, path: Path = SESSIONS_PATH) -> None:
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Failed to load sessions")
        return
    sessions = raw.get("sessions") or {}
    display = raw.get("display") or {}
    parsed_sessions: dict[str, list[ChatCompletionMessageParam]] = {}
    for sid, msgs in sessions.items():
        if isinstance(msgs, list):
            parsed_sessions[sid] = msgs  # type: ignore[assignment]
    parsed_display: dict[str, list[DisplayMessage]] = {}
    for room, msgs in display.items():
        if not isinstance(msgs, list):
            continue
        parsed_display[room] = []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            speaker = str(m.get("speaker", "Bot"))
            parsed_display[room].append(
                DisplayMessage(
                    speaker=speaker,
                    content=str(m.get("content", "")),
                    room=str(m.get("room", room)),
                    image_url=m.get("image_url"),
                    from_bot=bool(m.get("from_bot"))
                    or is_bot_display_speaker(speaker),
                )
            )
    store.import_state(parsed_sessions, parsed_display)
