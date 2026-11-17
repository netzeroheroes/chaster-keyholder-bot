import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";

const MINOR_RE =
  /\b(child|children|minor|underage|teen(?:ager)?s?|loli|shota|jailbait)\b/i;

type BriefRecord = {
  adultsConfirmed: boolean;
  durationMinutes: number;
  intensity: string;
  setting: string;
  tone: string;
  orgasm: string;
  experience: string;
  kinks: string[];
  toys: string;
  limits: string;
  notes: string;
};

type SaveBriefResult =
  | { ok: true; stored: true; brief: BriefRecord }
  | { ok: false; stored: false; reason: string };

function blob(brief: BriefRecord): string {
  return [
    brief.toys,
    brief.limits,
    brief.notes,
    brief.kinks.join(" "),
  ].join(" ");
}

export default defineTool({
  description: prompt`
    Store the negotiated scene brief before you write the itinerary.
    Call this once you have duration, setting, intensity, kinks, orgasm
    policy, and hard limits (empty string if none). Rejects underage
    content. Do not write a scene until this returns ok.
  `,
  execution: "server",
  effect: "idempotent",
  inputSchema: z.object({
    adultsConfirmed: z
      .boolean()
      .describe("Must be true. This planner is 18+ only."),
    durationMinutes: z.number().int().min(15).max(480),
    intensity: z.enum(["tease", "firm", "cruel", "extreme"]),
    setting: z.enum(["in_person", "distance", "mixed"]),
    tone: z.enum([
      "cruel",
      "teasing",
      "ritual",
      "training",
      "interrogation",
      "ownership",
    ]),
    orgasm: z.enum(["denied", "ruined", "maybe", "released"]),
    experience: z.enum(["new", "practiced", "experienced"]),
    kinks: z.array(z.string().min(1).max(80)).max(12),
    toys: z.string().max(800).default(""),
    limits: z.string().max(800).default(""),
    notes: z.string().max(800).default(""),
  }),
  async execute(input, ctx): Promise<SaveBriefResult> {
    const brief: BriefRecord = {
      adultsConfirmed: input.adultsConfirmed,
      durationMinutes: input.durationMinutes,
      intensity: input.intensity,
      setting: input.setting,
      tone: input.tone,
      orgasm: input.orgasm,
      experience: input.experience,
      kinks: input.kinks,
      toys: input.toys ?? "",
      limits: input.limits ?? "",
      notes: input.notes ?? "",
    };
    if (!brief.adultsConfirmed) {
      return {
        ok: false,
        stored: false,
        reason: "Confirm all participants are 18+ before planning.",
      };
    }
    if (MINOR_RE.test(blob(brief))) {
      return {
        ok: false,
        stored: false,
        reason: "This planner is adults 18+ only.",
      };
    }
    await ctx.host.kv.put(`brief:${ctx.session.id}`, brief);
    return { ok: true, stored: true, brief };
  },
});
