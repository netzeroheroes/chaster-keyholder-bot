# Scene Planner

Standalone femdom scene planner. Uses **OpenRouter** (`LLM_API_KEY` in the repo `.env`), the same key as the Chaster bot. It does not use Cursor models and does not need `agent-sdk login`.

It is not the Chaster extension. Run it as its own local server.

Adults 18+ only.

```powershell
cd C:\Users\andre\chatbot
.\.venv\Scripts\python.exe scene-planner\server.py
```

Open http://127.0.0.1:8787

Training is `scene-planner/instructions.md` plus `scene-planner/tests`. Change the prompt, keep the tests green, then generate a scene you like or hate and tighten the instructions.
