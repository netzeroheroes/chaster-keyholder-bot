(function () {
  const els = {
    gate: document.getElementById("gate"),
    gateMsg: document.getElementById("gateMsg"),
    app: document.getElementById("app"),
    roleLabel: document.getElementById("roleLabel"),
    heading: document.getElementById("heading"),
    sessionMeta: document.getElementById("sessionMeta"),
    settingsBtn: document.getElementById("settingsBtn"),
    settingsPanel: document.getElementById("settingsPanel"),
    settingsClose: document.getElementById("settingsClose"),
    settingsForm: document.getElementById("settingsForm"),
    settingsStatus: document.getElementById("settingsStatus"),
    roomTabs: document.getElementById("roomTabs"),
    privateTab: document.getElementById("privateTab"),
    roomHint: document.getElementById("roomHint"),
    messages: document.getElementById("messages"),
    jumpLatest: document.getElementById("jumpLatest"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("input"),
    sendBtn: document.getElementById("sendBtn"),
    status: document.getElementById("status"),
  };

  const state = {
    mainToken: "",
    role: null,
    chasterRole: null,
    room: "group",
    lastCount: 0,
    stickToBottom: true,
    pendingNew: 0,
    pollTimer: null,
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

  function parseHashToken() {
    const raw = (window.location.hash || "").replace(/^#/, "");
    if (!raw) return "";
    try {
      const params = JSON.parse(decodeURIComponent(raw));
      return String(params.mainToken || "").trim();
    } catch {
      return "";
    }
  }

  function setStatus(t) {
    els.status.textContent = t || "";
  }

  function nearBottom() {
    const el = els.messages;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  }

  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
    state.stickToBottom = true;
    state.pendingNew = 0;
    if (els.jumpLatest) els.jumpLatest.classList.add("hidden");
  }

  function updateJumpBtn() {
    if (!els.jumpLatest) return;
    if (state.pendingNew > 0 && !state.stickToBottom) {
      els.jumpLatest.classList.remove("hidden");
      els.jumpLatest.textContent =
        state.pendingNew === 1
          ? "↓ New message"
          : `↓ ${state.pendingNew} new messages`;
    } else {
      els.jumpLatest.classList.add("hidden");
    }
  }

  function autosizeInput() {
    const el = els.input;
    el.style.height = "auto";
    el.style.height = Math.min(120, Math.max(44, el.scrollHeight)) + "px";
  }

  function updateRoomUi() {
    els.roomTabs.querySelectorAll(".room-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.room === state.room);
    });
    if (state.room === "private") {
      els.roomHint.textContent =
        "Private: keyholder ↔ AI only (lockee cannot see this)";
      els.input.placeholder = "Plan with the AI…";
    } else {
      els.roomHint.textContent = "Group: Domme + Sub + AI";
      els.input.placeholder =
        state.chasterRole === "keyholder"
          ? "Message as keyholder…"
          : "Message as lockee…";
    }
  }

  function renderMessages(messages) {
    const prev = state.lastCount;
    const grew = messages.length > prev && prev >= 0;
    const added = grew ? messages.length - prev : 0;
    els.messages.innerHTML = "";
    for (const m of messages) {
      const div = document.createElement("div");
      const who = String(m.speaker || "Keyholder");
      const cls = who.startsWith("Domme")
        ? "Domme"
        : who.startsWith("Sub")
          ? "Sub"
          : "bot";
      div.className = `msg ${cls}`;
      div.innerHTML = `<span class="who">${who}</span>`;
      div.append(document.createTextNode(m.content || ""));
      els.messages.appendChild(div);
    }
    state.lastCount = messages.length;
    if (state.stickToBottom || prev <= 0) {
      scrollToBottom();
    } else if (added > 0) {
      state.pendingNew += added;
      updateJumpBtn();
    }
  }

  async function loadSession() {
    const res = await fetch("/api/ext/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ main_token: state.mainToken }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(data, "Session rejected"));
    const s = data.session || {};
    state.role = s.app_role;
    state.chasterRole = s.role;
    const handle =
      s.role === "keyholder" ? s.keyholder_username : s.wearer_username;
    els.roleLabel.textContent =
      s.role === "keyholder"
        ? `Keyholder${handle ? " @" + handle : ""}`
        : `Lockee${handle ? " @" + handle : ""}`;
    els.heading.textContent = data.bot_name || "Chat";
    els.sessionMeta.textContent = [
      s.wearer_username && `Lockee: ${s.wearer_username}`,
      s.keyholder_username && `KH: ${s.keyholder_username}`,
    ]
      .filter(Boolean)
      .join(" · ");

    if (s.app_role === "domme" || s.role === "keyholder") {
      els.privateTab.classList.remove("hidden");
      if (els.settingsBtn) els.settingsBtn.classList.remove("hidden");
    } else {
      els.privateTab.classList.add("hidden");
      if (els.settingsBtn) els.settingsBtn.classList.add("hidden");
      state.room = "group";
    }
    updateRoomUi();
    els.gate.classList.add("hidden");
    els.app.classList.remove("hidden");
  }

  function fillSettings(cfg) {
    const g = (id) => document.getElementById(id);
    g("defaultAdd").value = cfg.default_add_time_seconds ?? 3600;
    g("defaultRemove").value = cfg.default_remove_time_seconds ?? 1800;
    g("softAdd").value = cfg.soft_add_time_seconds ?? 900;
    g("hardAdd").value = cfg.hard_add_time_seconds ?? 7200;
    g("setAutoPunishEnabled").checked = !!cfg.auto_punish_enabled;
    g("setAutoPunishSeconds").value = cfg.auto_punish_seconds ?? 600;
    g("setAutopilotEnabled").checked = !!cfg.autopilot_enabled;
    g("setWindowStart").value = cfg.autopilot_window_start || "18:00";
    g("setWindowEnd").value = cfg.autopilot_window_end || "23:00";
    g("setAutopilotTz").value = cfg.autopilot_timezone || "Europe/London";
    g("setAutopilotChaster").checked = !!cfg.autopilot_allow_chaster;
    g("setAutopilotPunish").value = cfg.autopilot_punish_seconds ?? 600;
    g("setBotName").value = cfg.bot_name || "Keyholder";
    g("setDommeTitle").value = cfg.domme_title || "Mistress";
  }

  function readSettings() {
    const g = (id) => document.getElementById(id);
    return {
      default_add_time_seconds: Number(g("defaultAdd").value) || 3600,
      default_remove_time_seconds: Number(g("defaultRemove").value) || 1800,
      soft_add_time_seconds: Number(g("softAdd").value) || 900,
      hard_add_time_seconds: Number(g("hardAdd").value) || 7200,
      auto_punish_enabled: g("setAutoPunishEnabled").checked,
      auto_punish_seconds: Number(g("setAutoPunishSeconds").value) || 600,
      autopilot_enabled: g("setAutopilotEnabled").checked,
      autopilot_window_start: g("setWindowStart").value.trim() || "18:00",
      autopilot_window_end: g("setWindowEnd").value.trim() || "23:00",
      autopilot_timezone: g("setAutopilotTz").value.trim() || "Europe/London",
      autopilot_allow_chaster: g("setAutopilotChaster").checked,
      autopilot_punish_seconds: Number(g("setAutopilotPunish").value) || 600,
      bot_name: g("setBotName").value.trim() || "Keyholder",
      domme_title: g("setDommeTitle").value.trim() || "Mistress",
    };
  }

  async function openSettings() {
    if (!els.settingsPanel) return;
    els.settingsStatus.textContent = "Loading…";
    els.settingsPanel.classList.remove("hidden");
    els.settingsPanel.setAttribute("aria-hidden", "false");
    try {
      const res = await fetch("/api/ext/settings/get", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Could not load settings"));
      fillSettings(data.config || {});
      els.settingsStatus.textContent = "Edit and save.";
    } catch (err) {
      els.settingsStatus.textContent = String(err.message || err);
    }
  }

  function closeSettings() {
    if (!els.settingsPanel) return;
    els.settingsPanel.classList.add("hidden");
    els.settingsPanel.setAttribute("aria-hidden", "true");
  }

  async function loadHistory() {
    const res = await fetch("/api/ext/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        main_token: state.mainToken,
        room: state.room,
      }),
    });
    if (!res.ok) return;
    const data = await res.json();
    if ((data.messages || []).length !== state.lastCount) {
      renderMessages(data.messages || []);
    }
  }

  async function sendMessage(text) {
    const message = (text || "").trim();
    if (!message) return;
    els.sendBtn.disabled = true;
    setStatus("…");
    els.input.value = "";
    autosizeInput();
    try {
      const res = await fetch("/api/ext/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          main_token: state.mainToken,
          message,
          room: state.room,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, res.statusText));
      state.lastCount = -1;
      state.stickToBottom = true;
      await loadHistory();
      setStatus("");
    } catch (err) {
      setStatus(String(err.message || err));
    } finally {
      els.sendBtn.disabled = false;
      els.input.focus();
    }
  }

  async function switchRoom(room) {
    if (room === state.room) return;
    if (room === "private" && state.role !== "domme") {
      setStatus("Only the keyholder can use private chat.");
      return;
    }
    state.room = room;
    state.lastCount = -1;
    state.stickToBottom = true;
    state.pendingNew = 0;
    updateJumpBtn();
    updateRoomUi();
    setStatus("");
    await loadHistory();
  }

  els.roomTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".room-tab");
    if (!btn || btn.classList.contains("hidden")) return;
    if (btn.dataset.action === "settings" || btn.id === "settingsBtn") {
      openSettings();
      return;
    }
    switchRoom(btn.dataset.room);
  });

  if (els.settingsBtn) {
    els.settingsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      openSettings();
    });
  }
  if (els.settingsClose) {
    els.settingsClose.addEventListener("click", closeSettings);
  }
  if (els.settingsPanel) {
    els.settingsPanel.addEventListener("click", (e) => {
      if (e.target === els.settingsPanel) closeSettings();
    });
  }
  if (els.settingsForm) {
    els.settingsForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      els.settingsStatus.textContent = "Saving…";
      try {
        const res = await fetch("/api/ext/settings/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            main_token: state.mainToken,
            config: readSettings(),
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiDetail(data, "Save failed"));
        els.settingsStatus.textContent = "Saved.";
      } catch (err) {
        els.settingsStatus.textContent = String(err.message || err);
      }
    });
  }

  els.messages.addEventListener("scroll", () => {
    state.stickToBottom = nearBottom();
    if (state.stickToBottom) {
      state.pendingNew = 0;
      updateJumpBtn();
    }
  });

  if (els.jumpLatest) {
    els.jumpLatest.addEventListener("click", scrollToBottom);
  }

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(els.input.value);
  });

  els.input.addEventListener("input", autosizeInput);
  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });

  async function boot() {
    state.mainToken = parseHashToken();
    if (!state.mainToken && /^#dev:/.test(window.location.hash || "")) {
      state.mainToken = (window.location.hash || "").slice(1);
    }
    if (!state.mainToken) {
      els.gateMsg.textContent =
        "No Chaster session token. Open this extension from your lock in the Chaster app.";
      return;
    }
    try {
      await loadSession();
      await loadHistory();
      autosizeInput();
      state.pollTimer = setInterval(() => loadHistory().catch(() => {}), 2500);
    } catch (err) {
      els.gateMsg.textContent = String(err.message || err);
    }
  }

  boot();
})();
