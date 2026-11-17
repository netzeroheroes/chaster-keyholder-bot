# Scene Planner

Standalone femdom **scene-planning bot**. It writes timed, guided BDSM
itineraries. It is **not** the Chaster keyholder extension and does not
talk to locks, Telegram, or the lockbox.

Adults 18+ only.

## What it does

- Asks for duration, setting, intensity, kinks, and hard limits (or invents a demanding brief if you say surprise me).
- Stores that brief, then writes a clock-based itinerary: what you do, what he does, safewords, aftercare.

## Run locally

Needs a Cursor API key (`agent-sdk login`, or `CURSOR_API_KEY`).

```bash
cd scene-planner
npx @grok/agent-sdk@0.6.0 login
npx @grok/agent-sdk@0.6.0 dev
```

Playground: http://127.0.0.1:3000/playground

```bash
npx @grok/agent-sdk@0.6.0 run --dir . --message "I am 18+. Surprise me with a 60-minute extreme in-person scene. Limits: blood, scat."
npx @grok/agent-sdk@0.6.0 eval --dir .
```

## Train it

Evals in `evals/` are the training loop:

1. Pin a fixture prompt (a real brief you care about).
2. Run `eval`, name one failure (weak beats, ignored limits, too soft).
3. Change **one** thing in `bot/instructions.md` or `bot/skills/guided-scene.md`.
4. Re-run the same eval. Keep the change only if it improves.
5. Add an eval case that would have failed before.

Do not wire this agent into the Chaster bot.
