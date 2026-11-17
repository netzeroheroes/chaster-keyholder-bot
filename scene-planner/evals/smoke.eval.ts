import { defineEval, includes } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description: "Saves a brief, then writes a timed guided scene.",
  async test(t) {
    await t.send(
      "I am 18+. Write a 45-minute in-person extreme femdom scene. " +
        "Kinks: chastity, orgasm denial, humiliation, bondage. " +
        "Orgasm denied. Hard limits: blood, scat. Surprise is not needed — " +
        "use these details and write the itinerary.",
    );
    t.succeeded();
    t.calledTool("save_brief");
    t.notCalledTool("echo");
    t.check(t.reply, includes(/aftercare/i));
    t.check(t.reply, includes(/\d+\s*[–-]\s*\d+/));
  },
});
