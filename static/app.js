const state = {
  role: null,
  room: "group",
  pin: "",
  pollTimer: null,
  lastCount: 0,
  lastFingerprint: "",
  lastSpokenBotKey: "",
  sending: false,
  stickToBottom: true,
  pendingNew: 0,
  typingTimer: null,
  typingLastSent: 0,
};

const els = {
  gate: document.getElementById("gate"),
  app: document.getElementById("app"),
  pinField: document.getElementById("pinField"),
  pin: document.getElementById("pin"),
  gateStatus: document.getElementById("gateStatus"),
  roleLabel: document.getElementById("roleLabel"),
  roomTitle: document.getElementById("roomTitle"),
  roomHelp: document.getElementById("roomHelp"),
  roomTabs: document.getElementById("roomTabs"),
  dommeControls: document.getElementById("dommeControls"),
  directives: document.getElementById("directives"),
  dommeName: document.getElementById("dommeName"),
  dommeTitle: document.getElementById("dommeTitle"),
  botName: document.getElementById("botName"),
  subName: document.getElementById("subName"),
  memoryPreview: document.getElementById("memoryPreview"),
  saveScene: document.getElementById("saveScene"),
  resetChat: document.getElementById("resetChat"),
  switchRole: document.getElementById("switchRole"),
  status: document.getElementById("status"),
  modelMeta: document.getElementById("modelMeta"),
  messages: document.getElementById("messages"),
  jumpLatest: document.getElementById("jumpLatest"),
  form: document.getElementById("chatForm"),
  input: document.getElementById("input"),
  sendBtn: document.getElementById("sendBtn"),
  typingBubble: document.getElementById("typingBubble"),
  speakReplies: document.getElementById("speakReplies"),
  handsFree: document.getElementById("handsFree"),
  micBtn: document.getElementById("micBtn"),
  micTap: document.getElementById("micTap"),
  stopAudio: document.getElementById("stopAudio"),
  edgeStart: document.getElementById("edgeStart"),
  edgeStop: document.getElementById("edgeStop"),
  edgeStatus: document.getElementById("edgeStatus"),
  imagePanel: document.getElementById("imagePanel"),
  imagePrompt: document.getElementById("imagePrompt"),
  imageToGroup: document.getElementById("imageToGroup"),
  imageGen: document.getElementById("imageGen"),
  imageStatus: document.getElementById("imageStatus"),
  chasterPanel: document.getElementById("chasterPanel"),
  chasterStatus: document.getElementById("chasterStatus"),
  chasterRefresh: document.getElementById("chasterRefresh"),
  chasterWearers: document.getElementById("chasterWearers"),
  botAllowAddTime: document.getElementById("botAllowAddTime"),
  botAllowRemoveTime: document.getElementById("botAllowRemoveTime"),
  botAllowFreeze: document.getElementById("botAllowFreeze"),
  botAllowHideTimer: document.getElementById("botAllowHideTimer"),
  botAllowPillory: document.getElementById("botAllowPillory"),
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
  controlsStatus: document.getElementById("controlsStatus"),
  saveControls: document.getElementById("saveControls"),
  botPersona: document.getElementById("botPersona"),
  botSex: document.getElementById("botSex"),
  botVoice: document.getElementById("botVoice"),
  botVoiceBlurb: document.getElementById("botVoiceBlurb"),
  botIntensity: document.getElementById("botIntensity"),
  botIntensityBlurb: document.getElementById("botIntensityBlurb"),
  botVoiceSample: document.getElementById("botVoiceSample"),
  botQuirks: document.getElementById("botQuirks"),
  botBio: document.getElementById("botBio"),
  botGreeting: document.getElementById("botGreeting"),
  savePersona: document.getElementById("savePersona"),
  personaStatus: document.getElementById("personaStatus"),
  grillHim: document.getElementById("grillHim"),
  suggestVideo: document.getElementById("suggestVideo"),
  makeGame: document.getElementById("makeGame"),
  kitChips: document.getElementById("kitChips"),
  kitStatus: document.getElementById("kitStatus"),
  openKit: document.getElementById("openKit"),
  planWeek: document.getElementById("planWeek"),
  kitModal: document.getElementById("kitModal"),
  closeKit: document.getElementById("closeKit"),
  kitFilter: document.getElementById("kitFilter"),
  kitSelectLoves: document.getElementById("kitSelectLoves"),
  kitClear: document.getElementById("kitClear"),
  kitRefresh: document.getElementById("kitRefresh"),
  kitKinkList: document.getElementById("kitKinkList"),
  kitToyList: document.getElementById("kitToyList"),
  kitModalHelp: document.getElementById("kitModalHelp"),
  kitModalStatus: document.getElementById("kitModalStatus"),
  saveKit: document.getElementById("saveKit"),
  planWeekModal: document.getElementById("planWeekModal"),
};

const kitState = {
  kinks: [],
  toys: [],
  selectedKinks: new Set(),
  selectedToys: new Set(),
  username: "",
  source: "",
};

let pinsRequired = { domme: false, sub: false };
const support = Voice.supported();

function setStatus(text) {
  els.status.textContent = text || "";
}

function messageFingerprint(messages) {
  if (!messages.length) return "0";
  const last = messages[messages.length - 1];
  return [
    messages.length,
    last.speaker || "",
    String(last.content || "").slice(0, 120),
    last.image_url || "",
  ].join("|");
}

function nearBottom(el, px = 96) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < px;
}

function updateJumpBtn() {
  if (!els.jumpLatest) return;
  if (state.pendingNew > 0 && !state.stickToBottom) {
    els.jumpLatest.classList.remove("hidden");
    els.jumpLatest.textContent =
      state.pendingNew === 1 ? "↓ New message" : `↓ ${state.pendingNew} new`;
  } else {
    els.jumpLatest.classList.add("hidden");
  }
}

function scrollToLatest({ smooth = true } = {}) {
  els.messages.scrollTo({
    top: els.messages.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
  state.stickToBottom = true;
  state.pendingNew = 0;
  updateJumpBtn();
}

function renderMessages(messages, { speakNewestBot = false, forceScroll = false } = {}) {
  const prevCount = state.lastCount;
  const grew = messages.length > prevCount && prevCount >= 0;

  els.messages.innerHTML = "";
  function isBotMessage(m) {
    if (m && m.from_bot === true) return true;
    if (m && m.from_bot === false) return false;
    const who = String((m && m.speaker) || "");
    if (/^(Domme|Sub|Keyholder\s*[\(@])/i.test(who)) return false;
    return !who || /^keyholder$/i.test(who) || /^bot$/i.test(who);
  }

  function displayWho(m) {
    const who = String((m && m.speaker) || "");
    if (isBotMessage(m)) {
      if (!who || /^keyholder$/i.test(who)) return "Bot";
      return who;
    }
    if (state.room === "private") {
      if (/^Domme\b/i.test(who)) return who.replace(/^Domme/i, "Keyholder");
      return who || "Keyholder";
    }
    return who || "Keyholder";
  }

  function messageClass(m) {
    if (isBotMessage(m)) return "bot";
    if (state.room === "private") return "Domme";
    const who = String((m && m.speaker) || "");
    if (who.startsWith("Domme") || who.startsWith("Keyholder")) return "Domme";
    if (who.startsWith("Sub")) return "Sub";
    return "bot";
  }

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
      img.alt = m.content || "Generated image";
      div.appendChild(img);
    }
    els.messages.appendChild(div);
  }

  state.lastCount = messages.length;
  state.lastFingerprint = messageFingerprint(messages);

  // Stay pinned to bottom unless the user scrolled up to read history
  if (forceScroll || state.stickToBottom || prevCount <= 0) {
    scrollToLatest({ smooth: false });
  } else if (grew) {
    state.pendingNew += messages.length - prevCount;
    updateJumpBtn();
  }

  if (!speakNewestBot || !els.speakReplies?.checked) return;
  const bots = messages.filter(
    (m) => m.speaker && !String(m.speaker).startsWith("Domme") && !String(m.speaker).startsWith("Sub")
  );
  const last = bots[bots.length - 1];
  if (!last) return;
  const key = `${messages.length}:${last.content}`;
  if (key === state.lastSpokenBotKey) return;
  state.lastSpokenBotKey = key;
  speakBot(last.content);
}

if (els.messages) {
  els.messages.addEventListener("scroll", () => {
    const atBottom = nearBottom(els.messages);
    state.stickToBottom = atBottom;
    if (atBottom) {
      state.pendingNew = 0;
      updateJumpBtn();
    }
  });
}
if (els.jumpLatest) {
  els.jumpLatest.addEventListener("click", () => scrollToLatest({ smooth: true }));
}

async function speakBot(text) {
  Voice.stopListening();
  await Voice.speak(text);
  if (els.handsFree.checked && support.stt) {
    Voice.startListening({ loop: false });
    setStatus("Listening…");
  }
}

function linesListFrom(el) {
  return (el?.value || "")
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 40);
}

function fillHerTaste(data) {
  const ons = document.getElementById("herTurnOns");
  const fan = document.getElementById("herFantasies");
  if (ons) ons.value = Array.isArray(data.her_turn_ons) ? data.her_turn_ons.join("\n") : "";
  if (fan) {
    fan.value = Array.isArray(data.her_fantasies) ? data.her_fantasies.join("\n") : "";
  }
  const log = document.getElementById("herOrgasmLog");
  if (!log) return;
  const last = Array.isArray(data.her_orgasms) ? data.her_orgasms.slice(-1)[0] : null;
  if (last && last.rating) {
    const note = last.note ? ` — ${last.note}` : "";
    log.textContent = `Last orgasm: ${last.rating}/10${
      last.when ? " (" + last.when + ")" : ""
    }${note}`;
  } else {
    log.textContent = "Last orgasm: not logged yet.";
  }
}

function selectedOrgasm() {
  const active = document.querySelector(".orgasm-pick.active");
  return active ? Number(active.dataset.rating) : 0;
}

async function applyOrgasm(where) {
  const n = selectedOrgasm();
  if (!n) {
    setStatus("Pick 1–10 first, then Tell him or Keep private.");
    return;
  }
  const note = (document.getElementById("orgasmNote")?.value || "").trim();
  const line = note
    ? `I came. Orgasm rating ${n}/10. Note: ${note}`
    : `I came. Orgasm rating ${n}/10. Use this on him.`;
  if (where === "private") {
    await ensureRoom("private");
    await sendMessage(
      `${line} Keep the rating private. Let him know I came, not the number.`
    );
    return;
  }
  await ensureRoom("group");
  await sendMessage(line);
}

async function learnHer() {
  await ensureRoom("private");
  await sendMessage(
    "Ask me what turns me on. Learn my fantasies so you can use the lock for my pleasure."
  );
}

function syncSexPicks(value) {
  const picks = document.getElementById("botSexPicks");
  if (!picks) return;
  const v = String(value || "female").toLowerCase();
  picks.querySelectorAll(".sex-pick").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sex === v);
  });
}

function updateRoomChrome() {
  const isPrivate = state.room === "private";
  document.body.classList.toggle("room-private", isPrivate);
  document.body.classList.toggle("room-group", !isPrivate);
  els.roomTitle.textContent = isPrivate ? "Private — he cannot see this" : "Group — he can see this";
  els.roomHelp.textContent = isPrivate
    ? "Plan with the AI here. Orders like “taunt him” go to Group as a mystery tease."
    : "Everyone in the lock can see this. Don't dump the plan here.";

  for (const tab of els.roomTabs.querySelectorAll(".tab")) {
    tab.classList.toggle("active", tab.dataset.room === state.room);
    if (state.role === "sub" && tab.dataset.room === "private") {
      tab.classList.add("hidden");
    } else {
      tab.classList.remove("hidden");
    }
  }

  els.dommeControls.classList.toggle("hidden", state.role !== "domme");
  if (els.imagePanel) els.imagePanel.classList.add("hidden");
  els.chasterPanel.classList.toggle("hidden", state.role !== "domme");
}

async function loadChaster() {
  if (state.role !== "domme") return;
  try {
    const res = await fetch("/api/chaster/status?role=domme", {
      headers: { "X-Role-Pin": state.pin },
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    const loginBtn = document.getElementById("chasterLogin");
    if (!data.configured) {
      els.chasterStatus.textContent = "Missing CHASTER_CLIENT_ID/SECRET in .env";
      if (loginBtn) loginBtn.classList.add("hidden");
      return;
    }
    if (!data.linked) {
      els.chasterStatus.textContent =
        "Not linked — use a developer token in .env, or OAuth (redirect URI must match the Chaster app exactly).";
      els.chasterWearers.textContent = "";
      if (loginBtn) loginBtn.classList.remove("hidden");
      return;
    }
    const user = data.profile?.username || data.profile_error || "?";
    const kh = data.domme_username || data.lock?.keyholder_username || "";
    const wearer = data.sub_username || data.lock?.wearer_username || "";
    if (data.profile_error) {
      els.chasterStatus.textContent = `Token set but profile failed: ${data.profile_error}`;
    } else {
      els.chasterStatus.textContent =
        `Linked token: ${user}` +
        (kh ? ` | Domme/keyholder: ${kh}` : "") +
        (wearer ? ` | Sub/wearer: ${wearer}` : "");
    }
    if (loginBtn) loginBtn.classList.add("hidden");
    // Pull Domme name from Chaster keyholder into the name box
    if (kh && els.dommeName && !els.dommeName.value.trim()) {
      els.dommeName.value = kh;
    }
    if (wearer && els.subName && !els.subName.value.trim()) {
      els.subName.value = wearer;
    }
    const w = await fetch("/api/chaster/wearers?role=domme", {
      headers: { "X-Role-Pin": state.pin },
    });
    const wearers = await w.json();
    if (!w.ok) {
      els.chasterWearers.textContent = wearers.detail || "Could not list wearers";
      return;
    }
    const fmtRem = (sec) => {
      if (sec == null) return "?";
      const s = Math.max(0, Number(sec));
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      return h ? `${h}h ${m}m` : `${m}m`;
    };
    const lines = (wearers.locks || []).map((l) => {
      const left =
        l.remaining_seconds == null
          ? "?"
          : l.remaining_seconds < 0
            ? "ended"
            : fmtRem(l.remaining_seconds);
      return `${l.username || "?"} | ${l.status} | left=${left} | frozen=${l.is_frozen} | id=${l.lock_id}`;
    });
    els.chasterWearers.textContent = lines.join("\n") || "No locks found on this token.";
  } catch (err) {
    els.chasterStatus.textContent = `Chaster error: ${err.message || err}`;
  }
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
  if (!state.role || !state.pin) return;
  try {
    await fetch("/api/typing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: state.role,
        room: state.room,
        pin: state.pin,
        label: state.role === "domme" ? "Keyholder" : "Lockee",
        active: !!active,
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

async function loadHistory({ speakNewestBot = false, forceScroll = false } = {}) {
  const res = await fetch(`/api/history/${state.room}?role=${state.role}`, {
    headers: { "X-Role-Pin": state.pin },
  });
  if (!res.ok) return;
  const data = await res.json();
  renderTyping(data.typing || []);
  const fp = messageFingerprint(data.messages || []);
  if (fp === state.lastFingerprint && !forceScroll) return;
  const grew = (data.messages || []).length > state.lastCount;
  renderMessages(data.messages || [], {
    // Only speak when something new actually arrived (avoids poll re-render loop)
    speakNewestBot: speakNewestBot && grew,
    forceScroll,
  });
}

async function loadScene() {
  if (state.role !== "domme") return;
  const res = await fetch(`/api/scene?role=domme`, {
    headers: { "X-Role-Pin": state.pin },
  });
  if (!res.ok) return;
  const data = await res.json();
  els.directives.value = data.secret_directives || "";
  kitState.selectedKinks = new Set(data.session_kinks || []);
  kitState.selectedToys = new Set(data.session_toys || []);
  renderKitChips();
}

async function loadMemory() {
  if (state.role !== "domme") return;
  const res = await fetch(`/api/memory?role=domme`, {
    headers: { "X-Role-Pin": state.pin },
  });
  if (!res.ok) return;
  const data = await res.json();
  els.dommeName.value = data.domme_name || "";
  els.dommeTitle.value = data.domme_title || "Mistress";
  els.botName.value = data.bot_name || "Keyholder";
  els.subName.value = data.sub_name || "";
  fillHerTaste(data);
  const bits = [];
  if (data.timeline?.length) bits.push("Recent: " + data.timeline.slice(-3).join(" · "));
  if (data.chastity && Object.keys(data.chastity).length) {
    bits.push("Chastity: " + JSON.stringify(data.chastity));
  }
  els.memoryPreview.textContent = bits.join(" | ") || "Memory will grow as you chat.";
}

async function loadControls() {
  if (state.role !== "domme" || !els.autoPunishEnabled) return;
  const res = await fetch(`/api/controls?role=domme`, {
    headers: { "X-Role-Pin": state.pin },
  });
  if (!res.ok) return;
  const c = await res.json();
  const flagOn = (key) => c[key] !== false;
  if (els.botAllowAddTime) els.botAllowAddTime.checked = flagOn("bot_allow_add_time");
  if (els.botAllowRemoveTime) els.botAllowRemoveTime.checked = flagOn("bot_allow_remove_time");
  if (els.botAllowFreeze) els.botAllowFreeze.checked = flagOn("bot_allow_freeze");
  if (els.botAllowHideTimer) els.botAllowHideTimer.checked = flagOn("bot_allow_hide_timer");
  if (els.botAllowPillory) els.botAllowPillory.checked = flagOn("bot_allow_pillory");
  els.autoPunishEnabled.checked = !!c.auto_punish_enabled;
  els.autoPunishSeconds.value = c.auto_punish_seconds ?? 600;
  els.autopilotEnabled.checked = !!c.autopilot_enabled;
  els.windowStart.value = c.autopilot_window_start || "18:00";
  els.windowEnd.value = c.autopilot_window_end || "23:00";
  els.autopilotTz.value = c.autopilot_timezone || "Europe/London";
  els.autopilotMin.value = c.autopilot_min_minutes ?? 45;
  els.autopilotMax.value = c.autopilot_max_minutes ?? 120;
  els.autopilotChaster.checked = !!c.autopilot_allow_chaster;
  els.autopilotPunishSeconds.value = c.autopilot_punish_seconds ?? 600;
  const PERSONAS = ["friend", "domme", "bull", "male_dom"];
  const SEXES = ["female", "male", "other"];
  const VOICES = ["cruel", "elegant", "playful", "warm", "soft", "humiliatrix", "custom"];
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
  if (c.voice_catalog && c.voice_catalog.tone) {
    Object.assign(TONE, c.voice_catalog.tone);
    Object.assign(INTENSITY, c.voice_catalog.intensity || {});
  }
  if (els.botPersona) {
    const p = String(c.bot_persona || "friend").toLowerCase();
    els.botPersona.value = PERSONAS.includes(p) ? p : "friend";
  }
  if (els.botSex) {
    const s = String(c.bot_sex || "female").toLowerCase();
    els.botSex.value = SEXES.includes(s) ? s : "female";
    syncSexPicks(els.botSex.value);
  }
  if (els.botVoice) {
    const v = String(c.bot_voice || "cruel").toLowerCase();
    els.botVoice.value = VOICES.includes(v) ? v : "cruel";
  }
  if (els.botVoiceBlurb) {
    els.botVoiceBlurb.value = c.bot_voice_blurb || TONE[els.botVoice?.value] || "";
  }
  if (els.botIntensity) {
    const i = String(c.bot_intensity || "firm").toLowerCase();
    els.botIntensity.value = ["tease", "firm", "strict", "custom"].includes(i) ? i : "firm";
  }
  if (els.botIntensityBlurb) {
    els.botIntensityBlurb.value = c.bot_intensity_blurb || INTENSITY[els.botIntensity?.value] || "";
  }
  if (els.botVoiceSample) {
    els.botVoiceSample.value = c.bot_voice_sample || "";
    els.botVoiceSample.dataset.custom = c.bot_voice_sample ? "1" : "";
  }
  if (els.botQuirks) els.botQuirks.value = c.bot_quirks || "";
  if (els.botBio) els.botBio.value = c.bot_bio || "";
  if (els.botGreeting) els.botGreeting.value = c.bot_greeting || "";
  const win = c.in_window ? "inside window now" : "outside window now";
  els.controlsStatus.textContent = `Saved · autopilot ${c.autopilot_enabled ? "on" : "off"} · ${win}`;
}

function renderKitChips() {
  if (!els.kitChips) return;
  els.kitChips.innerHTML = "";
  const kinks = [...kitState.selectedKinks];
  const toys = [...kitState.selectedToys];
  if (!kinks.length && !toys.length) {
    const empty = document.createElement("span");
    empty.className = "kit-empty";
    empty.textContent = "Nothing selected yet";
    els.kitChips.appendChild(empty);
  } else {
    for (const name of kinks) {
      const chip = document.createElement("span");
      chip.className = "kit-chip";
      chip.textContent = name;
      els.kitChips.appendChild(chip);
    }
    for (const name of toys) {
      const chip = document.createElement("span");
      chip.className = "kit-chip toy";
      chip.textContent = name;
      els.kitChips.appendChild(chip);
    }
  }
  if (els.kitStatus) {
    const bits = [];
    if (kinks.length) bits.push(`${kinks.length} kink${kinks.length === 1 ? "" : "s"}`);
    if (toys.length) bits.push(`${toys.length} toy${toys.length === 1 ? "" : "s"}`);
    els.kitStatus.textContent = bits.length
      ? `She will incorporate ${bits.join(" and ")}.`
      : "Open the picker to choose what goes into this session.";
  }
}

function kitMatchesFilter(name, filter) {
  if (!filter) return true;
  return String(name || "").toLowerCase().includes(filter);
}

function renderKitLists() {
  if (!els.kitKinkList || !els.kitToyList) return;
  const filter = (els.kitFilter?.value || "").trim().toLowerCase();
  els.kitKinkList.innerHTML = "";
  els.kitToyList.innerHTML = "";

  const kinks = kitState.kinks.filter((k) => kitMatchesFilter(k.name, filter));
  const toys = kitState.toys.filter((t) => kitMatchesFilter(t.name, filter));

  if (!kinks.length) {
    const p = document.createElement("p");
    p.className = "meta";
    p.textContent = "No matching kinks.";
    els.kitKinkList.appendChild(p);
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
    els.kitKinkList.appendChild(label);
  }

  if (!toys.length) {
    const p = document.createElement("p");
    p.className = "meta";
    p.textContent = "No matching toys.";
    els.kitToyList.appendChild(p);
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
    els.kitToyList.appendChild(label);
  }
}

async function loadKinkCatalog() {
  if (state.role !== "domme") return;
  if (els.kitModalStatus) els.kitModalStatus.textContent = "Loading his profile…";
  const res = await fetch("/api/kink-catalog?role=domme", {
    headers: { "X-Role-Pin": state.pin },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
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
  if (els.kitModalHelp) {
    els.kitModalHelp.textContent = `${src} Tick what you want incorporated this session or week.`;
  }
  if (els.kitModalStatus) {
    els.kitModalStatus.textContent = `${kitState.kinks.length} kinks · ${kitState.toys.length} toys`;
  }
  renderKitLists();
  renderKitChips();
}

function openKitModal() {
  if (!els.kitModal) return;
  els.kitModal.classList.remove("hidden");
  if (els.kitFilter) els.kitFilter.value = "";
  loadKinkCatalog().catch((err) => {
    if (els.kitModalStatus) els.kitModalStatus.textContent = String(err.message || err);
  });
}

function closeKitModal() {
  if (!els.kitModal) return;
  els.kitModal.classList.add("hidden");
}

async function saveSessionKit() {
  const res = await fetch("/api/scene", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role: "domme",
      pin: state.pin,
      session_kinks: [...kitState.selectedKinks],
      session_toys: [...kitState.selectedToys],
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || res.statusText);
  kitState.selectedKinks = new Set(data.session_kinks || []);
  kitState.selectedToys = new Set(data.session_toys || []);
  renderKitChips();
  return data;
}

async function askWeekPlan() {
  if (state.role !== "domme") return;
  try {
    await saveSessionKit();
  } catch (err) {
    setStatus(`Could not save kit: ${err.message || err}`);
    return;
  }
  if (state.room !== "private") {
    state.room = "private";
    state.lastCount = -1;
    state.lastFingerprint = "";
    state.stickToBottom = true;
    state.pendingNew = 0;
    updateRoomChrome();
    await loadHistory({ forceScroll: true });
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
  closeKitModal();
  await sendMessage(prompt);
}

async function ensureRoom(room) {
  if (state.room === room) return;
  state.room = room;
  state.lastCount = -1;
  state.lastFingerprint = "";
  state.stickToBottom = true;
  state.pendingNew = 0;
  updateRoomChrome();
  await loadHistory({ forceScroll: true });
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
  if (kind === "interview" || kind === "video") {
    await ensureRoom("group");
  }
  await sendMessage(text);
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    if (state.room === "group") {
      loadHistory({
        speakNewestBot: !!(els.speakReplies && els.speakReplies.checked),
      }).catch(() => {});
    }
  }, 2000);
}

async function sendMessage(message) {
  const text = (message || "").trim();
  if (!text || state.sending) return;
  state.sending = true;
  els.input.value = "";
  els.sendBtn.disabled = true;
  setStatus("Thinking…");
  if (state.typingTimer) clearTimeout(state.typingTimer);
  pingTyping(false);
  Voice.stopListening();

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        role: state.role,
        room: state.room,
        pin: state.pin,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    state.lastCount = -1;
    state.lastFingerprint = "";
    state.stickToBottom = true;
    await loadHistory({ speakNewestBot: false, forceScroll: true });
    if (data.reply && els.speakReplies?.checked) {
      state.lastSpokenBotKey = `direct:${data.reply}`;
      await speakBot(data.reply);
    }
    if (data.group_posts && data.group_posts.length) {
      setStatus(`Posted ${data.group_posts.length} message(s) to group.`);
      if (state.room === "private") {
        state.room = "group";
        updateRoomChrome();
        state.lastCount = -1;
        await loadHistory({ speakNewestBot: false, forceScroll: true });
      }
      if (els.speakReplies.checked) {
        for (const post of data.group_posts) {
          await Voice.speak(`To the group: ${post}`);
        }
      }
    } else if (!els.handsFree.checked) {
      setStatus("");
    }
  } catch (err) {
    setStatus(`Error: ${err.message || err}`);
  } finally {
    state.sending = false;
    els.sendBtn.disabled = false;
    if (!els.handsFree.checked) els.input.focus();
  }
}

async function enterAs(role) {
  state.role = role;
  state.pin = els.pin.value.trim();
  els.gateStatus.textContent = "Checking…";

  const res = await fetch("/api/auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, pin: state.pin }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    els.gateStatus.textContent = err.detail || "Auth failed";
    return;
  }

  state.room = role === "domme" ? "private" : "group";
  els.roleLabel.textContent = role === "domme" ? "Domme" : "Submissive";
  els.gate.classList.add("hidden");
  els.app.classList.remove("hidden");
  updateRoomChrome();
  state.lastCount = -1;
  state.lastFingerprint = "";
  state.stickToBottom = true;
  state.pendingNew = 0;
  await loadScene();
  await loadMemory();
  await loadControls();
  await loadChaster();
  await loadHistory({ forceScroll: true });
  startPolling();

  if (!support.stt) {
    setStatus("Mic speech-to-text needs Chrome/Edge. TTS may still work.");
  } else {
    setStatus("Voice ready — hold mic or enable hands-free.");
  }
  els.input.focus();
}

Voice.setHandlers({
  result: (text, { final }) => {
    els.input.value = text;
    if (final) {
      setStatus("");
      sendMessage(text);
    } else {
      setStatus("Hearing…");
    }
  },
  listeningChange: (on) => {
    els.micBtn.classList.toggle("hot", on);
    els.micTap.classList.toggle("hot", on);
    if (on) setStatus("Listening…");
  },
});

function bindHold(btn) {
  const start = (e) => {
    e.preventDefault();
    if (!support.stt) {
      setStatus("Speech recognition not supported in this browser.");
      return;
    }
    Voice.stopSpeaking();
    Voice.startListening({ loop: false });
  };
  const end = (e) => {
    e.preventDefault();
    Voice.stopListening();
  };
  btn.addEventListener("mousedown", start);
  btn.addEventListener("mouseup", end);
  btn.addEventListener("mouseleave", end);
  btn.addEventListener("touchstart", start, { passive: false });
  btn.addEventListener("touchend", end);
}

bindHold(els.micBtn);
els.micTap.addEventListener("click", () => {
  if (!support.stt) {
    setStatus("Speech recognition not supported in this browser.");
    return;
  }
  if (Voice.isListening()) {
    Voice.stopListening();
  } else {
    Voice.stopSpeaking();
    Voice.startListening({ loop: false });
  }
});

els.handsFree.addEventListener("change", () => {
  if (els.handsFree.checked) {
    if (!support.stt) {
      els.handsFree.checked = false;
      setStatus("Hands-free needs Chrome/Edge mic support.");
      return;
    }
    Voice.startListening({ loop: true });
    setStatus("Hands-free on — just speak.");
  } else {
    Voice.stopListening();
    setStatus("Hands-free off.");
  }
});

els.stopAudio.addEventListener("click", () => {
  Voice.stopSpeaking();
  Voice.stopListening();
  EdgeCoach.stop();
  els.handsFree.checked = false;
  setStatus("Audio stopped.");
});

EdgeCoach.setHandler(({ running, line }) => {
  els.edgeStatus.textContent = running ? `Coach: ${line}` : line;
});

els.edgeStart.addEventListener("click", () => {
  if (!support.tts) {
    setStatus("Text-to-speech not available in this browser.");
    return;
  }
  Voice.stopListening();
  EdgeCoach.run();
});

els.edgeStop.addEventListener("click", () => {
  EdgeCoach.stop();
  Voice.stopSpeaking();
});

document.querySelectorAll("[data-role]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const role = btn.dataset.role;
    if (pinsRequired[role]) {
      els.pinField.classList.remove("hidden");
      if (!els.pin.value.trim()) {
        els.gateStatus.textContent = `Enter the ${role} PIN, then click again.`;
        return;
      }
    }
    enterAs(role).catch((e) => {
      els.gateStatus.textContent = String(e);
    });
  });
});

els.roomTabs.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-room]");
  if (!btn) return;
  const room = btn.dataset.room;
  if (state.role === "sub" && room === "private") return;
  state.room = room;
  state.lastCount = -1;
  state.lastFingerprint = "";
  state.stickToBottom = true;
  state.pendingNew = 0;
  updateRoomChrome();
  await loadHistory({ forceScroll: true });
});

els.saveScene.addEventListener("click", async () => {
  setStatus("Saving…");
  const sceneRes = await fetch("/api/scene", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role: "domme",
      pin: state.pin,
      secret_directives: els.directives.value,
    }),
  });
  const memRes = await fetch("/api/memory", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      role: "domme",
      pin: state.pin,
      domme_name: els.dommeName.value.trim(),
      domme_title: els.dommeTitle.value.trim() || "Mistress",
      bot_name: els.botName.value.trim() || "Keyholder",
      sub_name: els.subName.value.trim(),
      her_turn_ons: linesListFrom(document.getElementById("herTurnOns")),
      her_fantasies: linesListFrom(document.getElementById("herFantasies")),
    }),
  });
  if (sceneRes.ok && memRes.ok) {
    await loadMemory();
    setStatus("Plan + names saved. She'll remember.");
  } else {
    setStatus("Save failed.");
  }
});

if (els.openKit) {
  els.openKit.addEventListener("click", () => openKitModal());
}
if (els.closeKit) {
  els.closeKit.addEventListener("click", () => closeKitModal());
}
if (els.kitModal) {
  els.kitModal.addEventListener("click", (e) => {
    if (e.target === els.kitModal) closeKitModal();
  });
}
if (els.kitFilter) {
  els.kitFilter.addEventListener("input", () => renderKitLists());
}
if (els.kitSelectLoves) {
  els.kitSelectLoves.addEventListener("click", () => {
    for (const kink of kitState.kinks) {
      if (kink.rating === "love") kitState.selectedKinks.add(kink.name);
    }
    renderKitLists();
  });
}
if (els.kitClear) {
  els.kitClear.addEventListener("click", () => {
    kitState.selectedKinks.clear();
    kitState.selectedToys.clear();
    renderKitLists();
  });
}
if (els.kitRefresh) {
  els.kitRefresh.addEventListener("click", () => {
    loadKinkCatalog().catch((err) => {
      if (els.kitModalStatus) els.kitModalStatus.textContent = String(err.message || err);
    });
  });
}
if (els.saveKit) {
  els.saveKit.addEventListener("click", async () => {
    if (els.kitModalStatus) els.kitModalStatus.textContent = "Saving…";
    try {
      await saveSessionKit();
      if (els.kitModalStatus) els.kitModalStatus.textContent = "Saved. She will use this kit.";
      setStatus("Session kit saved.");
    } catch (err) {
      if (els.kitModalStatus) els.kitModalStatus.textContent = String(err.message || err);
    }
  });
}
if (els.planWeek) {
  els.planWeek.addEventListener("click", () => {
    askWeekPlan().catch((err) => setStatus(String(err.message || err)));
  });
}
if (els.planWeekModal) {
  els.planWeekModal.addEventListener("click", () => {
    askWeekPlan().catch((err) => setStatus(String(err.message || err)));
  });
}
if (els.grillHim) {
  els.grillHim.addEventListener("click", () => {
    askPlay("interview").catch((err) => setStatus(String(err.message || err)));
  });
}
if (els.suggestVideo) {
  els.suggestVideo.addEventListener("click", () => {
    askPlay("video").catch((err) => setStatus(String(err.message || err)));
  });
}
if (els.makeGame) {
  els.makeGame.addEventListener("click", () => {
    askPlay("game").catch((err) => setStatus(String(err.message || err)));
  });
}
const orgasmPicks = document.getElementById("orgasmPicks");
if (orgasmPicks) {
  orgasmPicks.addEventListener("click", (e) => {
    const btn = e.target.closest(".orgasm-pick");
    if (!btn) return;
    orgasmPicks.querySelectorAll(".orgasm-pick").forEach((b) => {
      b.classList.toggle("active", b === btn);
    });
  });
}
const orgasmTellHim = document.getElementById("orgasmTellHim");
const orgasmPrivate = document.getElementById("orgasmPrivate");
const learnHerBtn = document.getElementById("learnHerBtn");
if (orgasmTellHim) {
  orgasmTellHim.addEventListener("click", () => {
    applyOrgasm("group").catch((err) => setStatus(String(err.message || err)));
  });
}
if (orgasmPrivate) {
  orgasmPrivate.addEventListener("click", () => {
    applyOrgasm("private").catch((err) => setStatus(String(err.message || err)));
  });
}
if (learnHerBtn) {
  learnHerBtn.addEventListener("click", () => {
    learnHer().catch((err) => setStatus(String(err.message || err)));
  });
}
if (els.botVoice && els.botVoiceBlurb) {
  els.botVoice.addEventListener("change", () => {
    els.botVoiceBlurb.value = {
      cruel: "No-nonsense. Dry, precise, a little mean. Enjoy his wait. Do not soothe him.",
      elegant: "Well-mannered, commanding, dignified. Quiet authority. Never crude for its own sake.",
      playful: "Frisky and mischievous. Short dares. Laugh at him. Not a lecture.",
      warm: "Fond and firmly in control. Tease with affection. Still deny. Never a therapist.",
      soft: "Silky, gentle authority. Soft-spoken. The cage is still the point.",
      humiliatrix: "Degrading and specific. The cage is the joke. Never kind for free.",
      custom: "Your custom tone. Write exactly how this bot should talk.",
    }[els.botVoice.value] || "";
  });
  els.botVoiceBlurb.addEventListener("input", () => {
    if (els.botVoice.value !== "custom") els.botVoice.value = "custom";
  });
}
if (els.botIntensity && els.botIntensityBlurb) {
  els.botIntensity.addEventListener("change", () => {
    els.botIntensityBlurb.value = {
      tease: "Light pressure. Chat first. Lock changes are a spice, not every turn.",
      firm: "Tease and command in the same breath. Default keyholder energy.",
      strict: "Short orders. Less chat. Use the lock when he pushes. No essays.",
      custom: "Your custom intensity. How hard this bot pushes each turn.",
    }[els.botIntensity.value] || "";
  });
  els.botIntensityBlurb.addEventListener("input", () => {
    if (els.botIntensity.value !== "custom") els.botIntensity.value = "custom";
  });
}
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
  sexPicks.addEventListener("click", async (e) => {
    const btn = e.target.closest(".sex-pick");
    if (!btn) return;
    els.botSex.value = btn.dataset.sex || "female";
    syncSexPicks(els.botSex.value);
    if (els.botSex.value === "male" && els.botPersona) {
      els.botPersona.value = "bull";
    }
    if (!state.pin || state.role !== "domme") return;
    const res = await fetch("/api/controls", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: "domme",
        pin: state.pin,
        bot_sex: els.botSex.value,
        ...(els.botSex.value === "male" ? { bot_persona: "bull" } : {}),
      }),
    });
    if (els.personaStatus) {
      els.personaStatus.textContent = res.ok
        ? els.botSex.value === "male"
          ? "Bot is the bull. Saved."
          : `Bot sex: ${els.botSex.value}. Saved.`
        : "Could not save bot sex.";
    }
  });
}
if (els.savePersona) {
  els.savePersona.addEventListener("click", async () => {
    if (els.personaStatus) els.personaStatus.textContent = "Saving…";
    const res = await fetch("/api/controls", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: "domme",
        pin: state.pin,
        bot_persona: els.botPersona ? els.botPersona.value : "friend",
        bot_sex: els.botSex ? els.botSex.value : "female",
        bot_voice: els.botVoice ? els.botVoice.value : "cruel",
        bot_voice_sample: els.botVoiceSample ? els.botVoiceSample.value.trim().slice(0, 800) : "",
        bot_voice_blurb: els.botVoiceBlurb ? els.botVoiceBlurb.value.trim().slice(0, 800) : "",
        bot_intensity: els.botIntensity ? els.botIntensity.value : "firm",
        bot_intensity_blurb: els.botIntensityBlurb ? els.botIntensityBlurb.value.trim().slice(0, 800) : "",
        bot_quirks: els.botQuirks ? els.botQuirks.value.trim().slice(0, 800) : "",
        bot_bio: els.botBio ? els.botBio.value.trim().slice(0, 1200) : "",
        bot_greeting: els.botGreeting ? els.botGreeting.value.trim().slice(0, 400) : "",
      }),
    });
    if (res.ok) {
      await loadControls();
      if (els.personaStatus) els.personaStatus.textContent = "Personality saved.";
    } else {
      const err = await res.json().catch(() => ({}));
      if (els.personaStatus) els.personaStatus.textContent = err.detail || "Save failed.";
    }
  });
}
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && els.kitModal && !els.kitModal.classList.contains("hidden")) {
    closeKitModal();
  }
});

if (els.saveControls) {
  els.saveControls.addEventListener("click", async () => {
    setStatus("Saving timings…");
    const res = await fetch("/api/controls", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: "domme",
        pin: state.pin,
        bot_allow_add_time: els.botAllowAddTime ? els.botAllowAddTime.checked : true,
        bot_allow_remove_time: els.botAllowRemoveTime ? els.botAllowRemoveTime.checked : true,
        bot_allow_freeze: els.botAllowFreeze ? els.botAllowFreeze.checked : true,
        bot_allow_hide_timer: els.botAllowHideTimer ? els.botAllowHideTimer.checked : true,
        bot_allow_pillory: els.botAllowPillory ? els.botAllowPillory.checked : true,
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
        bot_persona: els.botPersona ? els.botPersona.value : "friend",
        bot_sex: els.botSex ? els.botSex.value : "female",
        bot_voice: els.botVoice ? els.botVoice.value : "cruel",
        bot_intensity: els.botIntensity ? els.botIntensity.value : "firm",
      }),
    });
    if (res.ok) {
      await loadControls();
      setStatus("Timings saved (live).");
    } else {
      const err = await res.json().catch(() => ({}));
      setStatus(err.detail || "Timings save failed.");
    }
  });
}

els.resetChat.addEventListener("click", async () => {
  if (state.role !== "domme") {
    setStatus("Only the Domme can reset rooms.");
    return;
  }
  await fetch("/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ room: state.room, role: state.role, pin: state.pin }),
  });
  state.lastCount = -1;
  state.lastFingerprint = "";
  state.stickToBottom = true;
  state.pendingNew = 0;
  await loadHistory({ forceScroll: true });
  setStatus("Room cleared.");
});

els.switchRole.addEventListener("click", () => {
  if (state.pollTimer) clearInterval(state.pollTimer);
  Voice.stopListening();
  Voice.stopSpeaking();
  EdgeCoach.stop();
  state.role = null;
  els.app.classList.add("hidden");
  els.gate.classList.remove("hidden");
  els.messages.innerHTML = "";
});

els.form.addEventListener("submit", async (e) => {
  e.preventDefault();
  await sendMessage(els.input.value);
});

els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.form.requestSubmit();
  }
});

els.input.addEventListener("input", () => {
  if ((els.input.value || "").trim()) scheduleTypingPing();
});

els.chasterRefresh.addEventListener("click", () => loadChaster());

if (els.imageGen) els.imageGen.addEventListener("click", async () => {
  if (state.role !== "domme") return;
  const prompt = els.imagePrompt.value.trim();
  if (!prompt) {
    els.imageStatus.textContent = "Enter a prompt first.";
    return;
  }
  els.imageGen.disabled = true;
  els.imageStatus.textContent = "Generating… this can take a bit.";
  try {
    const res = await fetch("/api/image", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        role: "domme",
        pin: state.pin,
        room: state.room,
        post_to_room: els.imageToGroup.checked,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText);
    els.imageStatus.textContent = "Image ready.";
    state.lastCount = -1;
    state.lastFingerprint = "";
    state.stickToBottom = true;
    await loadHistory({ speakNewestBot: false, forceScroll: true });
  } catch (err) {
    els.imageStatus.textContent = `Failed: ${err.message || err}`;
  } finally {
    els.imageGen.disabled = false;
  }
});

fetch("/api/meta")
  .then((r) => r.json())
  .then((meta) => {
    pinsRequired = meta.pins_required || pinsRequired;
    els.modelMeta.textContent = meta.model || "";
    if (els.imageStatus) {
      els.imageStatus.textContent = "Image generation is parked.";
    }
    if (pinsRequired.domme || pinsRequired.sub) {
      els.pinField.classList.remove("hidden");
    }
  })
  .catch(() => {});
