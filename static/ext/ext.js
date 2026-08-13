(function () {
  const els = {
    gate: document.getElementById("gate"),
    gateMsg: document.getElementById("gateMsg"),
    app: document.getElementById("app"),
    roleLabel: document.getElementById("roleLabel"),
    heading: document.getElementById("heading"),
    sessionMeta: document.getElementById("sessionMeta"),
    messages: document.getElementById("messages"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("input"),
    sendBtn: document.getElementById("sendBtn"),
    status: document.getElementById("status"),
  };

  const state = {
    mainToken: "",
    role: null,
    lastCount: 0,
    stickToBottom: true,
    pollTimer: null,
  };

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
    if (!res.ok) throw new Error(data.detail || "Session rejected");
    const s = data.session || {};
    state.role = s.app_role;
    els.roleLabel.textContent =
      s.role === "keyholder" ? "Keyholder" : "Lockee";
    els.heading.textContent = data.bot_name || "Chat";
    els.sessionMeta.textContent = [
      s.wearer_username && `Lockee: ${s.wearer_username}`,
      s.keyholder_username && `KH: ${s.keyholder_username}`,
    ]
      .filter(Boolean)
      .join(" · ");
    els.gate.classList.add("hidden");
    els.app.classList.remove("hidden");
  }

  async function loadHistory() {
    const res = await fetch("/api/ext/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ main_token: state.mainToken }),
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
        body: JSON.stringify({ main_token: state.mainToken, message }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || res.statusText);
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
