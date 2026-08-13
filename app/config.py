from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "gryphe/mythomax-l2-13b"
    # Cap completion size — OpenRouter reserves credits against max_tokens.
    # Keep this under your remaining balance (402 if too high).
    llm_max_tokens: int = 768
    system_prompt: str = ""  # unused when scene prompts are active

    llm_enable_tools: bool = False

    openrouter_app_name: str = "nsfw-chatbot"
    openrouter_site_url: str = "http://localhost:8000"

    telegram_bot_token: str = ""
    # Numeric Telegram user IDs (get from @userinfobot)
    telegram_domme_user_id: int = 0
    telegram_sub_user_id: int = 0
    # Optional: lock group replies to one chat id
    telegram_group_chat_id: int = 0

    # Optional light web gate (leave empty to skip)
    domme_pin: str = ""
    sub_pin: str = ""

    # Image generation via OpenRouter
    image_enabled: bool = True
    image_model: str = "black-forest-labs/flux.2-pro"
    image_aspect_ratio: str = "3:4"

    # Chaster Public API (keyholder)
    chaster_client_id: str = ""
    chaster_client_secret: str = ""
    chaster_redirect_uri: str = "http://127.0.0.1:8000/api/chaster/callback"
    chaster_scopes: str = "profile locks keyholder"
    # Optional: paste a developer token instead of OAuth
    chaster_access_token: str = ""
    # Optional default wearer lock for quick actions
    chaster_lock_id: str = ""
    # Partner extension slug used for lock actions (add/freeze/pillory…)
    chaster_extension_slug: str = "duo-domme"
    # Poll Chaster lock history and let the AI Domme react in group chat
    lock_watch_enabled: bool = True
    lock_watch_seconds: int = 45

    # Auto-punish Sub rule breaks with real lock detriment
    auto_punish_enabled: bool = True
    auto_punish_seconds: int = 600

    # Unprompted bot activity inside a daily window (local timezone)
    autopilot_enabled: bool = False
    autopilot_timezone: str = "Europe/London"
    autopilot_window_start: str = "18:00"
    autopilot_window_end: str = "23:00"
    autopilot_min_minutes: int = 45
    autopilot_max_minutes: int = 120
    autopilot_allow_chaster: bool = False
    autopilot_chaster_chance: float = 0.25
    autopilot_punish_seconds: int = 600

    # Chaster partner extension (iframe) hosting
    # Main/config pages must be public HTTPS; content is token-gated.
    standalone_ui_enabled: bool = True
    extension_dev_bypass: bool = False  # local only: fake wearer/keyholder without token
    extension_frame_ancestors: str = (
        "https://chaster.app https://*.chaster.app https://www.chaster.app"
    )

    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
