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
    typingBubble: document.getElementById("typingBubble"),
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
    typingTimer: null,
    typingLastSent: 0,
    displayName: "",
  };

  function apiDetail(data, fallback) {
    const d = data && data.detail;
    if (typeof d === "string" && d.trim()) return d;
    if (Array.isArray(d)) {
      return d
        .map((x) => {
          if (!x) return "";
          const loc = Array.isArray(x.loc) ? x.loc.slice(1).join(".") : "";
          const msg = x.msg || x.message || JSON.stringify(x);
          return loc ? `${loc}: ${msg}` : msg;
        })
        .filter(Boolean)
        .join("; ");
    }
    if (d && typeof d === "object") return JSON.stringify(d);
    if (data && typeof data.message === "string" && data.message.trim()) {
      return data.message;
    }
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
    state.displayName = handle
      ? String(handle)
      : s.role === "keyholder"
        ? "Keyholder"
        : "Lockee";
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
    const mult = UNIT_SEC[unit] || 60;
    return Math.max(60, Math.round(n * mult));
  }

  function renderAutopilotStatus(st) {
    const el = document.getElementById("autopilotLive");
    if (!el) return;
    if (!st || typeof st !== "object") {
      el.textContent = "Autopilot status: —";
      return;
    }
    const on = st.autopilot_enabled ? "ON" : "OFF";
    const win = st.window_open ? "inside window" : "outside window";
    const bits = [`Live: ${on}`, win];
    if (st.loop_running === false) bits.push("loop not started");
    if (st.last_skip_reason) bits.push(st.last_skip_reason);
    if (st.last_tick_at) bits.push(`last tease ${st.last_tick_at}`);
    if (st.next_wake_at) bits.push(`next check ~${st.next_wake_at}`);
    el.textContent = bits.join(" · ");
  }

  function renderLockboxStatus(st) {
    const el = document.getElementById("lockboxLive");
    if (!el) return;
    if (!st || typeof st !== "object") {
      el.textContent = "Lockbox: —";
      return;
    }
    if (!st.configured) {
      el.textContent =
        "Lockbox: not configured (set RAD_API_TOKEN + RAD_LOCK_SETTINGS_ID on Render)";
      return;
    }
    const sess = st.session || null;
    const state = sess
      ? `${sess.lockState || "?"}${sess.isActive ? " (active)" : ""}`
      : "no active session";
    const sync = st.sync_enabled ? "sync ON" : "sync OFF";
    const hyg = st.hygiene_unlock ? "hygiene→unlock" : "hygiene off";
    const bits = [sync, "time from Chaster", hyg, state];
    if (st.last_sync && st.last_sync.chaster_remaining != null) {
      bits.push(`Chaster ~${st.last_sync.chaster_remaining}s`);
    }
    if (st.last_sync && st.last_sync.detail) {
      bits.push(
        `last ${st.last_sync.action || "?"}: ${st.last_sync.detail}` +
          (st.last_sync.ok === false ? " (failed)" : "")
      );
    }
    if (st.error) bits.push(String(st.error));
    el.textContent = "Lockbox: " + bits.join(" · ");
  }

  async function refreshLockboxStatus() {
    if (!state.mainToken) return;
    try {
      const res = await fetch("/api/ext/lockbox/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken }),
      });
      const data = await res.json().catch(() => ({}));
      renderLockboxStatus(data);
    } catch (_) {
      renderLockboxStatus({ configured: false, error: "status fetch failed" });
    }
  }

  async function lockboxAction(action) {
    const statusEl = document.getElementById("settingsStatus");
    if (statusEl) statusEl.textContent = `${action}ing lockbox…`;
    try {
      const res = await fetch("/api/ext/lockbox/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken, action }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Lockbox action failed"));
      renderLockboxStatus(data);
      if (statusEl) {
        const ls = data.last_sync || {};
        statusEl.textContent = ls.detail || `Lockbox ${action} done.`;
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = String(err.message || err);
    }
  }

  function fillSettings(cfg) {
    const g = (id) => document.getElementById(id);
    const minSec =
      cfg.min_add_time_seconds ?? cfg.soft_add_time_seconds ?? 900;
    const maxSec =
      cfg.max_add_time_seconds ??
      cfg.hard_add_time_seconds ??
      cfg.default_add_time_seconds ??
      86400;
    const minP = secondsToParts(minSec, "minutes");
    const maxP = secondsToParts(maxSec, "hours");
    g("minAddValue").value = minP.value;
    g("minAddUnit").value = minP.unit;
    g("maxAddValue").value = maxP.value;
    g("maxAddUnit").value = maxP.unit;
    g("setAutoPunishEnabled").checked = !!cfg.auto_punish_enabled;
    g("setAutoPunishSeconds").value = cfg.auto_punish_seconds ?? 600;
    g("setAutopilotEnabled").checked = !!cfg.autopilot_enabled;
    g("setWindowStart").value = cfg.autopilot_window_start || "18:00";
    g("setWindowEnd").value = cfg.autopilot_window_end || "23:00";
    g("setAutopilotTz").value = cfg.autopilot_timezone || "Europe/London";
    if (g("setAutopilotMin")) {
      g("setAutopilotMin").value = cfg.autopilot_min_minutes ?? 45;
    }
    if (g("setAutopilotMax")) {
      g("setAutopilotMax").value = cfg.autopilot_max_minutes ?? 120;
    }
    g("setAutopilotChaster").checked = !!cfg.autopilot_allow_chaster;
    g("setAutopilotPunish").value = cfg.autopilot_punish_seconds ?? 600;
    g("setBotName").value = cfg.bot_name || "Keyholder";
    g("setDommeTitle").value = cfg.domme_title || "Mistress";
  }

  function readSettings() {
    const g = (id) => document.getElementById(id);
    let minSec = partsToSeconds(g("minAddValue").value, g("minAddUnit").value);
    let maxSec = partsToSeconds(g("maxAddValue").value, g("maxAddUnit").value);
    if (minSec > maxSec) {
      const tmp = minSec;
      minSec = maxSec;
      maxSec = tmp;
    }
    let gapMin = Math.max(5, Number(g("setAutopilotMin")?.value) || 45);
    let gapMax = Math.max(5, Number(g("setAutopilotMax")?.value) || 120);
    if (gapMin > gapMax) {
      const tmp = gapMin;
      gapMin = gapMax;
      gapMax = tmp;
    }
    return {
      min_add_time_seconds: minSec,
      max_add_time_seconds: maxSec,
      soft_add_time_seconds: minSec,
      hard_add_time_seconds: maxSec,
      default_add_time_seconds: maxSec,
      auto_punish_enabled: g("setAutoPunishEnabled").checked,
      auto_punish_seconds: Number(g("setAutoPunishSeconds").value) || 600,
      autopilot_enabled: g("setAutopilotEnabled").checked,
      autopilot_window_start: g("setWindowStart").value.trim() || "18:00",
      autopilot_window_end: g("setWindowEnd").value.trim() || "23:00",
      autopilot_timezone: g("setAutopilotTz").value.trim() || "Europe/London",
      autopilot_min_minutes: gapMin,
      autopilot_max_minutes: gapMax,
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
      renderAutopilotStatus(data.autopilot);
      await refreshLockboxStatus();
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

  function renderTyping(typing) {
    const el = els.typingBubble;
    if (!el) return;
    const who = el.querySelector(".typing-who");
    const list = Array.isArray(typing) ? typing : [];
    if (!list.length) {
      el.classList.add("hidden");
      if (who) who.textContent = "";
      return;
    }
    const labels = list.map((t) => t.label || t.speaker || "Someone");
    if (who) {
      who.textContent =
        labels.length === 1
          ? `${labels[0]} is typing`
          : `${labels.join(" & ")} are typing`;
    }
    el.classList.remove("hidden");
  }

  async function pingTyping(active) {
    if (!state.mainToken) return;
    try {
      await fetch("/api/ext/typing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          main_token: state.mainToken,
          room: state.room,
          active: !!active,
          label:
            state.displayName ||
            (state.role === "domme" ? "Keyholder" : "Lockee"),
        }),
      });
    } catch {
      /* ignore */
    }
  }

  function scheduleTypingPing() {
    const now = Date.now();
    if (now - state.typingLastSent > 1500) {
      state.typingLastSent = now;
      pingTyping(true);
    }
    if (state.typingTimer) clearTimeout(state.typingTimer);
    state.typingTimer = setTimeout(() => {
      pingTyping(false);
    }, 2800);
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
    renderTyping(data.typing || []);
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
    if (state.typingTimer) clearTimeout(state.typingTimer);
    pingTyping(false);
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
      e.stopPropagation();
      els.settingsStatus.textContent = "Saving…";
      try {
        const cfg = readSettings();
        const res = await fetch("/api/ext/settings/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            main_token: state.mainToken,
            config: cfg,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiDetail(data, "Save failed"));
        renderAutopilotStatus(data.autopilot);
        if (data.chaster_sync === "failed") {
          els.settingsStatus.textContent =
            "Saved for the bot. Chaster sync note: " +
            (data.chaster_sync_error || "could not update session config");
        } else {
          els.settingsStatus.textContent = "Saved. Autopilot uses these live values.";
        }
      } catch (err) {
        els.settingsStatus.textContent = String(err.message || err);
      }
    });
  }

  const teaseNowBtn = document.getElementById("autopilotTeaseNow");
  if (teaseNowBtn) {
    teaseNowBtn.addEventListener("click", async () => {
      const statusEl = document.getElementById("settingsStatus");
      if (statusEl) statusEl.textContent = "Sending tease…";
      teaseNowBtn.disabled = true;
      try {
        const res = await fetch("/api/ext/autopilot/tick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ main_token: state.mainToken }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(apiDetail(data, "Tease failed"));
        renderAutopilotStatus(data.autopilot);
        if (statusEl) {
          statusEl.textContent = data.posted
            ? "Tease posted to Group — switch rooms to see it."
            : "Tick ran but nothing was posted.";
        }
        if (state.room !== "group") {
          // Soft hint only; history poll will pick it up in group
        } else {
          await loadHistory();
        }
      } catch (err) {
        if (statusEl) statusEl.textContent = String(err.message || err);
      } finally {
        teaseNowBtn.disabled = false;
      }
    });
  }

  const lbUnlock = document.getElementById("lockboxUnlock");
  const lbLock = document.getElementById("lockboxLock");
  const lbSync = document.getElementById("lockboxSyncTime");
  const lbRefresh = document.getElementById("lockboxRefresh");
  if (lbUnlock) lbUnlock.addEventListener("click", () => lockboxAction("unlock"));
  if (lbLock) lbLock.addEventListener("click", () => lockboxAction("lock"));
  if (lbSync) lbSync.addEventListener("click", () => lockboxAction("sync_time"));
  if (lbRefresh) lbRefresh.addEventListener("click", () => refreshLockboxStatus());

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

  els.input.addEventListener("input", () => {
    autosizeInput();
    if ((els.input.value || "").trim()) scheduleTypingPing();
  });
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
