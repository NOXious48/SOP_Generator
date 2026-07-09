// ProcessIQ demo UI — real upload -> async pipeline -> perception overlays -> SOP.
// Talks to the control-plane API on the same origin. Admin headers for single-user demo.
const H = { "X-Tenant": "demo", "X-User": "demo@admin", "X-Roles": "Admin,Analyst,Reviewer" };
const JSON_H = { ...H, "Content-Type": "application/json" };

// Two experiences of the same app. Admin authors SOPs; User reads them and submits improvement
// suggestions. Switching updates the identity headers so the server enforces the same boundary.
const ROLE_HEADERS = {
  admin: { user: "demo@admin", roles: "Admin,Analyst,Reviewer" },
  user:  { user: "demo@user",  roles: "Viewer" },
};
// A ?role= in the URL (from the /admin or /user entry points) wins over the last saved choice.
const _urlRole = new URLSearchParams(location.search).get("role");
let role = (_urlRole === "admin" || _urlRole === "user") ? _urlRole
           : (localStorage.getItem("piq_role") || "admin");
function applyRoleHeaders() {
  const r = ROLE_HEADERS[role] || ROLE_HEADERS.admin;
  H["X-User"] = r.user; H["X-Roles"] = r.roles;
  JSON_H["X-User"] = r.user; JSON_H["X-Roles"] = r.roles;
}
function setRole(r) {
  role = r === "user" ? "user" : "admin";
  localStorage.setItem("piq_role", role);
  applyRoleHeaders();
  document.body.classList.toggle("role-admin", role === "admin");
  document.body.classList.toggle("role-user", role === "user");
  const ab = $("role-admin-btn"), ub = $("role-user-btn");
  if (ab && ub) { ab.classList.toggle("on", role === "admin"); ub.classList.toggle("on", role === "user"); }
  if (sopId) loadSuggestions();   // refresh the role-specific panels for the open SOP
}
applyRoleHeaders();

let processId = null, jobId = null, sopId = null;
let running = false;   // guards against double-clicking Run (would fire two jobs / two API calls)
let onJobDone = null;  // one-shot callback fired when the next pipeline job completes
let currentSop = null; // last-rendered SOP (source for inline step editing)
let openSuggestions = [];  // admin inbox: currently-open suggestions for the loaded SOP
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

// image types we accept (all re-encoded to PNG server-side, so Gemini always gets a supported format)
const ACCEPT_RE = /\.(png|jpe?g|webp|gif|bmp)$/i;
const isSupportedImage = (f) => f.type.startsWith("image/") || ACCEPT_RE.test(f.name);

async function addFiles(fileList) {
  const all = [...fileList];
  const files = all.filter(isSupportedImage);
  const skipped = all.length - files.length;
  if (!files.length) {
    if (skipped) setStatus("upload-status", "✗ Unsupported file type. Use PNG, JPG, JPEG, WEBP, GIF or BMP.", "err");
    return;
  }
  try {
    await ensureProcess();
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const r = await fetch(`/v1/processes/${processId}/uploads:file`, { method: "POST", headers: H, body: fd });
      const body = await r.json();
      if (!r.ok) { setStatus("upload-status", `✗ ${f.name}: ${body.detail || r.status}`, "err"); continue; }
      artifacts.push({ id: body.artifactId, order: body.order, filename: f.name, url: URL.createObjectURL(f) });
    }
    renderThumbs();
    const extra = skipped ? ` (${skipped} unsupported file(s) skipped)` : "";
    setStatus("upload-status", `${artifacts.length} screenshot(s) registered.${extra}`, skipped ? "warn" : "ok");
    $("run-btn").disabled = artifacts.length === 0;
  } catch (e) { setStatus("upload-status", "✗ " + e.message, "err"); }
}

// ---------- thumbnail strip: drag to reorder, click ✕ to remove ----------
let dragFrom = null;
function renderThumbs() {
  const box = $("thumbs");
  box.innerHTML = "";
  artifacts.forEach((a, i) => {
    const div = document.createElement("div");
    div.className = "thumb relative w-[70px] cursor-grab";
    div.draggable = true;
    div.dataset.i = i;
    div.innerHTML =
      `<img src="${a.url}" class="w-[70px] h-[46px] object-cover rounded-md border border-slate-200 pointer-events-none" />
       <span class="absolute top-1 left-1 text-[10px] text-white bg-slate-900/70 rounded px-1">${i + 1}</span>
       <button title="Remove" data-x="${a.id}"
         class="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-rose-500 text-white text-[10px] leading-none flex items-center justify-center shadow hover:bg-rose-600">✕</button>`;
    box.appendChild(div);
  });
  $("thumbs-hint").classList.toggle("hidden", artifacts.length === 0);
}

// click ✕ to remove, click the image to open it large (event-delegated so it survives re-renders)
$("thumbs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-x]");
  if (btn) { removeArtifact(btn.dataset.x); return; }
  const t = e.target.closest(".thumb");
  if (t) { const a = artifacts[+t.dataset.i]; if (a) openLightbox(a.url, a.filename); }
});
// drag reorder
$("thumbs").addEventListener("dragstart", (e) => {
  const t = e.target.closest(".thumb"); if (!t) return;
  dragFrom = +t.dataset.i; e.dataTransfer.effectAllowed = "move"; t.classList.add("opacity-40");
});
$("thumbs").addEventListener("dragend", (e) => { const t = e.target.closest(".thumb"); if (t) t.classList.remove("opacity-40"); });
$("thumbs").addEventListener("dragover", (e) => e.preventDefault());
$("thumbs").addEventListener("drop", (e) => {
  e.preventDefault();
  if (dragFrom === null) return;
  const from = dragFrom; dragFrom = null;
  moveArtifact(from, dropSlot(e.clientX));
});

// Insertion slot = number of thumbnails whose horizontal midpoint is left of the cursor.
// Computed against every thumbnail (not just the drop target), so it works dragging in any
// direction and even when dropping over the gap between thumbnails or past the last one.
function dropSlot(x) {
  const thumbs = [...$("thumbs").querySelectorAll(".thumb")];
  for (let i = 0; i < thumbs.length; i++) {
    const rect = thumbs[i].getBoundingClientRect();
    if (x < rect.left + rect.width / 2) return i;
  }
  return thumbs.length;
}

function moveArtifact(from, to) {
  if (from < to) to -= 1;                   // removing the dragged item shifts later slots left by one
  to = Math.max(0, Math.min(to, artifacts.length - 1));
  if (to === from) { renderThumbs(); return; }   // dropped back in place — leave the array untouched
  const [moved] = artifacts.splice(from, 1);
  artifacts.splice(to, 0, moved);
  renderThumbs();
  syncOrder();
}

async function syncOrder() {
  if (!processId || !artifacts.length) return;
  try {
    await api(`/v1/processes/${processId}/artifacts:reorder`, {
      method: "POST", body: JSON.stringify({ order: artifacts.map((a) => a.id) }) });
    setStatus("upload-status", `Order updated — ${artifacts.length} screenshot(s).`, "ok");
  } catch (e) { setStatus("upload-status", "✗ reorder failed: " + e.message, "err"); }
}

async function removeArtifact(id) {
  if (!processId) return;
  try {
    await api(`/v1/processes/${processId}/artifacts/${id}`, { method: "DELETE" });
    artifacts = artifacts.filter((a) => a.id !== id);
    renderThumbs();
    setStatus("upload-status", artifacts.length ? `${artifacts.length} screenshot(s) registered.` : "No screenshots yet.", artifacts.length ? "ok" : "");
    $("run-btn").disabled = artifacts.length === 0;
  } catch (e) { setStatus("upload-status", "✗ remove failed: " + e.message, "err"); }
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
      if (onJobDone) { const cb = onJobDone; onJobDone = null; try { await cb(); } catch (e) { /* ignore */ } }
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
    img.title = "Click to select · double-click to enlarge";
    img.onclick = () => selectScreen(s.artifact_id);
    img.ondblclick = () => openLightbox(img.src, `Screen ${s.order}`);
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
    pct += Math.max(0.25, (93 - pct) * 0.0225);   // creep toward 93% at half speed; never hit 100 until done
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

// small helpers for the document-format sections shown on screen
function confLabel(c) { const p = c * 100; return p >= 80 ? "High" : p >= 60 ? "Moderate" : "Low"; }
function renderSection(label, items) {
  if (!items || !items.length) return "";
  const lis = items.map((x) => `<li>${esc(x)}</li>`).join("");
  return `<div class="mt-3"><div class="eyebrow mb-1">${esc(label)}</div>
    <ul class="list-disc pl-5 text-[12px] text-slate-600 space-y-0.5">${lis}</ul></div>`;
}

function renderSop(sop) {
  currentSop = sop;
  const fb = $("sop-fb"); if (fb) fb.style.display = "inline-flex";
  $("sop-title").textContent = `${sop.title}`;
  $("k-steps").textContent = sop.steps.length;
  $("k-conf").textContent = Math.round(sop.overall_confidence * 100) + "%";
  $("k-state").textContent = sop.state;
  // Objective + Pre-requisites (sections 1 & 2 of the document format)
  $("sop-objective").textContent = sop.objective || "";
  $("sop-prereqs").innerHTML = renderSection("Pre-requisites", sop.prerequisites);
  $("sop-steps-label").classList.toggle("hidden", !sop.steps.length);
  // Exception handling, validation, output + confidence (sections 4–7)
  $("sop-extra").innerHTML =
    renderSection("Exception handling", sop.exceptions) +
    renderSection("Validation & checks", sop.validation) +
    (sop.output ? `<div class="mt-3"><div class="eyebrow mb-1">Output</div>
       <div class="text-[12px] text-slate-600">${esc(sop.output)}</div></div>` : "") +
    `<div class="mt-3"><div class="eyebrow mb-1">Confidence score</div>
       <div class="text-[12px] text-slate-600"><b>${Math.round(sop.overall_confidence * 100)}%</b>
       — ${confLabel(sop.overall_confidence)} confidence in the reconstructed workflow.</div></div>`;
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
          <button title="Edit step" onclick="event.stopPropagation();editStep(${s.no})" class="admin-only text-[12px] text-slate-400 hover:text-brand-violet">✏️</button>
          <button title="Suggest an improvement for this step" onclick="event.stopPropagation();suggestStep(${s.no})" class="user-only text-[11px] font-medium text-slate-400 hover:text-brand-violet whitespace-nowrap">💡 Suggest</button>
        </span>
      </div>
      <div class="text-[12px] text-slate-500 mt-1 whitespace-pre-line">${esc(s.description)}</div>
      <div class="meter mt-2"><div style="width:${Math.round(s.confidence * 100)}%"></div></div>
      ${flagged ? `<button class="admin-only mt-2 text-[12px] font-medium text-brand-violet border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50" onclick="event.stopPropagation();approve(${s.no})">Approve step</button>` : ""}
    </div>`;
  }).join("") +
  `<button onclick="addStep()" class="admin-only w-full mt-1 text-[12px] font-medium text-brand-violet border border-dashed border-slate-300 rounded-lg py-2 hover:bg-slate-50">+ Add step</button>`;
  loadVersions();
  loadSuggestions();
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

// ---------- UI drift detection (upload current screenshots -> compare vs SOP's originals) ----------
let driftProcessId = null;   // process holding the freshly-uploaded "current" screenshots
const driftDrop = $("drift-drop"), driftInput = $("drift-input");
const DOVER = ["bg-violet-50", "border-brand-violet"];
driftDrop.onclick = () => { if (sopId) driftInput.click(); };
driftDrop.ondragover = (e) => { e.preventDefault(); driftDrop.classList.add(...DOVER); };
driftDrop.ondragleave = () => driftDrop.classList.remove(...DOVER);
driftDrop.ondrop = (e) => { e.preventDefault(); driftDrop.classList.remove(...DOVER); driftCheck(e.dataTransfer.files); };
driftInput.onchange = () => driftCheck(driftInput.files);

async function driftCheck(fileList) {
  if (!sopId) { setStatus("drift-status", "Generate or open a SOP first.", "warn"); return; }
  const files = [...fileList].filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  setStatus("drift-status", "Uploading updated screenshots…", "");
  try {
    // fresh process for the current screenshots, uploaded in order
    const p = await api("/v1/processes", { method: "POST", body: JSON.stringify({ name: "UI drift check" }) });
    driftProcessId = p.processId;
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f, f.name);
      const r = await fetch(`/v1/processes/${driftProcessId}/uploads:file`, { method: "POST", headers: H, body: fd });
      if (!r.ok) { const b = await r.json(); throw new Error(`${f.name}: ${b.detail || r.status}`); }
    }
    setStatus("drift-status", "Comparing against this SOP's screenshots…", "");
    const rep = await api(`/v1/sops/${sopId}/drift`, { method: "POST", body: JSON.stringify({ new_process_id: driftProcessId }) });
    renderDrift(rep);
  } catch (e) { setStatus("drift-status", "✗ " + e.message, "err"); }
  driftInput.value = "";
}

function renderDrift(rep) {
  const box = $("drift-report");
  box.classList.remove("hidden");
  const pct = Math.round((rep.driftScore || 0) * 100);
  const rows = (rep.screens || []).map((s) => {
    const label = s.note ? s.note : (s.changed ? `changed (distance ${s.distance})` : `unchanged (distance ${s.distance})`);
    const color = s.changed ? "text-rose-600" : "text-emerald-600";
    const dot = s.changed ? "bg-rose-500" : "bg-emerald-500";
    return `<div class="flex items-center gap-2 text-[12px] py-0.5">
      <span class="inline-block w-2 h-2 rounded-full ${dot}"></span>
      <span class="text-slate-500">Screen ${s.order}</span><span class="${color}">${label}</span></div>`;
  }).join("");
  const affected = (rep.affectedSteps || []).length
    ? `<div class="text-[12px] text-slate-600 mt-1">Steps likely affected: <b>${rep.affectedSteps.join(", ")}</b></div>` : "";
  if (rep.drift) {
    setStatus("drift-status", `⚠ UI drift detected — ${rep.changedScreens}/${rep.totalScreens} screens changed (${pct}%).`, "warn");
    box.innerHTML = rows + affected +
      `<button onclick="regenerateFromDrift()" class="btn-grad text-white text-[13px] font-semibold rounded-lg px-4 py-2 w-full mt-3">Update SOP from updated screenshots</button>`;
  } else {
    setStatus("drift-status", `✓ No UI drift — the SOP still matches the current screens.`, "ok");
    box.innerHTML = rows;
  }
}

// regenerate the SOP from the newly-uploaded screenshots (old kept as a version)
async function regenerateFromDrift() {
  if (running || !driftProcessId || !sopId) return;
  running = true; $("run-btn").disabled = true;
  startProgress();
  $("stage").textContent = "Updating SOP for the new UI";
  try {
    const j = await api("/v1/jobs", { method: "POST", body: JSON.stringify({
      process_id: driftProcessId,
      options: { async: true, refine_sop_id: sopId,
        instruction: "The UI has changed. Regenerate this SOP from these updated screenshots, re-deriving every step and its click target from the new UI." } }) });
    jobId = j.jobId;
    processId = driftProcessId;   // the SOP now points at the updated screenshots
    $("drift-report").classList.add("hidden");
    setStatus("drift-status", "");
    pollJob();   // reloads SOP (same id, new version) + perception from the new screenshots
  } catch (e) { stopProgress(false); setStatus("job-status", "✗ " + e.message, "err"); running = false; $("run-btn").disabled = false; }
}

function resetDrift() {
  driftProcessId = null;
  $("drift-report").classList.add("hidden");
  $("drift-report").innerHTML = "";
  setStatus("drift-status", "");
}

// ---------- improvement suggestions (User submits · Admin curates & regenerates) ----------
function statusPill(status) {
  const map = { open: ["Open", "bg-amber-100 text-amber-700"],
                resolved: ["Resolved", "bg-emerald-100 text-emerald-700"],
                dismissed: ["Dismissed", "bg-slate-100 text-slate-500"] };
  const [label, cls] = map[status] || map.open;
  return `<span class="text-[10px] font-semibold px-2 py-0.5 rounded-full ${cls}">${label}</span>`;
}

// One GET fills both panels; CSS shows the one for the active role.
async function loadSuggestions() {
  if (!sopId) return;
  try {
    const r = await api(`/v1/sops/${sopId}/suggestions`);
    renderInbox(r);
    renderMySuggestions(r);
  } catch (e) { /* best-effort */ }
}

// ----- USER side -----
async function submitSuggestion(stepNo) {
  if (!sopId) { setStatus("suggest-status", "Open a SOP first.", "warn"); return; }
  const ta = $("suggest-input");
  const comment = ta.value.trim();
  if (!comment) { setStatus("suggest-status", "Write a suggestion first.", "warn"); return; }
  try {
    await api(`/v1/sops/${sopId}/suggestions`, { method: "POST", body: JSON.stringify({ comment, step_no: stepNo }) });
    ta.value = "";
    setStatus("suggest-status", "Suggestion submitted — thank you!", "ok");
    loadSuggestions();
  } catch (e) { setStatus("suggest-status", "✗ " + e.message, "err"); }
}

// inline "suggest for this step" form injected into a step card (user mode)
function suggestStep(no) {
  const card = document.querySelector(`.step-card[data-no="${no}"]`);
  if (!card || card.dataset.suggesting) return;
  card.dataset.suggesting = "1";
  const box = document.createElement("div");
  box.className = "mt-2 border-t border-slate-100 pt-2";
  box.innerHTML = `
    <textarea class="field step-suggest text-[12px]" rows="2" placeholder="What should change about step ${no}?"></textarea>
    <div class="flex gap-2 mt-2">
      <button class="btn-grad text-white text-[12px] font-semibold rounded-lg px-3 py-1.5" onclick="event.stopPropagation();sendStepSuggestion(${no}, this)">Send</button>
      <button class="text-[12px] text-slate-600 border border-slate-200 rounded-lg px-3 py-1.5" onclick="event.stopPropagation();cancelStepSuggestion(this)">Cancel</button>
    </div>`;
  card.appendChild(box);
  box.querySelector("textarea").focus();
}
function cancelStepSuggestion(btn) {
  const card = btn.closest(".step-card");
  if (card) card.removeAttribute("data-suggesting");
  btn.closest("div.mt-2").remove();
}
async function sendStepSuggestion(no, btn) {
  const card = btn.closest(".step-card");
  const comment = card.querySelector(".step-suggest").value.trim();
  if (!comment) { card.querySelector(".step-suggest").focus(); return; }
  try {
    await api(`/v1/sops/${sopId}/suggestions`, { method: "POST", body: JSON.stringify({ comment, step_no: no }) });
    card.removeAttribute("data-suggesting");
    setStatus("suggest-status", `Suggestion for step ${no} sent — thank you!`, "ok");
    loadSop();   // re-render clears the inline form and refreshes "Your suggestions"
  } catch (e) { setStatus("suggest-status", "✗ " + e.message, "err"); }
}

function renderMySuggestions(r) {
  const el = $("my-suggestions"); if (!el) return;
  const mine = (r.suggestions || []).filter((s) => s.author === H["X-User"]);
  if (!mine.length) { el.innerHTML = `<div class="text-[12px] text-slate-400">None yet.</div>`; return; }
  el.innerHTML = mine.map((s) => `
    <div class="border-t border-slate-100 py-1.5 first:border-t-0 text-[12px]">
      <div class="flex items-center gap-2"><span class="font-semibold text-slate-600">${s.stepNo ? "Step " + s.stepNo : "Whole SOP"}</span>${statusPill(s.status)}</div>
      <div class="text-slate-500 mt-0.5 whitespace-pre-line">${esc(s.effective)}</div>
      ${s.resolvedVersion ? `<div class="text-[11px] text-emerald-600 mt-0.5">✓ Applied in v${s.resolvedVersion}</div>` : ""}
    </div>`).join("");
}

// ----- ADMIN side -----
function renderInbox(r) {
  const el = $("inbox"); if (!el) return;
  const items = r.suggestions || [];
  openSuggestions = items.filter((s) => s.status === "open");
  const count = $("inbox-count");
  if (count) { count.textContent = `${openSuggestions.length} open`; count.classList.toggle("hidden", items.length === 0); }
  $("improve-btn").classList.toggle("hidden", openSuggestions.length === 0);
  if (!items.length) { el.innerHTML = `<div class="text-[12px] text-slate-400">No suggestions yet.</div>`; return; }
  el.innerHTML = items.map((s) => {
    const actions = s.status === "open"
      ? `<button onclick="curate('${s.id}','resolved')" class="text-[11px] text-emerald-600 hover:underline">Resolve</button>
         <button onclick="curate('${s.id}','dismissed')" class="text-[11px] text-slate-400 hover:underline">Dismiss</button>`
      : `<button onclick="curate('${s.id}','open')" class="text-[11px] text-brand-violet hover:underline">Reopen</button>`;
    return `<div class="border-t border-slate-100 py-2 first:border-t-0" data-sid="${s.id}">
      <div class="flex items-center gap-2 text-[12px]">
        <span class="font-semibold text-slate-600">${s.stepNo ? "Step " + s.stepNo : "Whole SOP"}</span>${statusPill(s.status)}
        <span class="text-slate-400 truncate">${esc(s.author || "")}</span>
      </div>
      <textarea class="field sug-edit text-[12px] mt-1" rows="2">${esc(s.effective)}</textarea>
      <div class="flex items-center gap-3 mt-1">
        <button onclick="saveCurate('${s.id}', this)" class="text-[11px] text-brand-violet hover:underline">Save edit</button>
        ${actions}
        ${s.resolvedVersion ? `<span class="text-[11px] text-emerald-600 ml-auto">→ v${s.resolvedVersion}</span>` : ""}
      </div>
    </div>`;
  }).join("");
}

async function curate(sid, status) {
  try {
    await api(`/v1/sops/${sopId}/suggestions/${sid}`, { method: "PATCH", body: JSON.stringify({ status }) });
    loadSuggestions();
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}
async function saveCurate(sid, btn) {
  const wrap = btn.closest("[data-sid]");
  const edited_comment = wrap.querySelector(".sug-edit").value;
  try {
    await api(`/v1/sops/${sopId}/suggestions/${sid}`, { method: "PATCH", body: JSON.stringify({ edited_comment }) });
    setStatus("job-status", "Suggestion wording updated.", "ok");
    loadSuggestions();
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}

// Fold the open suggestions into a refine instruction, regenerate a new version, then mark them resolved.
async function generateImproved() {
  if (running || !sopId || !processId || !openSuggestions.length) return;
  const picked = openSuggestions.slice();
  const lines = picked.map((s, i) => `${i + 1}. ${s.stepNo ? `(Step ${s.stepNo}) ` : ""}${s.effective}`);
  const instruction = "Apply these user-submitted improvement suggestions and regenerate an improved SOP, " +
    "re-deriving the affected steps and their click targets while keeping everything else intact:\n" + lines.join("\n");
  running = true; $("run-btn").disabled = true;
  startProgress();
  $("stage").textContent = "Applying user suggestions";
  try {
    const j = await api("/v1/jobs", { method: "POST", body: JSON.stringify({
      process_id: processId, options: { async: true, refine_sop_id: sopId, instruction } }) });
    jobId = j.jobId;
    onJobDone = async () => {
      const v = currentSop ? currentSop.version : null;
      for (const s of picked) {
        try {
          await api(`/v1/sops/${sopId}/suggestions/${s.id}`, { method: "PATCH",
            body: JSON.stringify({ status: "resolved", resolved_version: v }) });
        } catch (e) { /* ignore individual failures */ }
      }
      loadSuggestions();
      setStatus("job-status", `Improved version v${v} generated from ${picked.length} suggestion(s).`, "ok");
    };
    pollJob();
  } catch (e) { stopProgress(false); setStatus("job-status", "✗ " + e.message, "err"); running = false; $("run-btn").disabled = false; }
}

// ---------- feedback / learning memory ----------
async function loadFeedback() {
  try {
    const r = await api("/v1/feedback");
    const b = $("learn-badge");
    if (!b) return;
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
    resetDrift();
    $("trace").querySelector("tbody").innerHTML = "";
    [...document.querySelectorAll(".hist-item")].forEach((x) => x.classList.toggle("border-brand-violet", x.dataset.id === id));
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); }
}

// ---------- image lightbox (click a screenshot to view it full-size) ----------
function openLightbox(src, caption) {
  let ov = $("lightbox");
  if (!ov) {
    ov = document.createElement("div");
    ov.id = "lightbox";
    ov.className = "fixed inset-0 z-50 hidden items-center justify-center bg-black/80 p-6";
    ov.innerHTML = `
      <button id="lightbox-close" title="Close (Esc)" class="absolute top-4 right-5 text-white/80 hover:text-white text-3xl leading-none">&times;</button>
      <figure class="max-w-[92vw] max-h-[92vh] flex flex-col items-center gap-3">
        <img id="lightbox-img" alt="" class="max-w-full max-h-[82vh] object-contain rounded-lg shadow-2xl bg-white" />
        <figcaption id="lightbox-cap" class="text-white/80 text-[13px] text-center"></figcaption>
      </figure>`;
    document.body.appendChild(ov);
    // dismiss on backdrop click or the ✕ (clicking the image itself does nothing)
    ov.addEventListener("click", (e) => { if (e.target === ov || e.target.id === "lightbox-close") closeLightbox(); });
  }
  $("lightbox-img").src = src;
  $("lightbox-cap").textContent = caption || "";
  ov.classList.remove("hidden");
  ov.classList.add("flex");
}
function closeLightbox() {
  const ov = $("lightbox");
  if (ov) { ov.classList.add("hidden"); ov.classList.remove("flex"); }
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeLightbox(); });

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
  const badge = $("profile-badge");
  if (badge) badge.textContent = `profile: ${h.model_profile || "?"}`;
}).catch(() => {});
setRole(role);   // apply persisted role: body classes, toggle styling, identity headers
loadHistory();
loadFeedback();
