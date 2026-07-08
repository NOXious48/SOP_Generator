// ProcessIQ demo UI — real upload -> async pipeline -> perception overlays -> SOP.
// Talks to the control-plane API on the same origin. Admin headers for single-user demo.
const H = { "X-Tenant": "demo", "X-User": "demo@analyst", "X-Roles": "Admin,Analyst,Reviewer" };
const JSON_H = { ...H, "Content-Type": "application/json" };

let processId = null, jobId = null, sopId = null;
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
  if (!processId || !artifacts.length) return;
  $("run-btn").disabled = true;
  setStatus("job-status", "");
  $("stage").textContent = "starting…"; $("bar").style.width = "3%";
  try {
    const j = await api("/v1/jobs", { method: "POST",
      body: JSON.stringify({ process_id: processId,
        options: { async: true, instruction: $("instruction").value.trim() } }) });
    jobId = j.jobId;
    pollJob();
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); $("run-btn").disabled = false; }
}

async function pollJob() {
  try {
    const job = await api(`/v1/jobs/${jobId}`);
    const prog = await api(`/v1/jobs/${jobId}/progress`);
    const last = prog.events[prog.events.length - 1];
    if (last) { $("bar").style.width = `${Math.max(3, last.progress)}%`; $("stage").textContent = `${last.stage} — ${last.message}`; }
    if (job.status === "FAILED") {
      setStatus("job-status", "✗ " + (job.error ? job.error.detail : "pipeline failed"), "err");
      $("run-btn").disabled = false; return;
    }
    if (job.status === "COMPLETED" || job.status === "NEEDS_REVIEW") {
      sopId = job.sop_id; $("bar").style.width = "100%"; $("stage").textContent = "done";
      setStatus("job-status", job.status === "NEEDS_REVIEW" ? "Done — some steps need review." : "Done.", job.status === "NEEDS_REVIEW" ? "warn" : "ok");
      await Promise.all([loadSop(), loadPerception(), loadTrace()]);
      $("run-btn").disabled = false; return;
    }
    setTimeout(pollJob, 1000);
  } catch (e) { setStatus("job-status", "✗ " + e.message, "err"); $("run-btn").disabled = false; }
}

// ---------- perception viewer ----------
async function loadPerception() {
  const p = await api(`/v1/jobs/${jobId}/perception`);
  screens = p.screens;
  $("viewer-empty").classList.add("hidden");     // swap the cover hero for the live viewer
  $("viewer-content").classList.remove("hidden");
  const strip = $("strip");
  strip.innerHTML = "";
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
  const box = (b) => [b[0] * W, b[1] * Hh, b[2] * W, b[3] * Hh];
  if ($("t-el").checked) {
    ctx.strokeStyle = "#7C3AED"; ctx.lineWidth = Math.max(2, W / 700);
    for (const el of screen.elements) { const [x, y, w, h] = box(el.bbox); ctx.strokeRect(x, y, w, h); }
  }
  if ($("t-ocr").checked) {
    ctx.strokeStyle = "#06B6D4"; ctx.lineWidth = Math.max(1, W / 1000);
    for (const t of screen.text) { const [x, y, w, h] = box(t.bbox); ctx.strokeRect(x, y, w, h); }
  }
  if (highlightBbox) {
    ctx.strokeStyle = "#F59E0B"; ctx.lineWidth = Math.max(4, W / 320);
    const [x, y, w, h] = box(highlightBbox); ctx.strokeRect(x, y, w, h);
  }
  $("c-el").textContent = screen.elements.length;
  $("c-ocr").textContent = screen.text.length;
  $("sel-info").textContent = `screen ${screen.order}`;
}

// ---------- SOP ----------
async function loadSop() {
  if (!sopId) return;
  const sop = await api(`/v1/sops/${sopId}`);
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
    return `<div class="step-card" ${ref} onclick="stepClick(this)">
      <div class="flex justify-between items-center gap-2"><b class="text-[13px]">${s.no}. ${esc(s.action)}</b>${badge}</div>
      <div class="text-[12px] text-slate-500 mt-1 whitespace-pre-line">${esc(s.description)}</div>
      <div class="meter mt-2"><div style="width:${Math.round(s.confidence * 100)}%"></div></div>
      ${flagged ? `<button class="mt-2 text-[12px] font-medium text-brand-violet border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50" onclick="event.stopPropagation();approve(${s.no})">Approve step</button>` : ""}
    </div>`;
  }).join("");
}

function stepClick(el) {
  [...$("steps").children].forEach((s) => s.classList.remove("sel"));
  el.classList.add("sel");
  const art = el.dataset.art;
  if (art && images[art]) selectScreen(art, el.dataset.bbox.split(",").map(Number));
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
