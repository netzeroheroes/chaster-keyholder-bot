const $ = (id) => document.getElementById(id);
const KIT_KEY = "plannerKit";
const state = { catalog: null, kit: null, session: null, messages: [], lastScene: "" };

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderMarkdown(raw) {
  const escaped = escapeHtml(raw || "").replaceAll("\r\n", "\n");
  const blocks = escaped.split(/\n{2,}/);
  return blocks.map((block) => {
    const lines = block.split("\n");
    if (lines.every((line) => /^\d+\.\s+/.test(line))) {
      const items = lines.map((line) => `<li>${inline(line.replace(/^\d+\.\s+/, ""))}</li>`).join("");
      return `<ol>${items}</ol>`;
    }
    if (lines.every((line) => /^[-*]\s+/.test(line))) {
      const items = lines.map((line) => `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`).join("");
      return `<ul>${items}</ul>`;
    }
    return `<p>${inline(lines.join("<br>"))}</p>`;
  }).join("");
}

function inline(text) {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
}

function show(id) {
  ["gate", "kit", "session", "app"].forEach((name) => $(name).classList.toggle("hidden", name !== id));
}

function renderPicks(boxId, values, chosen, { single = false } = {}) {
  const box = $(boxId);
  box.innerHTML = "";
  const picked = new Set(chosen || []);
  for (const value of values) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pick" + (picked.has(value) ? " active" : "");
    btn.textContent = value;
    btn.addEventListener("click", () => {
      if (single) {
        box.querySelectorAll(".pick").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
      } else {
        btn.classList.toggle("active");
      }
    });
    box.appendChild(btn);
  }
}

function selectedPicks(boxId) {
  return [...document.querySelectorAll(`#${boxId} .pick.active`)].map((b) => b.textContent);
}

function readKit() {
  return {
    toys: $("kitToys").value.trim(),
    kinks: selectedPicks("kinkPicks"),
    limits: $("kitLimits").value.trim(),
  };
}

function readSession() {
  return {
    duration_minutes: Number($("duration").value || state.catalog.duration.default),
    focus: selectedPicks("focusPicks")[0] || "ownership",
    orgasm: $("orgasm").value,
    notes: $("sessionNotes").value.trim(),
  };
}

function kitLine(kit) {
  const kinks = (kit.kinks || []).join(", ") || "no kinks picked";
  const limits = kit.limits || "no hard limits listed";
  return `Kit: ${kit.toys || "no toys listed"} · ${kinks} · limits: ${limits}`;
}

function fillSelect(el, values, selected) {
  el.innerHTML = "";
  for (const value of values) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value.replaceAll("_", " ");
    if (value === selected) opt.selected = true;
    el.appendChild(opt);
  }
}

function addMessage(role, content, { store = true } = {}) {
  if (store) state.messages.push({ role, content });
  const node = document.createElement("article");
  node.className = `msg ${role === "user" ? "you" : "bot"}`;
  const who = document.createElement("p");
  who.className = "who";
  who.textContent = role === "user" ? "You" : "Scenario Planner";
  const body = document.createElement("div");
  body.className = "body";
  if (role === "user") body.innerHTML = `<p>${escapeHtml(content).replaceAll("\n", "<br>")}</p>`;
  else body.innerHTML = renderMarkdown(content);
  node.append(who, body);
  $("thread").appendChild(node);
  node.scrollIntoView({ block: "end" });
}

async function postChat(userText) {
  if (userText) addMessage("user", userText);
  $("formStatus").textContent = "Writing the scene…";
  $("sendBtn").disabled = true;
  $("writeBtn").disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        adults_confirmed: true,
        kit: state.kit,
        session: state.session,
        messages: state.messages,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || "Could not plan");
    const reply = data.reply || "";
    addMessage("assistant", reply);
    if (/theme:|scenario:|duration:/i.test(reply)) state.lastScene = reply;
    $("formStatus").textContent = data.detail || "";
    $("sessionStatus").textContent = data.detail || "";
  } catch (err) {
    $("formStatus").textContent = err.message || String(err);
    $("sessionStatus").textContent = err.message || String(err);
  } finally {
    $("sendBtn").disabled = false;
    $("writeBtn").disabled = false;
  }
}

function openKit() {
  const kit = state.kit || {};
  $("kitToys").value = kit.toys || "";
  $("kitLimits").value = kit.limits || "";
  renderPicks("kinkPicks", state.catalog.kinks, kit.kinks || ["chastity", "orgasm denial", "humiliation"]);
  show("kit");
}

function openSession() {
  $("kitSummary").textContent = kitLine(state.kit);
  const dur = state.catalog.duration;
  $("duration").min = dur.min;
  $("duration").max = dur.max;
  $("duration").value = state.session?.duration_minutes || dur.default;
  renderPicks("focusPicks", state.catalog.focuses, [state.session?.focus || "ownership"], { single: true });
  fillSelect($("orgasm"), state.catalog.orgasm_policies, state.session?.orgasm || "denied");
  $("sessionNotes").value = state.session?.notes || "";
  show("session");
}

function openChat() {
  $("runSummary").textContent = `${kitLine(state.kit)} · ${state.session.duration_minutes} min · ${state.session.focus} · orgasm ${state.session.orgasm}`;
  show("app");
}

function loadSavedKit() {
  try {
    const raw = localStorage.getItem(KIT_KEY);
    if (!raw) return null;
    const kit = JSON.parse(raw);
    if (!kit || typeof kit !== "object") return null;
    return kit;
  } catch {
    return null;
  }
}

async function boot() {
  const meta = await fetch("/api/meta").then((r) => r.json());
  state.catalog = meta;
  state.kit = loadSavedKit();
  $("adultBtn").addEventListener("click", () => {
    sessionStorage.setItem("planner18", "1");
    if (state.kit?.toys) openSession();
    else openKit();
  });
  if (sessionStorage.getItem("planner18") === "1") {
    if (state.kit?.toys) openSession();
    else openKit();
  }
  $("kitForm").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const kit = readKit();
    if (!kit.toys) {
      $("kitStatus").textContent = "List at least one toy or household stand-in.";
      return;
    }
    state.kit = kit;
    localStorage.setItem(KIT_KEY, JSON.stringify(kit));
    openSession();
  });
  $("editKitBtn").addEventListener("click", openKit);
  $("resetKitBtn").addEventListener("click", openKit);
  $("newSessionBtn").addEventListener("click", () => {
    state.messages = [];
    state.lastScene = "";
    $("thread").innerHTML = "";
    openSession();
  });
  $("sessionForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    state.session = readSession();
    state.messages = [];
    state.lastScene = "";
    $("thread").innerHTML = "";
    openChat();
    const ask = [
      `I want a ${state.session.duration_minutes} minute session.`,
      `Tonight's job: ${state.session.focus}.`,
      `Orgasm: ${state.session.orgasm}.`,
      state.session.notes ? `Notes: ${state.session.notes}` : "",
    ].filter(Boolean).join(" ");
    await postChat(ask);
    $("prompt").focus();
  });
  $("composer").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = $("prompt").value.trim();
    if (!text) return;
    $("prompt").value = "";
    postChat(text);
  });
  $("prompt").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      $("composer").requestSubmit();
    }
  });
  $("copyBtn").addEventListener("click", async () => {
    const text = state.lastScene || [...state.messages].reverse().find((m) => m.role === "assistant")?.content;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    $("formStatus").textContent = "Copied.";
  });
}

boot();
