// ProcessIQ demo UI — real upload -> async pipeline -> perception overlays -> SOP.
// Talks to the control-plane API on the same origin. Admin headers for single-user demo.
const H = { "X-Tenant": "demo", "X-User": "demo@analyst", "X-Roles": "Admin,Analyst,Reviewer" };
const JSON_H = { ...H, "Content-Type": "application/json" };

let processId = null, jobId = null, sopId = null;
let running = false;   // guards against double-clicking Run (would fire two jobs / two API calls)
let currentSop = null; // last-rendered SOP (source for inline step editing)
let screens = [];          // perception: [{artifact_id, order, elements[], text[]}]
let artifacts = [];        // [{id, order, filename}]
let images = {};           // artifact_id -> HTMLImageElement
let selectedArtifact = null, highlightBbox = null;

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: JSON_H, ...opts });
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(typeof body === "string" ? body : (body.detail || JSON.stringify(body)));
  return body;
}

// ---------- upload ----------
const drop = $("drop"), fileInput = $("file-input");
const OVER = ["bg-violet-50", "border-brand-violet"];
drop.onclick = () => fileInput.click();
drop.ondragover = (e) => { e.preventDefault(); drop.classList.add(...OVER); };
drop.ondragleave = () => drop.classList.remove(...OVER);
drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove(...OVER); addFiles(e.dataTransfer.files); };
fileInput.onchange = () => addFiles(fileInput.files);

async function ensureProcess() {
  if (processId) return;
  const p = await api("/v1/processes", { method: "POST", body: JSON.stringify({ name: $("pname").value || "Untitled Process" }) });
  processId = p.processId;
}

async function addFiles(fileList) {
  const files = [...fileList].filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  try {
    await ensureProcess();
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const r = await fetch(`/v1/processes/${processId}/uploads:file`, { method: "POST", headers: H, body: fd });
      const body = await r.json();
      if (!r.ok) { setStatus("upload-status", `✗ ${f.name}: ${body.detail || r.status}`, "err"); continue; }
      const div = document.createElement("div");
      div.className = "relative w-[70px]";
      const url = URL.createObjectURL(f);
      if (body.deduplicated) {
        div.innerHTML = `<img src="${url}" class="w-[70px] h-[46px] object-cover rounded-md border border-slate-200 opacity-60" />
          <span class="absolute inset-x-0 bottom-0 text-[9px] text-center bg-amber-400 text-slate-900 rounded-b-md">duplicate</span>`;
      } else {
        artifacts.push({ id: body.artifactId, order: body.order, filename: f.name });
        div.innerHTML = `<img src="${url}" class="w-[70px] h-[46px] object-cover rounded-md border border-slate-200" />
          <span class="absolute top-1 left-1 text-[10px] text-white bg-slate-900/70 rounded px-1">${body.order}</span>`;
      }
      $("thumbs").appendChild(div);
    }
    setStatus("upload-status", `${artifacts.length} screenshot(s) registered.`, "ok");
    $("run-btn").disabled = artifacts.length === 0;
  } catch (e) { setStatus("upload-status", "✗ " + e.message, "err"); }
}

// ---------- job ----------
async function runJob() {
  if (running || !processId || !artifacts.length) return;   // ignore extra clicks while a job runs
  running = true;
  $("run-btn").disabled = true;
  setStatus("job-status", "");
  startProgress();
  try {
    const j = await api("/v1/jobs", { method: "POST",
      body: JSON.stringify({ process_id: processId,
        options: { async: true, instruction: $("instruction").value.trim() } }) });
    jobId = j.jobId;
    pollJob();
  } catch (e) { stopProgress(false); setStatus("job-status", "✗ " + e.message, "err"); running = false; $("run-btn").disabled = false; }
}

async function pollJob() {
  try {
    const job = await api(`/v1/jobs/${jobId}`);
    if (job.status === "FAILED") {
      stopProgress(false);
      setStatus("job-status", "✗ " + (job.error ? job.error.detail : "pipeline failed"), "err");
      running = false; $("run-btn").disabled = false; return;
    }
    if (job.status === "COMPLETED" || job.status === "NEEDS_REVIEW") {
      sopId = job.sop_id;
      stopProgress(true);
      setStatus("job-status", job.status === "NEEDS_REVIEW" ? "Done — some steps need review." : "Done.", job.status === "NEEDS_REVIEW" ? "warn" : "ok");
      await Promise.all([loadSop(), loadPerception(), loadTrace()]);
      loadHistory(); loadChat();
      running = false; $("run-btn").disabled = false; return;
    }
    setTimeout(pollJob, 1000);
  } catch (e) { stopProgress(false); setStatus("job-status", "✗ " + e.message, "err"); running = false; $("run-btn").disabled = false; }
}

// ---------- perception viewer ----------
async function loadPerception() {
  const p = await api(`/v1/jobs/${jobId}/perception`);
  screens = p.screens;
  buildViewer();
}

// Build the screenshot strip + canvas from `screens` (used by both live runs and reopened history).
function buildViewer() {
  $("viewer-empty").classList.add("hidden");
  $("viewer-content").classList.remove("hidden");
  const strip = $("strip");
  strip.innerHTML = "";
  images = {};
  for (const s of screens) {
    const img = document.createElement("img");
    img.src = `/v1/processes/${processId}/artifacts/${s.artifact_id}/image`;
    img.onclick = () => selectScreen(s.artifact_id);
    img.dataset.artifact = s.artifact_id;
    strip.appendChild(img);
    images[s.artifact_id] = img;
  }
  if (screens.length) selectScreen(screens[0].artifact_id);
}

function selectScreen(artifactId, bbox = null) {
  selectedArtifact = artifactId; highlightBbox = bbox;
  [...$("strip").children].forEach((el) => el.classList.toggle("sel", el.dataset.artifact === artifactId));
  const img = images[artifactId];
  if (img && !img.complete) img.onload = draw;
  draw();
}

function draw() {
  const canvas = $("canvas"), ctx = canvas.getContext("2d");
  const screen = screens.find((s) => s.artifact_id === selectedArtifact);
  const img = images[selectedArtifact];
  if (!screen || !img || !img.complete || !img.naturalWidth) return;
  canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
  ctx.drawImage(img, 0, 0);
  const W = canvas.width, Hh = canvas.height;
  if (highlightBbox) {
    const [x, y, w, h] = [highlightBbox[0] * W, highlightBbox[1] * Hh, highlightBbox[2] * W, highlightBbox[3] * Hh];
    ctx.strokeStyle = "#F59E0B"; ctx.lineWidth = Math.max(4, W / 320);
    ctx.strokeRect(x, y, w, h);
    // scroll inside the pinned viewer so the highlighted control is centered
    const wrap = $("canvas-scroll");
    requestAnimationFrame(() => {
      const centerY = (highlightBbox[1] + highlightBbox[3] / 2) * canvas.clientHeight;
      wrap.scrollTo({ top: centerY - wrap.clientHeight / 2, behavior: "smooth" });
    });
  }
  const info = $("sel-info"); if (info) info.textContent = `Screen ${screen.order} of ${screens.length}`;
}

// ---------- animated progress (the job has no fine-grained server progress, so we simulate motion) ----------
let progTimer = null;
const PROG_MSGS = [
  "Analyzing your screenshots",
  "Understanding the workflow",
  "Identifying buttons, fields & actions",
  "Writing the step-by-step SOP",
  "Locating the control for each step",
  "Finalizing your SOP",
];
function startProgress() {
  stopProgressTimer();
  let pct = 5, tick = 0, i = 0;
  const bar = $("bar"), stage = $("stage");
  bar.classList.add("working");
  bar.style.width = "5%";
  stage.className = "text-[12px] text-slate-500 mt-2 min-h-[16px] stage-dot";
  stage.textContent = PROG_MSGS[0];
  progTimer = setInterval(() => {
    tick++;
    pct += Math.max(0.5, (93 - pct) * 0.045);   // creep smoothly toward 93%, never hit 100 until done
    if (pct > 93) pct = 93;
    bar.style.width = pct.toFixed(1) + "%";
    if (tick % 6 === 0 && i < PROG_MSGS.length - 1) { i++; stage.textContent = PROG_MSGS[i]; }
  }, 450);
}
function stopProgressTimer() { if (progTimer) { clearInterval(progTimer); progTimer = null; } }
function stopProgress(done) {
  stopProgressTimer();
  const bar = $("bar"), stage = $("stage");
  bar.classList.remove("working");
  bar.style.width = done ? "100%" : "0%";
  stage.className = "text-[12px] text-slate-500 mt-2 min-h-[16px]";
  stage.textContent = done ? "Done ✓" : "";
}

// ---------- SOP ----------
async function loadSop() {
  if (!sopId) return;
  renderSop(await api(`/v1/sops/${sopId}`));
}

function renderSop(sop) {
  currentSop = sop;
  const fb = $("sop-fb"); if (fb) fb.style.display = "inline-flex";
  $("sop-title").textContent = `${sop.title}`;
  $("k-steps").textContent = sop.steps.length;
  $("k-conf").textContent = Math.round(sop.overall_confidence * 100) + "%";
  $("k-state").textContent = sop.state;
  $("steps").innerHTML = sop.steps.map((s) => {
    const flagged = (s.flags || []).length > 0;
    const badge = flagged
      ? `<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 whitespace-nowrap">needs review</span>`
      : `<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">ok</span>`;
    const ref = s.screenshot_ref ? `data-art="${s.screenshot_ref.artifact_id}" data-bbox="${s.screenshot_ref.bbox.join(",")}"` : "";
    return `<div class="step-card" data-no="${s.no}" ${ref} onclick="stepClick(this)">
      <div class="flex justify-between items-center gap-2">
        <b class="text-[13px]">${s.no}. ${esc(s.action)}</b>
        <span class="flex items-center gap-1.5">${badge}
          <button title="Edit step" onclick="event.stopPropagation();editStep(${s.no})" class="text-[12px] text-slate-400 hover:text-brand-violet">✏️</button>
        </span>
      </div>
      <div class="text-[12px] text-slate-500 mt-1 whitespace-pre-line">${esc(s.description)}</div>
      <div class="meter mt-2"><div style="width:${Math.round(s.confidence * 100)}%"></div></div>
      ${flagged ? `<button class="mt-2 text-[12px] font-medium text-brand-violet border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50" onclick="event.stopPropagation();approve(${s.no})">Approve step</button>` : ""}
    </div>`;
  }).join("") +
  `<button onclick="addStep()" class="w-full mt-1 text-[12px] font-medium text-brand-violet border border-dashed border-slate-300 rounded-lg py-2 hover:bg-slate-50">+ Add step</button>`;
  loadVersions();
}

function stepClick(el) {
  if (el.dataset.editing) return;   // don't jump while editing
  [...$("steps").children].forEach((s) => s.classList.remove("sel"));
  el.classList.add("sel");
  const art = el.dataset.art;
  if (art && images[art]) selectScreen(art, el.dataset.bbox.split(",").map(Number));
}

// ---------- step editing (each save creates a new SOP version) ----------
function editStep(no) {
  const step = (currentSop.steps || []).find((s) => s.no === no);
  const card = document.querySelector(`.step-card[data-no="${no}"]`);
  if (!step || !card) return;
  card.dataset.editing = "1";
  card.innerHTML = `
    <input class="field mb-2 step-action" placeholder="Action" />
    <textarea class="field step-desc" rows="4" style="resize:vertical" placeholder="Description"></textarea>
    <div class="flex gap-2 mt-2">
      <button class="btn-grad text-white text-[12px] font-semibold rounded-lg px-3 py-1.5" onclick="saveStep(${no})">Save</button>
      <button class="text-[12px] text-slate-600 border border-slate-200 rounded-lg px-3 py-1.5" onclick="loadSop()">Cancel</button>
      <button class="ml-auto text-[12px] text-red-500 border border-slate-200 rounded-lg px-3 py-1.5" onclick="deleteStep(${no})">Delete</button>
    </div>`;
  card.querySelector(".step-action").value = step.action;
  card.querySelector(".step-desc").value = step.description;
}
async function saveStep(no) {
  const card = document.querySelector(`.step-card[data-no="${no}"]`);
  const action = card.querySelector(".step-action").value;
  const description = card.querySelector(".step-desc").value;
  try {
    await api(`/v1/sops/${sopId}/steps/${no}`, { method: "PATCH", body: JSON.stringify({ action, description }) });
    await loadSop();
    loadFeedback();
    setStatus("job-status", "Step saved — new version created.", "ok");
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}
async function addStep() {
  try {
    await api(`/v1/sops/${sopId}/steps`, { method: "POST", body: JSON.stringify({ action: "New step", description: "Describe the action…" }) });
    await loadSop();
    loadFeedback();
    setStatus("job-status", "Step added — new version created.", "ok");
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}
async function deleteStep(no) {
  try {
    await api(`/v1/sops/${sopId}/steps/${no}`, { method: "DELETE" });
    await loadSop();
    loadFeedback();
    setStatus("job-status", "Step deleted — new version created.", "ok");
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}

// ---------- version history ----------
async function loadVersions() {
  if (!sopId) return;
  try {
    const r = await api(`/v1/sops/${sopId}/versions`);
    const el = $("versions");
    if (!el) return;
    if (!r.versions.length) { el.innerHTML = `<div class="text-[12px] text-slate-400">No versions yet.</div>`; return; }
    el.innerHTML = r.versions.slice().reverse().map((v) => `
      <div class="flex items-center gap-2 text-[12px] border-t border-slate-100 py-1.5 first:border-t-0">
        <span class="font-semibold text-slate-700">v${v.version}</span>
        <span class="text-slate-400">${v.steps} steps · ${Math.round(v.confidence * 100)}% · ${esc(v.state)}</span>
        <button onclick="viewVersion(${v.version})" class="ml-auto text-slate-500 hover:text-brand-violet">View</button>
        <button onclick="downloadVersion(${v.version})" class="text-brand-violet hover:underline" title="Download in the selected format">⬇</button>
      </div>`).join("");
  } catch (e) { /* best-effort */ }
}
async function viewVersion(v) {
  try { renderSop(await api(`/v1/sops/${sopId}/versions/${v}`)); } catch (e) { /* ignore */ }
}
async function downloadVersion(v) {
  const fmt = $("fmt").value;
  const r = await fetch(`/v1/sops/${sopId}/exports`, { method: "POST", headers: JSON_H, body: JSON.stringify({ format: fmt, version: v }) });
  if (!r.ok) { setStatus("job-status", "Export failed", "err"); return; }
  const blob = await r.blob();
  const ext = EXPORT_EXT[fmt] || fmt;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = `sop_v${v}.${ext}`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(a.href);
}

async function approve(no) {
  await api(`/v1/sops/${sopId}/steps/${no}:approve`, { method: "POST" });
  setStatus("job-status", `Step ${no} approved.`, "ok");
  await loadSop();
}

async function publish() {
  if (!sopId) return;
  try {
    const r = await api(`/v1/sops/${sopId}:publish`, { method: "POST" });
    setStatus("job-status", `Published v${r.version} · ${r.state}`, "ok");
    await loadSop();
  } catch (e) { setStatus("job-status", "Publish blocked: " + e.message, "warn"); }
}

const EXPORT_EXT = { markdown: "md", html: "html", json: "json", bpmn: "bpmn.xml",
                     testcases: "testcases.md", rpa: "rpa.md", docx: "docx", pdf: "pdf" };

async function doExport() {
  if (!sopId) return;
  const fmt = $("fmt").value;
  const r = await fetch(`/v1/sops/${sopId}/exports`, { method: "POST", headers: JSON_H, body: JSON.stringify({ format: fmt }) });
  const out = $("out"); out.style.display = "block";
  if (!r.ok) { out.textContent = "Export failed: " + await r.text(); return; }
  const blob = await r.blob();
  const ext = EXPORT_EXT[fmt] || fmt;
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `sop.${ext}`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(a.href);
  if (fmt === "pdf" || fmt === "docx") {
    out.textContent = `Downloaded sop.${ext}`;
  } else {
    out.textContent = await blob.text();   // download + preview for text formats
  }
}

// ---------- trace ----------
async function loadTrace() {
  const t = await api(`/v1/jobs/${jobId}/trace`);
  $("trace").querySelector("tbody").innerHTML = t.events.map((e) =>
    `<tr class="border-t border-slate-100">
       <td class="py-1 text-slate-700">${e.agent}</td>
       <td class="py-1 text-slate-400">${e.model || ""}</td>
       <td class="py-1 text-slate-500">${Math.round(e.latency_ms)}</td>
       <td class="py-1 font-medium ${e.status === "ok" ? "text-emerald-600" : "text-red-500"}">${e.status}</td>
     </tr>`).join("");
}

// ---------- chat over the SOP (persisted per SOP) ----------
function chatBubble(m) {
  return m.role === "user"
    ? `<div class="text-right"><span class="inline-block bg-violet-100 text-violet-900 rounded-xl px-3 py-1.5 max-w-[85%] text-left whitespace-pre-line">${esc(m.text)}</span></div>`
    : `<div class="text-left"><span class="inline-block bg-slate-100 text-slate-700 rounded-xl px-3 py-1.5 max-w-[90%] whitespace-pre-line">${esc(m.text)}</span></div>`;
}
function renderChat(msgs) {
  const el = $("chat-log");
  el.innerHTML = msgs.length ? msgs.map(chatBubble).join("")
    : `<div class="text-[12px] text-slate-400">No messages yet — ask anything about this SOP.</div>`;
  el.scrollTop = el.scrollHeight;
}
async function loadChat() {
  if (!sopId) return;
  try { renderChat((await api(`/v1/sops/${sopId}/chat`)).messages); } catch (e) { /* best-effort */ }
}
async function sendChat() {
  const input = $("chat-input");
  const msg = input.value.trim();
  if (!msg) return;
  if (!sopId) { setStatus("job-status", "Generate or open a SOP first.", "warn"); return; }
  input.value = "";
  const el = $("chat-log");
  el.insertAdjacentHTML("beforeend", chatBubble({ role: "user", text: msg }));
  el.insertAdjacentHTML("beforeend", `<div class="text-left" id="chat-typing"><span class="inline-block bg-slate-100 text-slate-400 rounded-xl px-3 py-1.5">…</span></div>`);
  el.scrollTop = el.scrollHeight;
  try {
    const r = await api(`/v1/sops/${sopId}/chat`, { method: "POST", body: JSON.stringify({ message: msg }) });
    renderChat(r.messages);
  } catch (e) { const t = $("chat-typing"); if (t) t.remove(); setStatus("job-status", "✗ " + e.message, "err"); }
}

// ---------- refine (regenerate a better SOP from follow-up changes; old kept as a version) ----------
async function refineSop() {
  if (running) return;
  if (!sopId || !processId) { setStatus("job-status", "Generate or open a SOP first.", "warn"); return; }
  const changes = $("refine").value.trim();
  if (!changes) { setStatus("job-status", "Describe the changes you want.", "warn"); return; }
  running = true; $("run-btn").disabled = true;
  startProgress();
  $("stage").textContent = "Applying your changes";
  try {
    const j = await api("/v1/jobs", { method: "POST", body: JSON.stringify({
      process_id: processId, options: { async: true, refine_sop_id: sopId, instruction: changes } }) });
    jobId = j.jobId;
    $("refine").value = "";
    pollJob();   // on completion re-loads the SOP (same id, new version) + version history
  } catch (e) { stopProgress(false); setStatus("job-status", "✗ " + e.message, "err"); running = false; $("run-btn").disabled = false; }
}

// ---------- feedback / learning memory ----------
async function loadFeedback() {
  try {
    const r = await api("/v1/feedback");
    const b = $("learn-badge");
    if (r.corrections > 0) {
      b.textContent = `🧠 learned from ${r.corrections} correction${r.corrections > 1 ? "s" : ""}`;
      b.classList.remove("hidden");
    } else { b.classList.add("hidden"); }
  } catch (e) { /* best-effort */ }
}
async function submitRating(rating) {
  try {
    await api("/v1/feedback", { method: "POST", body: JSON.stringify({ sop_id: sopId, rating }) });
    setStatus("job-status", rating === "up" ? "Thanks — feedback saved." : "Noted — the AI will learn from it.", "ok");
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}

// ---------- history (past SOPs, like a chat sidebar) ----------
async function loadHistory() {
  try {
    const r = await api("/v1/sops");
    const el = $("history");
    if (!r.sops.length) { el.innerHTML = `<div class="text-[12px] text-slate-400">No SOPs yet.</div>`; return; }
    el.innerHTML = r.sops.map((s) => `
      <div onclick="openSop('${s.id}')" data-id="${s.id}"
           class="hist-item cursor-pointer rounded-lg border border-slate-100 hover:border-brand-violet px-3 py-2 mb-1.5">
        <div class="text-[13px] font-medium text-slate-700 truncate">${esc(s.title)}</div>
        <div class="text-[11px] text-slate-400">${s.steps} steps · ${Math.round(s.confidence * 100)}% · ${esc(s.state)}</div>
      </div>`).join("");
  } catch (e) { /* history is best-effort */ }
}

// Reopen a past SOP: load it + its screenshots into the viewer (no job needed).
async function openSop(id) {
  try {
    const sop = await api(`/v1/sops/${id}`);
    sopId = id; jobId = null; processId = sop.process_id;
    const proc = await api(`/v1/processes/${processId}`);
    screens = (proc.artifacts || [])
      .sort((a, b) => (a.order || 0) - (b.order || 0))
      .map((a) => ({ artifact_id: a.id, order: a.order || 1, elements: [], text: [] }));
    buildViewer();
    renderSop(sop);
    loadChat();
    $("trace").querySelector("tbody").innerHTML = "";
    [...document.querySelectorAll(".hist-item")].forEach((x) => x.classList.toggle("border-brand-violet", x.dataset.id === id));
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}

// ---------- misc ----------
function setStatus(id, msg, cls) {
  const el = $(id);
  el.textContent = msg;
  const color = { ok: "text-emerald-600", warn: "text-amber-600", err: "text-red-500" }[cls] || "text-slate-400";
  el.className = "text-[12px] mt-1 " + color;
}
function esc(s) { const d = document.createElement("div"); d.textContent = s ?? ""; return d.innerHTML; }
function resetAll() { location.reload(); }

fetch("/v1/health").then((r) => r.json()).then((h) => {
  $("profile-badge").textContent = `profile: ${h.model_profile || "?"}`;
}).catch(() => {});
loadHistory();
loadFeedback();
