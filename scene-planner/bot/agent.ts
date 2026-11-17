import { defineAgent } from "@grok/agent-sdk";

export default defineAgent({
  name: "scene-planner",
  description:
    "Standalone femdom scene planner. Writes timed, guided BDSM itineraries. Not the Chaster keyholder bot.",
  model: {
    id: "grok-4.7",
    params: [
      { id: "reasoning_effort", value: "high" },
      { id: "fast", value: "true" },
    ],
  },
});
