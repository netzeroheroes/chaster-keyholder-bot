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
    llm_model: str = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
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

    # Image generation via OpenRouter /api/v1/images (Flux is not a chat model)
    image_enabled: bool = False
    image_model: str = "black-forest-labs/flux.2-pro"
    image_fallback_models: str = (
        "bytedance-seed/seedream-4.5,"
        "black-forest-labs/flux.2-klein-4b,"
        "google/gemini-2.5-flash-image"
    )
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
    # (backup if webhooks miss; primary path is POST /api/chaster/webhook)
    lock_watch_enabled: bool = True
    lock_watch_seconds: int = 45
    # Duo Domme (your developer app) → Extension URLs → webhooks
    # Basic auth is optional; if password is set AND require_auth=true, Chaster must send it.
    chaster_webhook_user: str = "chaster-bot"
    chaster_webhook_password: str = ""
    chaster_webhook_require_auth: bool = False

    # Research & Desire Lockbox (Dashboard API) — Chaster hygiene ↔ physical box
    # Docs: https://dev.researchanddesire.com/ — Ultra API token required
    rad_api_token: str = ""
    rad_api_base_url: str = "https://dashboard.researchanddesire.com/api/v1"
    rad_lockbox_sync_enabled: bool = False
    rad_sync_hygiene: bool = True
    # Also mirror full Chaster unlock/lock (usually leave false)
    rad_sync_session_lock: bool = False
    # Manual-only: no continuous Chaster timer sync — lock/unlock (+ hygiene) only.
    # Keep false so Chaster remaining is periodically mirrored to the box.
    rad_manual_only: bool = False
    # How often to push Chaster remaining onto R+D (seconds).
    rad_timer_sync_seconds: int = 60
    # Lockee's R+D user id (keyholder token acting on linked user)
    rad_target_user_id: int = 0
    # Lock template id — only used to *start* a session; duration comes from Chaster.
    # Leave 0 to auto-pick the first available template.
    rad_lock_settings_id: int = 0
    # Comma-separated R+D user ids assigned as keyholders on re-lock
    rad_keyholder_ids: str = ""
    rad_is_test_lock: bool = False

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

    # What the bot may do on the lock (overridden by Settings → Enable)
    bot_allow_add_time: bool = True
    bot_allow_remove_time: bool = True
    bot_allow_freeze: bool = True
    bot_allow_hide_timer: bool = True
    bot_allow_pillory: bool = True
    bot_voice: str = "cruel"
    bot_voice_sample: str = ""

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
