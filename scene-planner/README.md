# Scene Planner

Standalone femdom scene planner. Uses **OpenRouter** (`LLM_API_KEY` in the repo `.env`). It does not use Cursor models and does not need `agent-sdk login`.

It chats like the Miniapps BDSM Scenario Planner: it asks for toys and hard limits, writes a unique numbered itinerary, then rewrites the whole scene from follow-ups.

It is not the Chaster extension. Run it as its own local server.

Adults 18+ only. Default dynamic is female dominant / male submissive.

```powershell
cd C:\Users\andre\chatbot
.\.venv\Scripts\python.exe scene-planner\server.py
```

Open http://127.0.0.1:8787

Training is `scene-planner/instructions.md` plus `scene-planner/tests`. Change the prompt, keep the tests green, then send a scene you like or hate and tighten the instructions.
