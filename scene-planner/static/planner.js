const $ = (id) => document.getElementById(id);
const state = { last: null, catalog: null };

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

function renderKinks(kinks, chosen) {
  const box = $("kinkPicks");
  box.innerHTML = "";
  const picked = new Set(chosen || []);
  for (const kink of kinks) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pick" + (picked.has(kink) ? " active" : "");
    btn.textContent = kink;
    btn.addEventListener("click", () => btn.classList.toggle("active"));
    box.appendChild(btn);
  }
}

function selectedKinks() {
  return [...document.querySelectorAll("#kinkPicks .pick.active")].map((b) => b.textContent);
}

function briefFromForm() {
  return {
    adults_confirmed: true,
    duration_minutes: Number($("duration").value || 60),
    intensity: $("intensity").value,
    setting: $("setting").value,
    tone: $("tone").value,
    orgasm: $("orgasm").value,
    experience: $("experience").value,
    kinks: selectedKinks(),
    toys: $("toys").value.trim(),
    limits: $("limits").value.trim(),
    notes: $("notes").value.trim(),
  };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function renderItinerary(data) {
  $("empty").classList.add("hidden");
  $("itinerary").classList.remove("hidden");
  $("itTitle").textContent = data.title || "Itinerary";
  $("itPremise").textContent = data.premise || "";
  $("itMeta").textContent = [
    data.source,
    data.intensity,
    data.setting && String(data.setting).replaceAll("_", " "),
    data.duration_minutes ? `${data.duration_minutes} min` : "",
    data.orgasm ? `orgasm: ${data.orgasm}` : "",
  ].filter(Boolean).join(" · ");
  $("itWarnings").textContent = (data.warnings || []).join(" ");
  $("itKit").textContent = data.equipment?.length ? `Kit: ${data.equipment.join(", ")}` : "";
  const sw = data.safeword || {};
  $("itSafe").replaceChildren(
    el("strong", "", "Safewords: "),
    document.createTextNode(`green ${sw.green || "green"} · yellow ${sw.yellow || "yellow"} · red ${sw.red || "red"}`)
  );
  const list = $("itSteps");
  list.innerHTML = "";
  for (const step of data.steps || []) {
    const item = el("li", "step");
    item.appendChild(el("p", "step-time", `${step.start_min}–${step.end_min} min · ${step.phase || "beat"}`));
    item.appendChild(el("h3", "", step.title || "Beat"));
    if (step.domme) { item.appendChild(el("p", "who", "You")); item.appendChild(el("p", "", step.domme)); }
    if (step.sub) { item.appendChild(el("p", "who", "Him")); item.appendChild(el("p", "", step.sub)); }
    if (step.notes) item.appendChild(el("p", "notes", step.notes));
    list.appendChild(item);
  }
  $("itAfter").replaceChildren(...(data.aftercare || []).map((line) => el("li", "", line)));
  $("itVars").replaceChildren(...(data.variations || []).map((line) => el("li", "", line)));
  $("itVarWrap").classList.toggle("hidden", !(data.variations || []).length);
}

function itineraryText(data) {
  const lines = [data.title, data.premise, "", (data.warnings || []).join(" "), ""];
  for (const step of data.steps || []) {
    lines.push(`${step.start_min}–${step.end_min} min — ${step.title}`, `You: ${step.domme || ""}`, `Him: ${step.sub || ""}`, "");
  }
  lines.push("Aftercare:");
  for (const line of data.aftercare || []) lines.push(`- ${line}`);
  return lines.join("\n");
}

async function generate(payload) {
  $("formStatus").textContent = "Writing the scene…";
  $("planBtn").disabled = true;
  $("surpriseBtn").disabled = true;
  try {
    const res = await fetch("/api/scene", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || "Could not plan");
    state.last = data;
    renderItinerary(data);
    $("formStatus").textContent = data.detail || "";
  } catch (err) {
    $("formStatus").textContent = err.message || String(err);
  } finally {
    $("planBtn").disabled = false;
    $("surpriseBtn").disabled = false;
  }
}

async function boot() {
  $("adultBtn").addEventListener("click", () => {
    sessionStorage.setItem("planner18", "1");
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
  });
  if (sessionStorage.getItem("planner18") === "1") {
    $("gate").classList.add("hidden");
    $("app").classList.remove("hidden");
  }
  const meta = await fetch("/api/meta").then((r) => r.json());
  state.catalog = meta;
  fillSelect($("intensity"), meta.intensities, "extreme");
  fillSelect($("setting"), meta.settings, "in_person");
  fillSelect($("tone"), meta.tones, "cruel");
  fillSelect($("orgasm"), meta.orgasm_policies, "denied");
  renderKinks(meta.kinks, ["chastity", "orgasm denial", "humiliation", "bondage"]);
  if (!meta.llm_configured) {
    $("formStatus").textContent = "No LLM_API_KEY — local composer only until you set the OpenRouter key in .env";
  }
  $("brief").addEventListener("submit", (ev) => {
    ev.preventDefault();
    generate(briefFromForm());
  });
  $("surpriseBtn").addEventListener("click", () => generate({ ...briefFromForm(), surprise: true }));
  $("copyBtn").addEventListener("click", async () => {
    if (!state.last) return;
    await navigator.clipboard.writeText(itineraryText(state.last));
    $("formStatus").textContent = "Copied.";
  });
  $("printBtn").addEventListener("click", () => window.print());
}

boot();
