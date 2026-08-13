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

  function readForm() {
    const g = (id) => document.getElementById(id);
    return {
      default_add_time_seconds: Number(g("defaultAdd").value) || 3600,
      default_remove_time_seconds: Number(g("defaultRemove").value) || 1800,
      soft_add_time_seconds: Number(g("softAdd").value) || 900,
      hard_add_time_seconds: Number(g("hardAdd").value) || 7200,
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
    };
  }

  function fillForm(cfg) {
    const g = (id) => document.getElementById(id);
    g("defaultAdd").value = cfg.default_add_time_seconds ?? 3600;
    g("defaultRemove").value = cfg.default_remove_time_seconds ?? 1800;
    g("softAdd").value = cfg.soft_add_time_seconds ?? 900;
    g("hardAdd").value = cfg.hard_add_time_seconds ?? 7200;
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
