# AI Chatbot (HTTP + Telegram)

Minimal chatbot that talks to any **OpenAI-compatible** LLM API, can call external HTTP APIs as tools, and optionally runs on Telegram.

## What you get

- `POST /chat` — HTTP chat endpoint with session memory
- Telegram bot (optional) — same agent, per-chat memory
- Built-in tools: `http_get` / `http_post` so the model can hit APIs
- Provider-agnostic LLM client (Ollama, LM Studio, OpenRouter, OpenAI, vLLM, …)

## Quick start

```powershell
cd C:\Users\andre\chatbot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

| Variable | Purpose |
|----------|---------|
| `LLM_BASE_URL` | OpenAI-compatible base URL |
| `LLM_API_KEY` | API key (use `ollama` for local Ollama) |
| `LLM_MODEL` | Model name |
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) (optional) |
| `SYSTEM_PROMPT` | Optional instructions for the model |

### NSFW / adult models (OpenRouter cloud)

1. Create a key at [openrouter.ai/keys](https://openrouter.ai/keys)
2. Put it in `.env` as `LLM_API_KEY=sk-or-v1-...`
3. Default model: `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` (Venice Uncensored)

If the free tier is rate-limited, switch to the paid slug in `.env`:

```env
LLM_MODEL=cognitivecomputations/dolphin-mistral-24b-venice-edition
```

Adults only (18+). Never configure the bot for sexual content involving minors.

### GUI (Domme private + shared group)

```powershell
python main.py --http-only
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) on two devices/browsers:

1. One picks **Domme** → Private tab (bot only talks to Domme) + Group tab
2. One picks **Sub** → Group only
3. Domme can set **secret directives** the Sub never sees; the bot follows them in group
4. In **Private**, Domme can tell the bot to speak in group — it posts there automatically (Sub sees it via group polling)
5. **Voice (Chrome/Edge):** speak replies, hold-to-talk / hands-free mic, and an **edge coach** with timed spoken cues so you don't type mid-scene
6. **Images:** Domme can generate tease pics via OpenRouter (`IMAGE_MODEL`, costs credits). Also supports `[[[IMAGE]]]…[[[/IMAGE]]]` from the bot.
7. **Chaster:** OAuth keyholder link at `/api/chaster/login`. Set app redirect URI to `http://127.0.0.1:8000/api/chaster/callback`. Then list wearers / add time / freeze via `/api/chaster/*`.

Optional: set `DOMME_PIN` / `SUB_PIN` in `.env`.

### Telegram (same model)

1. Create a bot with [@BotFather](https://t.me/BotFather), put token in `TELEGRAM_BOT_TOKEN`
2. Get both user ids from [@userinfobot](https://t.me/userinfobot) → `TELEGRAM_DOMME_USER_ID` / `TELEGRAM_SUB_USER_ID`
3. Add the bot to a group with both of you
4. Run `python main.py` (HTTP + Telegram)

Domme DMs = private. Group messages = shared. Domme commands in DM: `/direct …`, `/directives`, `/reset_private`, `/reset_group`.

### With Telegram

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token into `.env` as `TELEGRAM_BOT_TOKEN`
2. Run:

```powershell
python main.py
```

That starts both the HTTP API and Telegram polling. Use `--telegram-only` if you only want Telegram.

Telegram commands: `/start`, `/reset`

## Connecting more APIs

Default tools let the model call arbitrary HTTP endpoints. For production, register dedicated tools in `app/tools/` (cleaner schemas, auth headers from env, rate limits).

Example pattern in `app/tools/http_tools.py` — add a `Tool(...)` with your own handler and register it in `build_default_registry()`.

## Project layout

```
app/
  agent.py          # LLM + tool loop
  api.py            # FastAPI routes
  config.py         # Settings from .env
  sessions.py       # In-memory chat history
  telegram_bot.py   # Telegram handlers
  tools/            # Callable tools (HTTP APIs, etc.)
main.py             # Entrypoint
```

## Notes

- Chat history is in-memory (fine for a first version; swap for Redis/SQLite later).
- Model safety behavior comes from the **model/provider you choose**, not from this app.
- Do not use this for illegal activity.
