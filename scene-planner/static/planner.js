const $ = (id) => document.getElementById(id);
const state = { messages: [], lastScene: "" };

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

function addMessage(role, content) {
  state.messages.push({ role, content });
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

function resetChat(opener) {
  state.messages = [];
  state.lastScene = "";
  $("thread").innerHTML = "";
  addMessage("assistant", opener);
}

async function send() {
  const text = $("prompt").value.trim();
  if (!text) return;
  $("prompt").value = "";
  addMessage("user", text);
  $("formStatus").textContent = "Writing the scene…";
  $("sendBtn").disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ adults_confirmed: true, messages: state.messages }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || "Could not plan");
    const reply = data.reply || "";
    addMessage("assistant", reply);
    if (/theme:|scenario:/i.test(reply)) state.lastScene = reply;
    $("formStatus").textContent = data.detail || "";
  } catch (err) {
    $("formStatus").textContent = err.message || String(err);
  } finally {
    $("sendBtn").disabled = false;
    $("prompt").focus();
  }
}

async function boot() {
  const meta = await fetch("/api/meta").then((r) => r.json());
  const opener = meta.opener || "List your toys and hard limits.";
  $("adultBtn").addEventListener("click", () => {
    sessionStorage.setItem("planner18", "1");
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    if (!state.messages.length) resetChat(opener);
    $("prompt").focus();
  });
  if (sessionStorage.getItem("planner18") === "1") {
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
    resetChat(opener);
  }
  if (!meta.llm_configured) {
    $("formStatus").textContent = "No LLM_API_KEY — local composer only until you set the OpenRouter key in .env";
  }
  $("composer").addEventListener("submit", (ev) => {
    ev.preventDefault();
    send();
  });
  $("prompt").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      send();
    }
  });
  $("resetBtn").addEventListener("click", () => resetChat(opener));
  $("copyBtn").addEventListener("click", async () => {
    const text = state.lastScene || [...state.messages].reverse().find((m) => m.role === "assistant")?.content;
    if (!text) return;
    await navigator.clipboard.writeText(text);
    $("formStatus").textContent = "Copied.";
  });
}

boot();
