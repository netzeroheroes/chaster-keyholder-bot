(function () {
  const els = {
    gate: document.getElementById("gate"),
    gateMsg: document.getElementById("gateMsg"),
    app: document.getElementById("app"),
    roleLabel: document.getElementById("roleLabel"),
    heading: document.getElementById("heading"),
    sessionMeta: document.getElementById("sessionMeta"),
    boxStatus: document.getElementById("boxStatus"),
    settingsBtn: document.getElementById("settingsBtn"),
    kinksBtn: document.getElementById("kinksBtn"),
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
    teaseNowBtn: document.getElementById("teaseNowBtn"),
    quickUnlockBtn: document.getElementById("quickUnlockBtn"),
    quickLockBtn: document.getElementById("quickLockBtn"),
    hygieneBar: document.getElementById("hygieneBar"),
    hygieneCopy: document.getElementById("hygieneCopy"),
    playBar: document.getElementById("playBar"),
    playCopy: document.getElementById("playCopy"),
    hygRequestBtn: document.getElementById("hygRequestBtn"),
    hygApproveBtn: document.getElementById("hygApproveBtn"),
    hygDenyBtn: document.getElementById("hygDenyBtn"),
    hygUnlockBtn: document.getElementById("hygUnlockBtn"),
    hygRelockBtn: document.getElementById("hygRelockBtn"),
    hygResetBtn: document.getElementById("hygResetBtn"),
    hygKhAsk: document.getElementById("hygKhAsk"),
    hygTimeValue: document.getElementById("hygTimeValue"),
    hygTimeUnit: document.getElementById("hygTimeUnit"),
    openKinks: document.getElementById("openKinks"),
    kinksPanel: document.getElementById("kinksPanel"),
    kinksClose: document.getElementById("kinksClose"),
    kinksHelp: document.getElementById("kinksHelp"),
    kinksFilter: document.getElementById("kinksFilter"),
    kinksSelectLoves: document.getElementById("kinksSelectLoves"),
    kinksClear: document.getElementById("kinksClear"),
    kinksRefresh: document.getElementById("kinksRefresh"),
    kinkList: document.getElementById("kinkList"),
    toyList: document.getElementById("toyList"),
    kinksPlanWeek: document.getElementById("kinksPlanWeek"),
    kinksGrill: document.getElementById("kinksGrill"),
    kinksLearn: document.getElementById("kinksLearn"),
    kinksVideo: document.getElementById("kinksVideo"),
    kinksGame: document.getElementById("kinksGame"),
    kinksSave: document.getElementById("kinksSave"),
    kinksStatus: document.getElementById("kinksStatus"),
  };

  const kitState = {
    kinks: [],
    toys: [],
    selectedKinks: new Set(),
    selectedToys: new Set(),
    username: "",
    source: "",
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
    seenCounts: { group: null, private: null },
  };

  const FALLBACK_VOICE = {
    tone: {
      cruel: "No-nonsense. Dry, precise, a little mean. Enjoy his wait. Do not soothe him.",
      elegant: "Well-mannered, commanding, dignified. Quiet authority. Never crude for its own sake.",
      playful: "Frisky and mischievous. Short dares. Laugh at him. Not a lecture.",
      warm: "Fond and firmly in control. Tease with affection. Still deny. Never a therapist.",
      soft: "Silky, gentle authority. Soft-spoken. The cage is still the point.",
      humiliatrix: "Degrading and specific. The cage is the joke. Never kind for free.",
      custom: "Your custom tone. Write exactly how this bot should talk.",
    },
    intensity: {
      tease: "Light pressure. Chat first. Lock changes are a spice, not every turn.",
      firm: "Tease and command in the same breath. Default keyholder energy.",
      strict: "Short orders. Less chat. Use the lock when he pushes. No essays.",
      custom: "Your custom intensity. How hard this bot pushes each turn.",
    },
    samples: {
      cruel: "Hey you. Tell me your kinks and a hard limit. Now.",
      elegant: "Good. You are locked. Tell me a limit, then a kink I may use.",
      playful: "Oh we're doing this. What's a kink you hope I won't use?",
      warm: "Mmm. Stay denied for me. What turns you on that I can use against you?",
      soft: "Easy. The cage stays. Whisper a kink, and a line you will not cross.",
      humiliatrix: "Hey you. That pathetic thing is locked. Kinks. Limits. Don't waste my time.",
      custom: "Hey you. Tell me your kinks and a hard limit.",
    },
  };
  let voiceCatalog = FALLBACK_VOICE;

  function setVoiceCatalog(cat) {
    if (cat && cat.tone) voiceCatalog = cat;
  }

  function toneBlurb(key) {
    return (voiceCatalog.tone && voiceCatalog.tone[key]) || FALLBACK_VOICE.tone[key] || "";
  }

  function intensityBlurb(key) {
    return (voiceCatalog.intensity && voiceCatalog.intensity[key]) || FALLBACK_VOICE.intensity[key] || "";
  }

  function bindVoiceCard(ids) {
    const voice = document.getElementById(ids.voice);
    const blurb = document.getElementById(ids.voiceBlurb);
    const intensity = document.getElementById(ids.intensity);
    const iBlurb = document.getElementById(ids.intensityBlurb);
    const sample = document.getElementById(ids.sample);
    if (voice && blurb) {
      voice.addEventListener("change", () => {
        blurb.value = toneBlurb(voice.value);
        if (sample && sample.dataset.custom !== "1") {
          const s = (voiceCatalog.samples || FALLBACK_VOICE.samples)[voice.value];
          if (s) sample.value = s;
        }
      });
      blurb.addEventListener("input", () => {
        if (voice.value !== "custom" && blurb.value.trim() !== toneBlurb(voice.value).trim()) {
          voice.value = "custom";
        }
      });
    }
    if (intensity && iBlurb) {
      intensity.addEventListener("change", () => {
        iBlurb.value = intensityBlurb(intensity.value);
      });
      iBlurb.addEventListener("input", () => {
        if (
          intensity.value !== "custom" &&
          iBlurb.value.trim() !== intensityBlurb(intensity.value).trim()
        ) {
          intensity.value = "custom";
        }
      });
    }
    if (sample) {
      sample.addEventListener("input", () => {
        sample.dataset.custom = sample.value.trim() ? "1" : "";
      });
    }
  }

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

  function renderTabBadges(counts) {
    const rooms = counts && typeof counts === "object" ? counts : {};
    ["group", "private"].forEach((room) => {
      const n = Number(rooms[room] || 0);
      if (state.seenCounts[room] == null) state.seenCounts[room] = n;
      const seen = Number(state.seenCounts[room] || 0);
      const unread = Math.max(0, n - seen);
      const badge = document.querySelector(`[data-badge="${room}"]`);
      if (!badge) return;
      if (room === state.room) {
        state.seenCounts[room] = n;
        badge.classList.add("hidden");
        badge.classList.remove("dot");
        badge.textContent = "";
        return;
      }
      if (unread <= 0) {
        badge.classList.add("hidden");
        badge.textContent = "";
        return;
      }
      badge.classList.remove("hidden");
      if (unread > 9) {
        badge.textContent = "";
        badge.classList.add("dot");
      } else {
        badge.textContent = String(unread);
        badge.classList.remove("dot");
      }
    });
  }

  function updateRoomUi() {
    els.roomTabs.querySelectorAll(".room-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.room === state.room);
    });
    els.app.classList.toggle("room-private", state.room === "private");
    els.app.classList.toggle("room-group", state.room !== "private");
    if (state.room === "private") {
      els.heading.textContent = "Private";
      els.roomHint.textContent = "Private — lockee cannot see this";
      els.input.placeholder = "Plan with the AI… he cannot see this";
    } else {
      els.heading.textContent = "Group";
      els.roomHint.textContent = "Group — lockee can see this";
      els.input.placeholder =
        state.chasterRole === "keyholder"
          ? "Message as keyholder… he can see this"
          : "Message as lockee…";
    }
  }

  function isBotMessage(m) {
    if (m && m.from_bot === true) return true;
    if (m && m.from_bot === false) return false;
    const who = String((m && m.speaker) || "");
    if (/^(Domme|Sub|Lockee|Keyholder\s*[\(@])/i.test(who)) return false;
    const bot = String(state.botName || "Keyholder");
    return !who || who === bot || /^keyholder$/i.test(who) || /^bot$/i.test(who);
  }

  function displayWho(m) {
    const who = String((m && m.speaker) || "");
    if (isBotMessage(m)) {
      if (!who || /^keyholder$/i.test(who)) return "Bot";
      return who;
    }
    if (/^Domme\b/i.test(who)) return who.replace(/^Domme/i, "Keyholder");
    if (/^Sub\b/i.test(who)) return who.replace(/^Sub/i, "Lockee");
    return who || (state.room === "private" ? "Keyholder" : "Lockee");
  }

  function messageClass(m) {
    if (isBotMessage(m)) return "bot";
    if (state.room === "private") return "Domme";
    const who = String((m && m.speaker) || "");
    if (who.startsWith("Domme") || who.startsWith("Keyholder")) return "Domme";
    if (who.startsWith("Sub") || who.startsWith("Lockee")) return "Sub";
    return "bot";
  }

  function renderMessages(messages) {
    const prev = state.lastCount;
    const grew = messages.length > prev && prev >= 0;
    const added = grew ? messages.length - prev : 0;
    els.messages.innerHTML = "";
    for (const m of messages) {
      const div = document.createElement("div");
      const who = displayWho(m);
      const cls = messageClass(m);
      div.className = `msg ${cls}`;
      div.innerHTML = `<span class="who">${who}</span>`;
      if (m.content && !String(m.content).startsWith("[image]")) {
        div.append(document.createTextNode(m.content));
      } else if (m.content && !m.image_url) {
        div.append(document.createTextNode(m.content));
      }
      if (m.image_url) {
        const img = document.createElement("img");
        img.className = "chat-image";
        img.src = m.image_url;
        img.alt = m.content || "Tease image";
        div.appendChild(img);
      }
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
    state.botName = data.bot_name || "Keyholder";
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
    renderAutopilotStatus(data.autopilot);
    renderHygiene(data.hygiene);
    renderPlaySession(data.play_session);
    renderBoxStatus(data.lockbox);
    els.sessionMeta.textContent = [
      s.wearer_username && `Lockee: ${s.wearer_username}`,
      s.keyholder_username && `KH: ${s.keyholder_username}`,
    ]
      .filter(Boolean)
      .join(" · ");

    if (s.app_role === "domme" || s.role === "keyholder") {
      els.privateTab.classList.remove("hidden");
      if (els.settingsBtn) els.settingsBtn.classList.remove("hidden");
      if (els.kinksBtn) els.kinksBtn.classList.remove("hidden");
      if (els.teaseNowBtn) els.teaseNowBtn.classList.remove("hidden");
      if (els.quickUnlockBtn) els.quickUnlockBtn.classList.remove("hidden");
      if (els.quickLockBtn) els.quickLockBtn.classList.remove("hidden");
      const khBar = document.getElementById("khBar");
      if (khBar) khBar.classList.remove("hidden");
      syncAllSexPicks(data.bot_sex || "female");
    } else {
      els.privateTab.classList.add("hidden");
      if (els.settingsBtn) els.settingsBtn.classList.add("hidden");
      if (els.kinksBtn) els.kinksBtn.classList.add("hidden");
      if (els.teaseNowBtn) els.teaseNowBtn.classList.add("hidden");
      if (els.quickUnlockBtn) els.quickUnlockBtn.classList.add("hidden");
      if (els.quickLockBtn) els.quickLockBtn.classList.add("hidden");
      const khBar = document.getElementById("khBar");
      if (khBar) khBar.classList.add("hidden");
      state.room = "group";
    }
    updateRoomUi();
    els.gate.classList.add("hidden");
    els.app.classList.remove("hidden");
    if (s.app_role === "domme" || s.role === "keyholder") {
      loadEnableSettings();
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

  function renderBoxStatus(st) {
    const el = els.boxStatus;
    if (!el) return;
    if (!st || typeof st !== "object") {
      el.textContent = "Box: —";
      el.classList.remove("locked", "open");
      return;
    }
    const label = st.label || "unknown";
    el.textContent = `Box: ${label}`;
    el.classList.toggle("locked", st.locked === true);
    el.classList.toggle("open", st.locked === false);
  }

  function formatRemain(sec) {
    const s = Math.max(0, Number(sec) || 0);
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${String(r).padStart(2, "0")}`;
  }

  function renderHygiene(st) {
    const copy = els.hygieneCopy;
    const kh = state.chasterRole === "keyholder" || state.role === "domme";
    const sub = !kh;
    const status = (st && st.status) || "idle";
    const allowed = Math.max(1, Math.round((st?.allowed_seconds || 600) / 60));
    const late = !!(st && st.late);
    const remain = st && st.remaining_seconds;
    let text = "Hygiene: idle";
    if (status === "requested") {
      text = kh
        ? "Lockee requested hygiene — how long may he be unlocked?"
        : "Hygiene requested. Waiting for the keyholder to set a time.";
    } else if (status === "approved") {
      text = sub
        ? `Tap Unlock next to Group. Then Lock within ${allowed} min or there will be a consequence.`
        : `Approved. His Unlock is next to Group. Your Unlock/Lock are for teasing him out of the cage.`;
    } else if (status === "unlocked") {
      text = late
        ? "LATE — tap Lock now. Time is being added."
        : `Unlocked. Tap Lock in ${formatRemain(remain)}.`;
    } else if (status === "denied") {
      text = "Denied. Lockee may request again.";
    }
    if (copy) {
      copy.textContent = text;
      copy.classList.toggle("late", late);
    }
    const show = (el, on) => {
      if (el) el.classList.toggle("hidden", !on);
    };
    const busy = status === "requested" || status === "approved" || status === "unlocked";
    show(els.hygieneBar, busy || status === "denied");
    show(
      els.hygRequestBtn,
      sub && (status === "idle" || status === "denied" || status === "requested")
    );
    if (els.hygRequestBtn) {
      els.hygRequestBtn.classList.toggle("pending", status === "requested");
      els.hygRequestBtn.textContent =
        status === "requested" ? "Requested" : "Hygiene";
    }
    show(els.hygKhAsk, kh && status === "requested");
    show(els.hygUnlockBtn, sub && status === "approved");
    show(els.hygRelockBtn, sub && status === "unlocked");
    if (els.hygRelockBtn && status === "unlocked" && remain != null && !late) {
      els.hygRelockBtn.textContent = `Lock ${formatRemain(remain)}`;
    } else if (els.hygRelockBtn) {
      els.hygRelockBtn.textContent = late ? "Lock (late)" : "Lock";
    }
    show(els.hygResetBtn, kh && status !== "idle");
  }

  function renderPlaySession(st) {
    const bar = els.playBar;
    const copy = els.playCopy;
    if (!bar || !copy) return;
    const kh = state.chasterRole === "keyholder" || state.role === "domme";
    if (!kh) {
      bar.classList.add("hidden");
      return;
    }
    const status = (st && st.status) || "idle";
    const rate = Number(st && st.rate) || 0;
    const elapsed = Number(st && st.elapsed_seconds) || 0;
    const pending = Number(st && st.pending_add_seconds) || 0;
    let text = "";
    let showBar = false;
    if (status === "running") {
      showBar = true;
      text =
        rate > 0
          ? `Out ${formatRemain(elapsed)} — ${rate}× → +${Math.max(
              1,
              Math.round(pending / 60)
            )} min when you Lock`
          : `Out ${formatRemain(elapsed)}. No price set — Lock will not add time.`;
    } else if (rate > 0) {
      showBar = true;
      text = `Price: ${rate} min locked per min out. Unlock starts the timer.`;
    }
    copy.textContent = text || "Play: idle";
    bar.classList.toggle("hidden", !showBar);
  }

  function hygieneAllowedSeconds() {
    const value = els.hygTimeValue ? els.hygTimeValue.value : 10;
    const unit = els.hygTimeUnit ? els.hygTimeUnit.value : "minutes";
    return partsToSeconds(value, unit);
  }

  async function hygieneAction(action) {
    setStatus(`${action}…`);
    try {
      const body = { main_token: state.mainToken, action };
      if (action === "approve") body.allowed_seconds = hygieneAllowedSeconds();
      const res = await fetch("/api/ext/hygiene", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Hygiene action failed"));
      renderHygiene(data.hygiene);
      if (data.lockbox && data.lockbox.label) renderBoxStatus(data.lockbox);
      state.lastCount = -1;
      await loadHistory();
      setStatus("");
    } catch (err) {
      setStatus(String(err.message || err));
    }
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
    const mode = st.manual_only
      ? "MANUAL (no timer)"
      : st.time_source === "chaster"
        ? "time from Chaster"
        : "time ?";
    const hyg = st.hygiene_unlock ? "hygiene→unlock" : "hygiene off";
    const bits = [sync, mode, hyg, state];
    if (!st.configured) {
      el.textContent =
        "Lockbox: NOT CONFIGURED — set RAD_API_TOKEN + RAD_LOCKBOX_SYNC_ENABLED=true on Render";
      return;
    }
    if (st.last_sync && st.last_sync.chaster_frozen) bits.push("Chaster FROZEN");
    if (st.last_sync && st.last_sync.chaster_time_hidden)
      bits.push("Chaster timer HIDDEN");
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
    const chatStatus = els.status;
    const note = `${action === "unlock" ? "Unlocking" : action === "lock" ? "Locking" : action}…`;
    if (statusEl) statusEl.textContent = note;
    if (chatStatus) chatStatus.textContent = note;
    if (els.quickUnlockBtn) els.quickUnlockBtn.disabled = true;
    if (els.quickLockBtn) els.quickLockBtn.disabled = true;
    try {
      const res = await fetch("/api/ext/lockbox/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken, action }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Lockbox action failed"));
      renderLockboxStatus(data);
      if (data.lockbox) renderBoxStatus(data.lockbox);
      if (data.play_session) renderPlaySession(data.play_session);
      const ls = data.last_sync || {};
      const done = ls.detail || `Lockbox ${action} done.`;
      if (statusEl) statusEl.textContent = done;
      if (chatStatus) {
        chatStatus.textContent = data.chat
          ? `${done} Conversation started.`
          : data.chat_error || done;
      }
      if (action === "unlock" || action === "lock") {
        await loadHistory();
      }
    } catch (err) {
      const msg = String(err.message || err);
      if (statusEl) statusEl.textContent = msg;
      if (chatStatus) chatStatus.textContent = msg;
    } finally {
      if (els.quickUnlockBtn) els.quickUnlockBtn.disabled = false;
      if (els.quickLockBtn) els.quickLockBtn.disabled = false;
    }
  }

  const ENABLE_FLAGS = [
    ["bot_allow_add_time", "setBotAllowAddTime"],
    ["bot_allow_remove_time", "setBotAllowRemoveTime"],
    ["bot_allow_freeze", "setBotAllowFreeze"],
    ["bot_allow_hide_timer", "setBotAllowHideTimer"],
    ["bot_allow_pillory", "setBotAllowPillory"],
  ];

  function setEnableFlags(cfg) {
    const flagOn = (key) => cfg[key] !== false;
    ENABLE_FLAGS.forEach(([key, setId]) => {
      const formEl = document.getElementById(setId);
      if (formEl) formEl.checked = flagOn(key);
    });
  }

  function readEnableFlags() {
    const out = {};
    ENABLE_FLAGS.forEach(([key, setId]) => {
      const formEl = document.getElementById(setId);
      out[key] = formEl ? formEl.checked : true;
    });
    return out;
  }

  async function loadEnableSettings() {
    if (!state.mainToken) return;
    try {
      const res = await fetch("/api/ext/settings/get", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return;
      fillSettings(data.config || {});
      fillHerTaste(data);
      if (data.voice_catalog) setVoiceCatalog(data.voice_catalog);
      syncAllSexPicks((data.config || {}).bot_sex || "female");
    } catch (_) {
      /* Settings stay at defaults until the panel is opened */
    }
  }

  function setKhStatus(text) {
    const el = document.getElementById("khBarStatus");
    if (el) el.textContent = text || "";
  }

  function syncAllSexPicks(value) {
    const v = String(value || "female").toLowerCase();
    const sex = ["female", "male", "other"].includes(v) ? v : "female";
    document.querySelectorAll(".sex-picks .sex-pick").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sex === sex);
    });
    const hidden = document.getElementById("setBotSex");
    if (hidden) hidden.value = sex;
  }

  function readBotSex() {
    const active = document.querySelector(".sex-picks .sex-pick.active");
    if (active && active.dataset.sex) return active.dataset.sex;
    return document.getElementById("setBotSex")?.value || "female";
  }

  async function persistBotSex(sex) {
    syncAllSexPicks(sex);
    if (sex === "male") {
      const personaEl = document.getElementById("setBotPersona");
      if (personaEl) personaEl.value = "bull";
    }
    if (!state.mainToken) return;
    setKhStatus("Saving bot sex…");
    try {
      const config = { bot_sex: sex };
      if (sex === "male") config.bot_persona = "bull";
      const res = await fetch("/api/ext/settings/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          main_token: state.mainToken,
          config,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Could not save bot sex"));
      setKhStatus(
        sex === "male"
          ? "Bot is the bull. Saved — it plays with you; he stays locked."
          : `Bot sex: ${sex}. Saved.`
      );
    } catch (err) {
      setKhStatus(String(err.message || err));
    }
  }

  function linesList(id) {
    return (document.getElementById(id)?.value || "")
      .split(/[\n,;]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .slice(0, 40);
  }

  function fillHerTaste(data) {
    const g = (id) => document.getElementById(id);
    const ons = data.her_turn_ons || [];
    const fan = data.her_fantasies || [];
    if (g("setHerTurnOns")) {
      g("setHerTurnOns").value = Array.isArray(ons) ? ons.join("\n") : "";
    }
    if (g("setHerFantasies")) {
      g("setHerFantasies").value = Array.isArray(fan) ? fan.join("\n") : "";
    }
    const last = Array.isArray(data.her_orgasms)
      ? data.her_orgasms.slice(-1)[0]
      : null;
    const log = g("herOrgasmLog");
    if (log) {
      if (last && last.rating) {
        const note = last.note ? ` — ${last.note}` : "";
        log.textContent = `Last orgasm: ${last.rating}/10${
          last.when ? " (" + last.when + ")" : ""
        }${note}`;
      } else {
        log.textContent = "Last orgasm: not logged yet.";
      }
    }
  }

  function bindSexPicks() {
    document.querySelectorAll(".sex-picks").forEach((picks) => {
      picks.addEventListener("click", (e) => {
        const btn = e.target.closest(".sex-pick");
        if (!btn) return;
        persistBotSex(btn.dataset.sex || "female");
      });
    });
  }

  function selectedOrgasm() {
    const active = document.querySelector(".orgasm-pick.active");
    return active ? Number(active.dataset.rating) : 0;
  }

  function bindOrgasmPicks() {
    const picks = document.getElementById("orgasmPicks");
    if (!picks) return;
    picks.addEventListener("click", (e) => {
      const btn = e.target.closest(".orgasm-pick");
      if (!btn) return;
      picks.querySelectorAll(".orgasm-pick").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
    });
  }

  async function applyOrgasm(where) {
    const n = selectedOrgasm();
    if (!n) {
      setKhStatus("Pick 1–10 first, then Tell him or Keep private.");
      return;
    }
    const note = (document.getElementById("orgasmNote")?.value || "").trim();
    const line = note
      ? `I came. Orgasm rating ${n}/10. Note: ${note}`
      : `I came. Orgasm rating ${n}/10. Use this on him.`;
    if (where === "private") {
      await switchRoom("private");
      await sendMessage(
        `${line} Keep the rating private. Let him know I came, not the number.`
      );
      setKhStatus(
        `Logged ${n}/10 in private. He’ll see that you came — not the score.`
      );
      return;
    }
    if (state.room !== "group") await switchRoom("group");
    await sendMessage(line);
    setKhStatus(`Logged ${n}/10 and told him.`);
  }

  async function learnHer() {
    if (state.room !== "private") await switchRoom("private");
    await sendMessage(
      "Ask me what turns me on. Learn my fantasies so you can use the lock for my pleasure."
    );
    setKhStatus("Ask her in Private — it will remember what she says.");
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
    setEnableFlags(cfg);
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
    const PERSONAS = ["friend", "domme", "bull", "male_dom"];
    const SEXES = ["female", "male", "other"];
    const VOICES = ["cruel", "elegant", "playful", "warm", "soft", "humiliatrix", "custom"];
    const personaEl = g("setBotPersona");
    if (personaEl) {
      const p = String(cfg.bot_persona || "friend").toLowerCase();
      personaEl.value = PERSONAS.includes(p) ? p : "friend";
    }
    const sexVal = SEXES.includes(String(cfg.bot_sex || "").toLowerCase())
      ? String(cfg.bot_sex).toLowerCase()
      : "female";
    syncAllSexPicks(sexVal);
    const voiceEl = g("setBotVoice");
    const v = VOICES.includes(String(cfg.bot_voice || "").toLowerCase())
      ? String(cfg.bot_voice).toLowerCase()
      : "cruel";
    if (voiceEl) voiceEl.value = v;
    const blurbEl = g("setBotVoiceBlurb");
    if (blurbEl) blurbEl.value = cfg.bot_voice_blurb || toneBlurb(v);
    const sampleEl = g("setBotVoiceSample");
    if (sampleEl) {
      sampleEl.value = cfg.bot_voice_sample || "";
      sampleEl.dataset.custom = cfg.bot_voice_sample ? "1" : "";
    }
    const intensityEl = g("setBotIntensity");
    const i = ["tease", "firm", "strict", "custom"].includes(
      String(cfg.bot_intensity || "").toLowerCase()
    )
      ? String(cfg.bot_intensity).toLowerCase()
      : "firm";
    if (intensityEl) intensityEl.value = i;
    const iBlurbEl = g("setBotIntensityBlurb");
    if (iBlurbEl) iBlurbEl.value = cfg.bot_intensity_blurb || intensityBlurb(i);
    const quirksEl = g("setBotQuirks");
    if (quirksEl) quirksEl.value = cfg.bot_quirks || "";
    if (g("setBotBio")) g("setBotBio").value = cfg.bot_bio || "";
    if (g("setBotGreeting")) g("setBotGreeting").value = cfg.bot_greeting || "";
    const allowP = secondsToParts(cfg.hygiene_allowed_seconds ?? 600, "minutes");
    const lateP = secondsToParts(cfg.hygiene_late_punish_seconds ?? 1800, "minutes");
    if (g("hygAllowValue")) {
      g("hygAllowValue").value = allowP.value;
      g("hygAllowUnit").value = allowP.unit === "days" ? "hours" : allowP.unit;
    }
    if (els.hygTimeValue) els.hygTimeValue.value = allowP.value;
    if (els.hygTimeUnit) {
      els.hygTimeUnit.value = allowP.unit === "days" ? "hours" : allowP.unit;
    }
    if (g("hygPunishValue")) {
      g("hygPunishValue").value = lateP.value;
      g("hygPunishUnit").value = lateP.unit === "days" ? "hours" : lateP.unit;
    }
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
      ...readEnableFlags(),
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
      bot_persona: g("setBotPersona")?.value || "friend",
      bot_sex: readBotSex(),
      bot_voice: g("setBotVoice")?.value || "cruel",
      bot_voice_sample: (g("setBotVoiceSample")?.value || "").trim().slice(0, 800),
      bot_voice_blurb: (g("setBotVoiceBlurb")?.value || "").trim().slice(0, 800),
      bot_intensity: g("setBotIntensity")?.value || "firm",
      bot_intensity_blurb: (g("setBotIntensityBlurb")?.value || "").trim().slice(0, 800),
      bot_quirks: (g("setBotQuirks")?.value || "").trim().slice(0, 800),
      bot_bio: (g("setBotBio")?.value || "").trim().slice(0, 1200),
      bot_greeting: (g("setBotGreeting")?.value || "").trim().slice(0, 400),
      hygiene_allowed_seconds: partsToSeconds(
        g("hygAllowValue")?.value || 10,
        g("hygAllowUnit")?.value || "minutes"
      ),
      hygiene_late_punish_seconds: partsToSeconds(
        g("hygPunishValue")?.value || 30,
        g("hygPunishUnit")?.value || "minutes"
      ),
    };
  }

  function kitMatchesFilter(name, filter) {
    if (!filter) return true;
    return String(name || "").toLowerCase().includes(filter);
  }

  function renderKinkLists() {
    if (!els.kinkList || !els.toyList) return;
    const filter = (els.kinksFilter?.value || "").trim().toLowerCase();
    els.kinkList.innerHTML = "";
    els.toyList.innerHTML = "";
    const kinks = kitState.kinks.filter((k) => kitMatchesFilter(k.name, filter));
    const toys = kitState.toys.filter((t) => kitMatchesFilter(t.name, filter));
    if (!kinks.length) {
      const p = document.createElement("p");
      p.className = "meta";
      p.textContent = "No matching kinks.";
      els.kinkList.appendChild(p);
    }
    for (const kink of kinks) {
      const label = document.createElement("label");
      label.className = "kit-item";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = kitState.selectedKinks.has(kink.name);
      box.addEventListener("change", () => {
        if (box.checked) kitState.selectedKinks.add(kink.name);
        else kitState.selectedKinks.delete(kink.name);
      });
      const span = document.createElement("span");
      span.textContent = kink.name;
      const rating = document.createElement("em");
      rating.className = `kit-rating ${kink.rating || "other"}`;
      rating.textContent = kink.rating && kink.rating !== "other" ? kink.rating : "";
      label.append(box, span, rating);
      els.kinkList.appendChild(label);
    }
    if (!toys.length) {
      const p = document.createElement("p");
      p.className = "meta";
      p.textContent = "No matching toys.";
      els.toyList.appendChild(p);
    }
    for (const toy of toys) {
      const label = document.createElement("label");
      label.className = "kit-item";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = kitState.selectedToys.has(toy.name);
      box.addEventListener("change", () => {
        if (box.checked) kitState.selectedToys.add(toy.name);
        else kitState.selectedToys.delete(toy.name);
      });
      const span = document.createElement("span");
      span.textContent = toy.name;
      label.append(box, span);
      els.toyList.appendChild(label);
    }
  }

  async function loadKinkCatalog() {
    if (els.kinksStatus) els.kinksStatus.textContent = "Loading his profile…";
    const res = await fetch("/api/ext/kink-catalog", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ main_token: state.mainToken }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(data, "Could not load kinks"));
    kitState.kinks = data.kinks || [];
    kitState.toys = data.toys || [];
    kitState.username = data.username || "";
    kitState.source = data.source || "";
    if (Array.isArray(data.selected_kinks)) {
      kitState.selectedKinks = new Set(data.selected_kinks);
    }
    if (Array.isArray(data.selected_toys)) {
      kitState.selectedToys = new Set(data.selected_toys);
    }
    const who = kitState.username ? `${kitState.username}'s` : "his";
    const src =
      kitState.source === "chaster"
        ? `From ${who} Chaster profile.`
        : kitState.source === "mixed"
          ? `From ${who} Chaster profile, with starter items filling empty lists.`
          : "Chaster list unavailable — using a starter catalog you can still tick.";
    if (els.kinksHelp) {
      els.kinksHelp.textContent = `${src} Tick what you want incorporated this session or week.`;
    }
    if (els.kinksStatus) {
      els.kinksStatus.textContent = `${kitState.kinks.length} kinks · ${kitState.toys.length} toys`;
    }
    renderKinkLists();
  }

  function openKinks() {
    if (!els.kinksPanel) return;
    closeSettings();
    els.kinksPanel.classList.remove("hidden");
    els.kinksPanel.setAttribute("aria-hidden", "false");
    if (els.kinksFilter) els.kinksFilter.value = "";
    loadKinkCatalog().catch((err) => {
      if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
    });
  }

  function closeKinks() {
    if (!els.kinksPanel) return;
    els.kinksPanel.classList.add("hidden");
    els.kinksPanel.setAttribute("aria-hidden", "true");
  }

  async function saveSessionKit() {
    const res = await fetch("/api/ext/session-kit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        main_token: state.mainToken,
        session_kinks: [...kitState.selectedKinks],
        session_toys: [...kitState.selectedToys],
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiDetail(data, "Save failed"));
    kitState.selectedKinks = new Set(data.session_kinks || []);
    kitState.selectedToys = new Set(data.session_toys || []);
    return data;
  }

  async function askWeekPlan() {
    try {
      await saveSessionKit();
    } catch (err) {
      if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
      return;
    }
    closeKinks();
    if (state.room !== "private") {
      await switchRoom("private");
    }
    const kinks = [...kitState.selectedKinks];
    const toys = [...kitState.selectedToys];
    const kitLine = [
      kinks.length ? `Kinks I want in: ${kinks.join(", ")}.` : "",
      toys.length ? `Toys I want in: ${toys.join(", ")}.` : "",
    ]
      .filter(Boolean)
      .join(" ");
    const prompt = [
      "Help me plan this week as his keyholder.",
      kitLine || "I have not ticked a kit yet — use his profile loves and listed toys.",
      "Give me a day-by-day plan and specific suggestions for keeping him horny, denied, and submissive — when to tease, when to go colder, rituals, and how to use the lock.",
      "This is planning with me only. Do not execute in group yet.",
    ].join(" ");
    await sendMessage(prompt);
  }

  async function askPlay(kind) {
    const prompts = {
      interview:
        "Grill him about his kinks and the toys we can use against him. One question at a time. Start now.",
      video:
        "Find a porn video that matches this lock's current kinks and tease him with it.",
      game:
        "Create a game for us to play with him while he's locked. Look online if you need ideas.",
    };
    const text = prompts[kind];
    if (!text) return;
    closeKinks();
    if (kind === "interview" || kind === "video") {
      if (state.room !== "group") await switchRoom("group");
    }
    await sendMessage(text);
  }

  async function openSettings() {
    if (!els.settingsPanel) return;
    els.settingsStatus.textContent = "Loading…";
    els.settingsPanel.classList.remove("hidden");
    els.settingsPanel.setAttribute("aria-hidden", "false");
    const card = els.settingsPanel.querySelector(".settings-card");
    if (card) card.scrollTop = 0;
    try {
      const res = await fetch("/api/ext/settings/get", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ main_token: state.mainToken }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(apiDetail(data, "Could not load settings"));
      fillSettings(data.config || {});
      fillHerTaste(data);
      if (data.voice_catalog) setVoiceCatalog(data.voice_catalog);
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
    if (data.hygiene) renderHygiene(data.hygiene);
    if (data.play_session) renderPlaySession(data.play_session);
    if (data.lockbox) renderBoxStatus(data.lockbox);
    if (data.room_counts) renderTabBadges(data.room_counts);
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
      if (data.play_session) renderPlaySession(data.play_session);
      state.lastCount = -1;
      state.stickToBottom = true;
      const posted = data.group_posts || [];
      if (data.open_private && state.role === "domme") {
        setStatus("Moved the plan to Private.");
        await switchRoom("private");
      } else if (posted.length && state.room !== "group") {
        setStatus(`Posted ${posted.length} to Group.`);
        await switchRoom("group");
      } else {
        await loadHistory();
        setStatus(posted.length ? `Posted ${posted.length} to Group.` : "");
      }
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
    if (btn.dataset.action === "kinks" || btn.id === "kinksBtn") {
      openKinks();
      return;
    }
    if (btn.classList.contains("kh-action") || !btn.dataset.room) {
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
  if (els.kinksBtn) {
    els.kinksBtn.addEventListener("click", (e) => {
      e.preventDefault();
      openKinks();
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
            her_turn_ons: linesList("setHerTurnOns"),
            her_fantasies: linesList("setHerFantasies"),
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
        setEnableFlags(data.config || cfg);
      } catch (err) {
        els.settingsStatus.textContent = String(err.message || err);
      }
    });
  }

  async function fireTeaseNow() {
    const btn = els.teaseNowBtn;
    const statusEl = els.status;
    if (statusEl) statusEl.textContent = "Sending tease…";
    if (btn) btn.disabled = true;
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
          ? "Tease posted to Group."
          : "Tick ran but nothing was posted.";
      }
      if (data.posted && state.room !== "group") {
        await switchRoom("group");
      } else {
        await loadHistory();
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = String(err.message || err);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  if (els.teaseNowBtn) {
    els.teaseNowBtn.addEventListener("click", () => {
      fireTeaseNow();
    });
  }
  if (els.quickUnlockBtn) {
    els.quickUnlockBtn.addEventListener("click", () => lockboxAction("unlock"));
  }
  if (els.quickLockBtn) {
    els.quickLockBtn.addEventListener("click", () => lockboxAction("lock"));
  }
  if (els.hygRequestBtn) {
    els.hygRequestBtn.addEventListener("click", () => hygieneAction("request"));
  }
  if (els.hygApproveBtn) {
    els.hygApproveBtn.addEventListener("click", () => hygieneAction("approve"));
  }
  if (els.hygDenyBtn) {
    els.hygDenyBtn.addEventListener("click", () => hygieneAction("deny"));
  }
  if (els.hygResetBtn) {
    els.hygResetBtn.addEventListener("click", () => hygieneAction("reset"));
  }
  if (els.hygUnlockBtn) {
    els.hygUnlockBtn.addEventListener("click", () => hygieneAction("unlock"));
  }
  if (els.hygRelockBtn) {
    els.hygRelockBtn.addEventListener("click", () => hygieneAction("relock"));
  }
  if (els.openKinks) {
    els.openKinks.addEventListener("click", () => openKinks());
  }
  if (els.kinksClose) {
    els.kinksClose.addEventListener("click", closeKinks);
  }
  if (els.kinksPanel) {
    els.kinksPanel.addEventListener("click", (e) => {
      if (e.target === els.kinksPanel) closeKinks();
    });
  }
  if (els.kinksFilter) {
    els.kinksFilter.addEventListener("input", () => renderKinkLists());
  }
  if (els.kinksSelectLoves) {
    els.kinksSelectLoves.addEventListener("click", () => {
      for (const kink of kitState.kinks) {
        if (kink.rating === "love") kitState.selectedKinks.add(kink.name);
      }
      renderKinkLists();
    });
  }
  if (els.kinksClear) {
    els.kinksClear.addEventListener("click", () => {
      kitState.selectedKinks.clear();
      kitState.selectedToys.clear();
      renderKinkLists();
    });
  }
  if (els.kinksRefresh) {
    els.kinksRefresh.addEventListener("click", () => {
      loadKinkCatalog().catch((err) => {
        if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
      });
    });
  }
  if (els.kinksSave) {
    els.kinksSave.addEventListener("click", async () => {
      if (els.kinksStatus) els.kinksStatus.textContent = "Saving…";
      try {
        await saveSessionKit();
        if (els.kinksStatus) els.kinksStatus.textContent = "Saved. She will use this kit.";
      } catch (err) {
        if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
      }
    });
  }
  if (els.kinksPlanWeek) {
    els.kinksPlanWeek.addEventListener("click", () => {
      askWeekPlan().catch((err) => {
        if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
      });
    });
  }
  const playErr = (err) => {
    if (els.kinksStatus) els.kinksStatus.textContent = String(err.message || err);
  };
  if (els.kinksGrill) {
    els.kinksGrill.addEventListener("click", () => {
      askPlay("interview").catch(playErr);
    });
  }
  if (els.kinksLearn) {
    els.kinksLearn.addEventListener("click", () => {
      closeKinks();
      learnHer().catch(playErr);
    });
  }
  if (els.kinksVideo) {
    els.kinksVideo.addEventListener("click", () => {
      askPlay("video").catch(playErr);
    });
  }
  if (els.kinksGame) {
    els.kinksGame.addEventListener("click", () => {
      askPlay("game").catch(playErr);
    });
  }
  bindSexPicks();
  bindOrgasmPicks();
  bindVoiceCard({
    voice: "setBotVoice",
    voiceBlurb: "setBotVoiceBlurb",
    intensity: "setBotIntensity",
    intensityBlurb: "setBotIntensityBlurb",
    sample: "setBotVoiceSample",
  });
  const personaEl = document.getElementById("setBotPersona");
  if (personaEl) {
    personaEl.addEventListener("change", () => {
      const role = personaEl.value;
      if (role === "bull" || role === "male_dom") {
        persistBotSex("male");
      }
    });
  }
  const tellHim = document.getElementById("orgasmTellHim");
  const keepPriv = document.getElementById("orgasmPrivate");
  const learnBtn = document.getElementById("learnHerBtn");
  if (tellHim) {
    tellHim.addEventListener("click", () => {
      applyOrgasm("group").catch((err) => setKhStatus(String(err.message || err)));
    });
  }
  if (keepPriv) {
    keepPriv.addEventListener("click", () => {
      applyOrgasm("private").catch((err) =>
        setKhStatus(String(err.message || err))
      );
    });
  }
  if (learnBtn) {
    learnBtn.addEventListener("click", () => {
      learnHer().catch((err) => setKhStatus(String(err.message || err)));
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (els.kinksPanel && !els.kinksPanel.classList.contains("hidden")) {
      closeKinks();
    } else if (els.settingsPanel && !els.settingsPanel.classList.contains("hidden")) {
      closeSettings();
    }
  });

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
