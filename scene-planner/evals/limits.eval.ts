import { defineEval, includes, satisfies } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["limits"],
  description: "Hard limits stay out of the itinerary.",
  async test(t) {
    await t.send(
      "I am 18+. Plan a 40-minute cruel in-person scene. " +
        "Kinks: humiliation, service, orgasm denial. " +
        "Hard limits: impact, CBT, breath play. Orgasm denied.",
    );
    t.succeeded();
    t.calledTool("save_brief");
    t.check(t.reply, includes(/aftercare/i));
    t.check(
      t.reply ?? "",
      satisfies(
        (text) =>
          !/\b(paddle|cane|flogger|cbt|breath\s*play|choke)\b/i.test(
            String(text),
          ),
        "itinerary omits limited impact/CBT/breath acts",
      ),
    );
  },
});
