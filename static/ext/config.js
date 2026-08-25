(function () {
  const els = {
    gate: document.getElementById("gate"),
    gateMsg: document.getElementById("gateMsg"),
    form: document.getElementById("cfgForm"),
    status: document.getElementById("cfgStatus"),
    autoPunishEnabled: document.getElementById("autoPunishEnabled"),
    autoPunishSeconds: document.getElementById("autoPunishSeconds"),
    autopilotEnabled: document.getElementById("autopilotEnabled"),
    windowStart: document.getElementById("windowStart"),
    windowEnd: document.getElementById("windowEnd"),
    autopilotTz: document.getElementById("autopilotTz"),
    autopilotMin: document.getElementById("autopilotMin"),
    autopilotMax: document.getElementById("autopilotMax"),
    autopilotChaster: document.getElementById("autopilotChaster"),
    autopilotPunishSeconds: document.getElementById("autopilotPunishSeconds"),
    botName: document.getElementById("botName"),
    dommeTitle: document.getElementById("dommeTitle"),
    botVoice: document.getElementById("botVoice"),
    botVoiceSample: document.getElementById("botVoiceSample"),
    botVoiceBlurb: document.getElementById("botVoiceBlurb"),
    botIntensity: document.getElementById("botIntensity"),
    botIntensityBlurb: document.getElementById("botIntensityBlurb"),
    botQuirks: document.getElementById("botQuirks"),
    botBio: document.getElementById("botBio"),
    botGreeting: document.getElementById("botGreeting"),
    botPersona: document.getElementById("botPersona"),
    botSex: document.getElementById("botSex"),
  };

  let configurationToken = "";
  const TONE = {
    cruel: "No-nonsense. Dry, precise, a little mean. Enjoy his wait. Do not soothe him.",
    elegant: "Well-mannered, commanding, dignified. Quiet authority. Never crude for its own sake.",
    playful: "Frisky and mischievous. Short dares. Laugh at him. Not a lecture.",
    warm: "Fond and firmly in control. Tease with affection. Still deny. Never a therapist.",
    soft: "Silky, gentle authority. Soft-spoken. The cage is still the point.",
    humiliatrix: "Degrading and specific. The cage is the joke. Never kind for free.",
    custom: "Your custom tone. Write exactly how this bot should talk.",
  };
  const INTENSITY = {
    tease: "Light pressure. Chat first. Lock changes are a spice, not every turn.",
    firm: "Tease and command in the same breath. Default keyholder energy.",
    strict: "Short orders. Less chat. Use the lock when he pushes. No essays.",
    custom: "Your custom intensity. How hard this bot pushes each turn.",
  };
  const SAMPLES = {
    cruel: "Hey you. Tell me your kinks and a hard limit. Now.",
    elegant: "Good. You are locked. Tell me a limit, then a kink I may use.",
    playful: "Oh we're doing this. What's a kink you hope I won't use?",
    warm: "Mmm. Stay denied for me. What turns you on that I can use against you?",
    soft: "Easy. The cage stays. Whisper a kink, and a line you will not cross.",
    humiliatrix: "Hey you. That pathetic thing is locked. Kinks. Limits. Don't waste my time.",
    custom: "Hey you. Tell me your kinks and a hard limit.",
  };

  function apiDetail(data, fallback) {
    const d = data && data.detail;
    if (typeof d === "string" && d.trim()) return d;
    if (Array.isArray(d)) {
      return d
        .map((x) => (x && (x.msg || x.message)) || JSON.stringify(x))
        .join("; ");
    }
    if (d && typeof d === "object") return JSON.stringify(d);
    return fallback;
  }

  function parseConfigToken() {
    const raw = (window.location.hash || "").replace(/^#/, "");
    if (!raw) return "";
    try {
      const params = JSON.parse(decodeURIComponent(raw));
      return String(params.partnerConfigurationToken || "").trim();
    } catch {
      try {
        const params = JSON.parse(raw);
        return String(params.partnerConfigurationToken || "").trim();
      } catch {
        return "";
      }
    }
  }

  const UNIT_SEC = { minutes: 60, hours: 3600, days: 86400 };

  function secondsToParts(sec, fallbackUnit) {
    const s = Math.max(60, Number(sec) || 60);
    if (s % 86400 === 0) return { value: s / 86400, unit: "days" };
    if (s % 3600 === 0) return { value: s / 3600, unit: "hours" };
    if (s % 60 === 0) return { value: s / 60, unit: "minutes" };
    return {
      value: Math.max(1, Math.round(s / (UNIT_SEC[fallbackUnit] || 60))),
      unit: fallbackUnit || "minutes",
    };
  }

  function partsToSeconds(value, unit) {
    const n = Math.max(1, Number(value) || 1);
    return Math.max(60, Math.round(n * (UNIT_SEC[unit] || 60)));
  }

  function readForm() {
    const g = (id) => document.getElementById(id);
    let minSec = partsToSeconds(g("minAddValue").value, g("minAddUnit").value);
    let maxSec = partsToSeconds(g("maxAddValue").value, g("maxAddUnit").value);
    if (minSec > maxSec) {
      const tmp = minSec;
      minSec = maxSec;
      maxSec = tmp;
    }
    return {
      min_add_time_seconds: minSec,
      max_add_time_seconds: maxSec,
      soft_add_time_seconds: minSec,
      hard_add_time_seconds: maxSec,
      default_add_time_seconds: maxSec,
      bot_allow_add_time: document.getElementById("botAllowAddTime")?.checked !== false,
      bot_allow_remove_time: document.getElementById("botAllowRemoveTime")?.checked !== false,
      bot_allow_freeze: document.getElementById("botAllowFreeze")?.checked !== false,
      bot_allow_hide_timer: document.getElementById("botAllowHideTimer")?.checked !== false,
      bot_allow_pillory: document.getElementById("botAllowPillory")?.checked !== false,
      auto_punish_enabled: els.autoPunishEnabled.checked,
      auto_punish_seconds: Number(els.autoPunishSeconds.value) || 600,
      autopilot_enabled: els.autopilotEnabled.checked,
      autopilot_window_start: els.windowStart.value.trim() || "18:00",
      autopilot_window_end: els.windowEnd.value.trim() || "23:00",
      autopilot_timezone: els.autopilotTz.value.trim() || "Europe/London",
      autopilot_min_minutes: Number(els.autopilotMin.value) || 45,
      autopilot_max_minutes: Number(els.autopilotMax.value) || 120,
      autopilot_allow_chaster: els.autopilotChaster.checked,
      autopilot_punish_seconds: Number(els.autopilotPunishSeconds.value) || 600,
      bot_name: els.botName.value.trim() || "Keyholder",
      domme_title: els.dommeTitle.value.trim() || "Mistress",
      bot_persona: els.botPersona?.value || "friend",
      bot_sex: els.botSex?.value || "female",
      bot_voice: els.botVoice?.value || "cruel",
      bot_voice_sample: (els.botVoiceSample?.value || "").trim().slice(0, 800),
      bot_voice_blurb: (els.botVoiceBlurb?.value || "").trim().slice(0, 800),
      bot_intensity: els.botIntensity?.value || "firm",
      bot_intensity_blurb: (els.botIntensityBlurb?.value || "").trim().slice(0, 800),
      bot_quirks: (els.botQuirks?.value || "").trim().slice(0, 800),
      bot_bio: (els.botBio?.value || "").trim().slice(0, 1200),
      bot_greeting: (els.botGreeting?.value || "").trim().slice(0, 400),
    };
  }

  function syncSexPicks(value) {
    const picks = document.getElementById("botSexPicks");
    if (!picks) return;
    const v = String(value || "female").toLowerCase();
    picks.querySelectorAll(".sex-pick").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sex === v);
    });
  }

  function fillForm(cfg) {
    const g = (id) => document.getElementById(id);
    const minP = secondsToParts(
      cfg.min_add_time_seconds ?? cfg.soft_add_time_seconds ?? 900,
      "minutes"
    );
    const maxP = secondsToParts(
      cfg.max_add_time_seconds ??
        cfg.hard_add_time_seconds ??
        cfg.default_add_time_seconds ??
        86400,
      "hours"
    );
    g("minAddValue").value = minP.value;
    g("minAddUnit").value = minP.unit;
    g("maxAddValue").value = maxP.value;
    g("maxAddUnit").value = maxP.unit;
    const flagOn = (key) => cfg[key] !== false;
    const setCheck = (id, key) => {
      const el = document.getElementById(id);
      if (el) el.checked = flagOn(key);
    };
    setCheck("botAllowAddTime", "bot_allow_add_time");
    setCheck("botAllowRemoveTime", "bot_allow_remove_time");
    setCheck("botAllowFreeze", "bot_allow_freeze");
    setCheck("botAllowHideTimer", "bot_allow_hide_timer");
    setCheck("botAllowPillory", "bot_allow_pillory");
    els.autoPunishEnabled.checked = !!cfg.auto_punish_enabled;
    els.autoPunishSeconds.value = cfg.auto_punish_seconds ?? 600;
    els.autopilotEnabled.checked = !!cfg.autopilot_enabled;
    els.windowStart.value = cfg.autopilot_window_start || "18:00";
    els.windowEnd.value = cfg.autopilot_window_end || "23:00";
    els.autopilotTz.value = cfg.autopilot_timezone || "Europe/London";
    els.autopilotMin.value = cfg.autopilot_min_minutes ?? 45;
    els.autopilotMax.value = cfg.autopilot_max_minutes ?? 120;
    els.autopilotChaster.checked = !!cfg.autopilot_allow_chaster;
    els.autopilotPunishSeconds.value = cfg.autopilot_punish_seconds ?? 600;
    els.botName.value = cfg.bot_name || "Keyholder";
    els.dommeTitle.value = cfg.domme_title || "Mistress";
    if (els.botPersona) {
      const p = String(cfg.bot_persona || "friend").toLowerCase();
      const personas = ["friend", "domme", "bull", "male_dom"];
      els.botPersona.value = personas.includes(p) ? p : "friend";
    }
    if (els.botSex) {
      const s = String(cfg.bot_sex || "female").toLowerCase();
      els.botSex.value = ["female", "male", "other"].includes(s) ? s : "female";
      syncSexPicks(els.botSex.value);
    }
    if (els.botVoice) {
      const v = String(cfg.bot_voice || "cruel").toLowerCase();
      const voices = ["cruel", "elegant", "playful", "warm", "soft", "humiliatrix", "custom"];
      els.botVoice.value = voices.includes(v) ? v : "cruel";
    }
    if (els.botVoiceBlurb) {
      els.botVoiceBlurb.value = cfg.bot_voice_blurb || TONE[els.botVoice?.value] || "";
    }
    if (els.botVoiceSample) {
      els.botVoiceSample.value = cfg.bot_voice_sample || "";
      els.botVoiceSample.dataset.custom = cfg.bot_voice_sample ? "1" : "";
    }
    if (els.botIntensity) {
      const i = String(cfg.bot_intensity || "firm").toLowerCase();
      els.botIntensity.value = ["tease", "firm", "strict", "custom"].includes(i) ? i : "firm";
    }
    if (els.botIntensityBlurb) {
      els.botIntensityBlurb.value =
        cfg.bot_intensity_blurb || INTENSITY[els.botIntensity?.value] || "";
    }
    if (els.botQuirks) els.botQuirks.value = cfg.bot_quirks || "";
    if (els.botBio) els.botBio.value = cfg.bot_bio || "";
    if (els.botGreeting) els.botGreeting.value = cfg.bot_greeting || "";
  }

  function postParent(payload) {
    window.parent.postMessage(JSON.stringify(payload), "*");
  }

  async function loadConfig() {
    const res = await fetch("/api/ext/config/get", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        partner_configuration_token: configurationToken,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(
        apiDetail(
          data,
          `Config rejected (HTTP ${res.status}). Check CHASTER_ACCESS_TOKEN on Render.`
        )
      );
    }
    fillForm(data.config || {});
    if (data.voice_catalog && data.voice_catalog.tone) {
      Object.assign(TONE, data.voice_catalog.tone);
      Object.assign(INTENSITY, data.voice_catalog.intensity || {});
      Object.assign(SAMPLES, data.voice_catalog.samples || {});
    }
    els.gate.classList.add("hidden");
    els.form.classList.remove("hidden");
    els.status.textContent = "Loaded — use Chaster Save when done.";
  }

  async function saveConfig() {
    postParent({
      type: "partner_configuration",
      event: "save_loading",
    });
    try {
      const res = await fetch("/api/ext/config/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          partner_configuration_token: configurationToken,
          config: readForm(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Save failed"));
      els.status.textContent = "Saved.";
      postParent({ type: "partner_configuration", event: "save_success" });
    } catch (err) {
      els.status.textContent = String(err.message || err);
      postParent({ type: "partner_configuration", event: "save_failed" });
    }
  }

  // Tell Chaster modal we support Save
  postParent({
    type: "partner_configuration",
    event: "capabilities",
    payload: { features: { save: true } },
  });

  addEventListener("message", (e) => {
    if (typeof e.data !== "string") return;
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "chaster" && msg.event === "partner_configuration_save") {
        saveConfig();
      }
    } catch {
      /* ignore */
    }
  });

  if (els.botPersona && els.botSex) {
    els.botPersona.addEventListener("change", () => {
      const role = els.botPersona.value;
      if (role === "bull" || role === "male_dom") {
        els.botSex.value = "male";
        syncSexPicks("male");
      }
    });
  }
  const sexPicks = document.getElementById("botSexPicks");
  if (sexPicks && els.botSex) {
    sexPicks.addEventListener("click", (e) => {
      const btn = e.target.closest(".sex-pick");
      if (!btn) return;
      els.botSex.value = btn.dataset.sex || "female";
      syncSexPicks(els.botSex.value);
    });
  }

  if (els.botVoice && els.botVoiceBlurb) {
    els.botVoice.addEventListener("change", () => {
      els.botVoiceBlurb.value = TONE[els.botVoice.value] || "";
      if (els.botVoiceSample && els.botVoiceSample.dataset.custom !== "1") {
        els.botVoiceSample.value = SAMPLES[els.botVoice.value] || "";
      }
    });
    els.botVoiceBlurb.addEventListener("input", () => {
      if (
        els.botVoice.value !== "custom" &&
        els.botVoiceBlurb.value.trim() !== (TONE[els.botVoice.value] || "").trim()
      ) {
        els.botVoice.value = "custom";
      }
    });
  }
  if (els.botIntensity && els.botIntensityBlurb) {
    els.botIntensity.addEventListener("change", () => {
      els.botIntensityBlurb.value = INTENSITY[els.botIntensity.value] || "";
    });
    els.botIntensityBlurb.addEventListener("input", () => {
      if (
        els.botIntensity.value !== "custom" &&
        els.botIntensityBlurb.value.trim() !== (INTENSITY[els.botIntensity.value] || "").trim()
      ) {
        els.botIntensity.value = "custom";
      }
    });
  }
  if (els.botVoiceSample) {
    els.botVoiceSample.addEventListener("input", () => {
      els.botVoiceSample.dataset.custom = els.botVoiceSample.value.trim() ? "1" : "";
    });
  }

  async function boot() {
    configurationToken = parseConfigToken();
    if (!configurationToken) {
      els.gateMsg.textContent =
        "No configuration token. Open Configure on this extension inside Chaster.";
      return;
    }
    try {
      await loadConfig();
    } catch (err) {
      els.gateMsg.textContent = String(err.message || err);
    }
  }

  boot();
})();
