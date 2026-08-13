(function () {
  const els = {
    gate: document.getElementById("gate"),
    gateMsg: document.getElementById("gateMsg"),
    app: document.getElementById("app"),
    roleLabel: document.getElementById("roleLabel"),
    heading: document.getElementById("heading"),
    sessionMeta: document.getElementById("sessionMeta"),
    roomTabs: document.getElementById("roomTabs"),
    privateTab: document.getElementById("privateTab"),
    roomHint: document.getElementById("roomHint"),
    messages: document.getElementById("messages"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("input"),
    sendBtn: document.getElementById("sendBtn"),
    status: document.getElementById("status"),
  };

  const state = {
    mainToken: "",
    role: null, // app role: domme | sub
    chasterRole: null, // keyholder | wearer
    room: "group",
    lastCount: 0,
    stickToBottom: true,
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
    const grew = messages.length > state.lastCount && state.lastCount >= 0;
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
    if (state.stickToBottom || state.lastCount <= 0 || !grew) {
      els.messages.scrollTop = els.messages.scrollHeight;
      state.stickToBottom = true;
    }
    state.lastCount = messages.length;
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
    } else {
      els.privateTab.classList.add("hidden");
      state.room = "group";
    }
    updateRoomUi();
    els.gate.classList.add("hidden");
    els.app.classList.remove("hidden");
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
    updateRoomUi();
    setStatus("");
    await loadHistory();
  }

  els.roomTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".room-tab");
    if (!btn || btn.classList.contains("hidden")) return;
    switchRoom(btn.dataset.room);
  });

  els.messages.addEventListener("scroll", () => {
    state.stickToBottom = nearBottom();
  });

  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(els.input.value);
  });

  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      els.form.requestSubmit();
    }
  });

  async function boot() {
    state.mainToken = parseHashToken();
    // Local testing: /ext#dev:keyholder or /ext#dev:wearer with EXTENSION_DEV_BYPASS=true
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
      state.pollTimer = setInterval(() => loadHistory().catch(() => {}), 2500);
    } catch (err) {
      els.gateMsg.textContent = String(err.message || err);
    }
  }

  boot();
})();
