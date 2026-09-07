"""Load memory and scene isolated per lock."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from app.memory import LongTermMemory
from app.persist import DATA_DIR, load_scene, save_scene
from app.scene import SceneState

_LOCKS = DATA_DIR / "locks"
_mem: dict[str, LongTermMemory] = {}
_scene: dict[str, SceneState] = {}
_guard = Lock()


def lock_data_dir(scope: str) -> Path:
    return _LOCKS / scope


def memory_for(scope: str, default: LongTermMemory) -> LongTermMemory:
    key = (scope or "").strip()
    if not key:
        return default
    with _guard:
        cached = _mem.get(key)
        if cached is not None:
            return cached
        path = lock_data_dir(key) / "memory.json"
        mem = LongTermMemory.load(path)
        mem._path = path  # type: ignore[attr-defined]
        _mem[key] = mem
        return mem


def scene_for(scope: str, default: SceneState) -> SceneState:
    key = (scope or "").strip()
    if not key:
        return default
    with _guard:
        cached = _scene.get(key)
        if cached is not None:
            return cached
        path = lock_data_dir(key) / "scene.json"
        scn = load_scene(path)
        scn._path = path  # type: ignore[attr-defined]
        _scene[key] = scn
        return scn


def persist_scene(scene: SceneState) -> None:
    path = getattr(scene, "_path", None)
    save_scene(scene, path) if path is not None else save_scene(scene)


def clear_lock_store_cache() -> None:
    with _guard:
        _mem.clear()
        _scene.clear()
