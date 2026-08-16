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
    botIntensity: document.getElementById("botIntensity"),
    botQuirks: document.getElementById("botQuirks"),
  };

  let configurationToken = "";

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
      bot_voice: els.botVoice?.value || "cruel",
      bot_voice_sample: (els.botVoiceSample?.value || "").trim().slice(0, 800),
      bot_intensity: els.botIntensity?.value || "firm",
      bot_quirks: (els.botQuirks?.value || "").trim().slice(0, 800),
    };
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
    if (els.botVoice) {
      const v = String(cfg.bot_voice || "cruel").toLowerCase();
      const voices = ["cruel", "elegant", "playful", "warm", "soft", "humiliatrix"];
      els.botVoice.value = voices.includes(v) ? v : "cruel";
    }
    if (els.botVoiceSample) els.botVoiceSample.value = cfg.bot_voice_sample || "";
    if (els.botIntensity) {
      const i = String(cfg.bot_intensity || "firm").toLowerCase();
      els.botIntensity.value = ["tease", "firm", "strict"].includes(i) ? i : "firm";
    }
    if (els.botQuirks) els.botQuirks.value = cfg.bot_quirks || "";
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
