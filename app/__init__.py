"""Chatbot application package."""

__all__ = [
    "ChatAgent",
    "Settings",
    "SessionStore",
    "build_default_registry",
    "create_api",
    "get_settings",
]


def __getattr__(name: str):
    if name == "ChatAgent":
        from app.agent import ChatAgent

        return ChatAgent
    if name == "Settings":
        from app.config import Settings

        return Settings
    if name == "get_settings":
        from app.config import get_settings

        return get_settings
    if name == "SessionStore":
        from app.sessions import SessionStore

        return SessionStore
    if name == "build_default_registry":
        from app.tools import build_default_registry

        return build_default_registry
    if name == "create_api":
        from app.api import create_api

        return create_api
    raise AttributeError(name)
