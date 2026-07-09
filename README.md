<div align="center">

# ProcessIQ

### Enterprise AI Process Intelligence Platform

**Turn screenshots into professional, step-by-step Standard Operating Procedures — automatically.**

_From visuals to value. Automated · Intelligent · Actionable._

</div>

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [What ProcessIQ Does](#2-what-processiq-does)
3. [How It Works](#3-how-it-works)
4. [Architecture](#4-architecture)
5. [Technology Stack](#5-technology-stack)
6. [Quick Start (for everyone)](#6-quick-start)
   - [Step 0 — Get a free Gemini API key](#step-0--get-a-free-google-gemini-api-key-2-minutes)
   - [Option A — Run with Docker (easiest)](#option-a--run-with-docker-easiest--recommended)
   - [Option B — Run with Python](#option-b--run-with-python)
   - [Optional — Pixel-perfect click boxes](#optional--pixel-perfect-click-boxes-advanced)
7. [Roles & Access](#7-roles--access)
8. [Feature Catalog — every feature](#8-feature-catalog--every-feature)
   - [8.1 Admin features](#81-admin-features)
   - [8.2 User features](#82-user-features)
   - [8.3 Platform features (shared)](#83-platform-features-shared)
9. [The Generated SOP — document format](#9-the-generated-sop--document-format)
10. [API Reference](#10-api-reference)
11. [Configuration Reference](#11-configuration-reference)
12. [Project Structure](#12-project-structure)
13. [Hardware Profiles & Deployment](#13-hardware-profiles--deployment)
14. [Security, Audit & Governance](#14-security-audit--governance)
15. [Testing](#15-testing)
16. [Troubleshooting](#16-troubleshooting)
17. [Status & Roadmap](#17-status--roadmap)

---

## 1. Introduction

Every company runs on **Standard Operating Procedures (SOPs)** — the step-by-step guides that explain
how to do a task in an internal tool ("how to add a new employee", "how to create an order"). Today
these are written by hand: someone screenshots each screen, pastes them into a document, and types
"click the Save button." It's slow, and the moment the software changes, the document is wrong.

**ProcessIQ automates this.** You upload the screenshots of a workflow, describe the process in one
line, and ProcessIQ produces a complete, professional SOP: an objective, prerequisites, numbered
steps, each step showing the exact screenshot **with a box drawn on the button to click**, plus
exception handling, validations, expected output, confidence scores, and a human review/approval
flow.

It is **not an OCR tool.** OCR (reading text) is only one small part. The core is **visual process
intelligence** — understanding the _workflow_ across a sequence of screens, the way a human business
analyst would — plus a full **collaboration loop**: readers submit improvement suggestions, authors
curate them, and ProcessIQ regenerates an improved version.

> Full design set: [`../processiq-design/`](../processiq-design) (Sections 00–22).

---

## 2. What ProcessIQ Does

- 📤 **Ingests visuals** — upload one or many screenshots (PNG/JPG/JPEG/WEBP/GIF/BMP) of a workflow.
  Reorder by drag-and-drop, enlarge any thumbnail, remove individual images.
- 👁️ **Sees the UI** — detects text, buttons, form fields, menus, and layout.
- 🧠 **Understands the workflow** — a vision-LLM infers the sequence of actions, transitions, and
  business intent across all screens in a single pass.
- 📝 **Generates a structured SOP** — title, objective, prerequisites, numbered steps (action +
  expected system response), exception handling, validation checks, expected output, and a confidence
  score.
- 🎯 **Grounds every step to evidence** — each step points at the exact screenshot region / control,
  drawn as a box on the image; OCR can snap the box onto the precise control.
- 📊 **Scores confidence** — per-step and overall; low-confidence / suspicious steps are flagged.
- ✅ **Human-in-the-loop** — review, edit, approve, reject, sign off, and publish; nothing is "final"
  until a human approves. Every change is a new immutable version.
- 🔁 **Refines & learns** — regenerate a better SOP from plain-English change requests; accepted
  corrections feed back into future generations.
- 💡 **Collaboration loop** — readers submit improvement suggestions (whole-SOP or per-step); authors
  curate them and regenerate an improved version.
- 🩺 **Detects UI drift** — compares the current screenshots against the ones the SOP was built from
  and flags screens that changed, so the SOP stays accurate as the software evolves.
- 💬 **Answers questions** — a grounded chat assistant answers questions about any SOP.
- 📎 **Exports anywhere** — PDF, HTML, Markdown, DOCX, JSON, XML, BPMN, test cases, RPA skeletons.
- 🔒 **Governed** — role-based access, tenant isolation, PII redaction, prompt-injection defense, and a
  tamper-evident (hash-chained) audit log.

---

## 3. How It Works

```
  You upload screenshots + a one-line description of the process
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 1  INGEST     validate · preprocess · de-dup · store       │
   │ 2  UNDERSTAND a vision-LLM reads all screenshots at once,   │
   │              infers the steps, and picks the control to     │
   │              click on each screen                           │
   │ 3  GROUND     (optional) OCR snaps each step's box onto the │
   │              exact button/label on the screenshot           │
   │ 4  ASSEMBLE   structured SOP + per-step confidence + flags   │
   │ 5  REVIEW     edit · approve · publish (new version each)   │
   │ 6  EXPORT     PDF · HTML · DOCX · Markdown · BPMN · …        │
   │ 7  IMPROVE    users suggest → admin curates → regenerate    │
   │              an improved version (drift-aware)              │
   └──────────────────────────────────────────────────────────┘
                          │
                          ▼
        A professional SOP with screenshots + click-boxes
```

**Key design idea:** instead of dumping raw pixels into one giant prompt, ProcessIQ sends all
screenshots + your instruction to a vision model in **a single call**, gets back a structured SOP,
then (optionally) uses OCR to pin each step's box onto the exact control. This is cheaper, more
accurate, auditable, and works on the free tier of a hosted model. Accepted corrections and an
approved exemplar are folded back into the prompt as **learned guidance** for future runs.

---

## 4. Architecture

ProcessIQ is split into a fast **control plane** (the API + web UI you interact with) and an
**AI pipeline** of specialized agents. Everything is contract-first (typed Pydantic models), so
each piece is swappable.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WEB UI  (/app · /admin · /user)                    │
│  upload · live progress · screenshot overlays · SOP editor · chat ·   │
│  version history · drift check · improvement inbox / suggestions      │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  REST + async jobs + SSE progress
┌───────────────────────────────▼─────────────────────────────────────┐
│                 CONTROL PLANE  (FastAPI modular monolith)             │
│  processes · jobs · sops · review · improvements · drift · chat ·     │
│  exports · search · integrations · notifications · feedback · admin · │
│  health   —   RBAC + tenant scoping + hash-chained audit             │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  runs a job
┌───────────────────────────────▼─────────────────────────────────────┐
│                        AI PIPELINE  (agents)                          │
│  VLM SOP generation ─► OCR grounding ─► validation ─► confidence      │
│  (perception agents: vision / OCR / layout available for local GPU)   │
│  learned-guidance loop · refine-from-changes · pHash drift            │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  unified model access
┌───────────────────────────────▼─────────────────────────────────────┐
│                    INFERENCE GATEWAY                                   │
│   hardware profiles (mock / local-6gb / server-24gb / cloud)          │
│   hosted VLM (Gemini) · PaddleOCR · OmniParser · VRAM governor · cache │
└──────────────────────────────────────────────────────────────────────┘
```

**Layers (from the design):** `Input → Vision AI → Reasoning → Knowledge → Output`, with
cross-cutting Identity/RBAC, Audit, Observability, and Secrets.

**Persistence:** durable entities (processes, SOPs, versions, reviews, feedback/suggestions, chats)
are kept in memory for speed **and** snapshotted atomically to a JSON file (`data/store.json`), so
data survives restarts. Uploaded images are held in an object store on disk. The design's
Postgres/Mongo/Redis/Qdrant/Neo4j/MinIO stack (§9) is the drop-in production target.

---

## 5. Technology Stack

| Area                        | Technology                                                | Why                                                            |
| --------------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| API / backend               | **FastAPI** (Python 3.12)                                 | async, fast, shares typed models with the AI plane             |
| Contracts                   | **Pydantic v2**                                           | one typed source of truth across API + agents                  |
| Vision-LLM (SOP generation) | **Google Gemini** (`gemini-2.5-flash`), OpenAI-compatible | free tier, strong UI/document understanding                    |
| Grounded chat / refine      | Same hosted LLM (text)                                     | Q&A over a SOP + plain-English refinement                      |
| OCR (box grounding)         | **PaddleOCR** (PP-OCRv5)                                  | accurate text + boxes; mobile (fast) / server (precise) models |
| UI element detection        | **OmniParser v2** (local GPU option)                      | screenshot-purpose element detection                           |
| Model serving               | **Inference Gateway** + hardware profiles                 | swap models by env var; agents stay hardware-agnostic          |
| Image handling              | **Pillow** (re-encode to PNG) + average-hash pHash        | any format → Gemini-safe PNG; dedup & drift signal             |
| Web UI                      | **HTML + Tailwind (CDN)** + vanilla JS, served by the API | zero build step; professional light theme                     |
| Live progress               | **Server-Sent Events (SSE)** + polling                    | streamed job status without a websocket stack                  |
| Exports                     | **reportlab** (PDF), **python-docx** (DOCX), HTML/MD/XML  | multi-format SOP rendering with embedded, annotated screenshots|
| Security                    | RBAC, PII redaction, prompt-injection sanitizer           | untrusted screen text treated as data, not instructions        |
| Audit                       | **SHA-256 hash-chained** log                              | tamper-evident action history                                  |
| Observability               | **Prometheus** metrics (`/metrics`)                       | request + job counters                                         |
| Packaging                   | **Docker** + docker-compose                               | one-command run                                                |
| Datastores (optional/prod)  | Postgres, Mongo, Redis, Qdrant, Neo4j, MinIO              | polyglot persistence (design §9)                               |
| Quality                     | **pytest**, **ruff**, GitHub Actions CI                   | tested + linted on every push                                  |

---

## 6. Quick Start

You can run ProcessIQ two ways: **Docker** (simplest — one command) or **Python** (if you already
have Python). Either way you first need a **free** Google Gemini key. No credit card, no GPU.

### Step 0 — Get a free Google Gemini API key (2 minutes)

1. Go to **https://aistudio.google.com**
2. Sign in with any Google account.
3. Click **"Get API key"** → **"Create API key"**.
4. **Copy the key** (a long string). You'll paste it in a moment.

> The free tier allows ~20 SOPs per day — plenty for testing and demos.

### Download the project

- Easiest: on the GitHub page click the green **Code** button → **Download ZIP** → unzip it.
- Or, if you have git: `git clone <repo-url>` then `cd` into the folder.

### Add your key

1. In the project folder, find the file **`.env.example`**.
2. Make a copy of it and name the copy **`.env`** (just `.env`, nothing before the dot).
3. Open `.env` in any text editor and set these lines (paste your key):
   ```
   HOSTED_VLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
   HOSTED_VLM_API_KEY=PASTE_YOUR_GEMINI_KEY_HERE
   HOSTED_MODEL=gemini-2.5-flash
   INFERENCE_MODE=hosted
   ```
4. Save the file. **Never share this file — it contains your key.**

---

### Option A — Run with Docker (easiest / recommended)

**What you need:** [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and
running. That's it — no Python, no setup.

1. Open a terminal **in the project folder** (the one containing `docker-compose.yml`).
2. Run:
   ```bash
   docker compose up --build
   ```
   The first run downloads and builds the image (a few minutes). You'll see logs; wait for
   `Application startup complete`.
3. Open your browser to one of:
   - **http://localhost:8000/app** — the app (defaults to the Admin experience)
   - **http://localhost:8000/admin** — Admin: author SOPs and act on user feedback
   - **http://localhost:8000/user** — User: browse SOPs & versions and submit improvement suggestions
4. To stop it: press `Ctrl+C` in the terminal (or `docker compose down`).

That's the whole thing. Uploaded screenshots are remembered between restarts (stored in a Docker
volume).

---

### Option B — Run with Python

**What you need:** **Python 3.12** ([python.org/downloads](https://www.python.org/downloads/) — on
Windows, tick _"Add Python to PATH"_ during install).

> ProcessIQ is built and tested on **Python 3.12.x**.

1. Open a terminal **in the project folder**. Confirm your version first:

   ```bash
   python --version      # should print Python 3.12.x
   ```

2. Create and activate a virtual environment (pinned to Python 3.12):

   **Windows (PowerShell):**

   ```powershell
   py -3.12 -m venv .venv          # or: python -m venv .venv  (if python is already 3.12)
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS / Linux:**

   ```bash
   python3.12 -m venv .venv        # or: python3 -m venv .venv  (if python3 is already 3.12)
   source .venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the app:
   ```bash
   uvicorn apps.api.main:app --port 8000
   ```
5. Open one of:
   - **http://localhost:8000/app** — the app (defaults to the Admin experience)
   - **http://localhost:8000/admin** — Admin: author SOPs and act on user feedback
   - **http://localhost:8000/user** — User: browse SOPs & versions and submit improvement suggestions
6. To stop it: press `Ctrl+C`.

> With just `requirements.txt`, SOP boxes come from the vision model (approximate). For pixel-perfect
> boxes, see the optional section below.

---

### Optional — Pixel-perfect click boxes (advanced)

By default the click-boxes are placed by the vision model (good, but a little loose). To snap them
onto the exact button/field, ProcessIQ can run **OCR grounding** locally. This needs extra libraries
and is heavier (CPU-only is slower; a GPU makes it fast).

```bash
# after the Python setup above
pip install paddlepaddle==3.3.1 paddleocr==3.7.0
```

Then in `.env` set:

```
GROUND_BBOX=1
OCR_DEVICE=cpu                 # 'cuda' if you have a working GPU Paddle build (Linux)
OCR_DET_MODEL=PP-OCRv5_mobile_det   # 'PP-OCRv5_server_det' = more accurate, slower
OCR_REC_MODEL=PP-OCRv5_mobile_rec   # 'PP-OCRv5_server_rec'
```

Restart the app. First run downloads the OCR models (~130 MB) once.

---

## 7. Roles & Access

ProcessIQ ships two role-based entry points — **the same app**, scoped to what each role may do. Each
URL pre-sets the experience and sends the matching identity, so the server enforces the boundary (not
just the UI).

| URL | Role | Purpose |
| --- | --- | --- |
| **http://localhost:8000/admin** | **Admin / Author** | Create SOPs from screenshots, edit, review, publish, export, and act on user feedback. |
| **http://localhost:8000/user**  | **User / Reader**  | Browse all SOPs and versions read-only, enlarge screenshots, export/download, chat, and submit improvement suggestions. |
| `http://localhost:8000/app` | (defaults to Admin) | Plain entry point; remembers your last-used role. |

Under the hood the platform supports a richer **RBAC** model (each API action is permission-gated):

| Role | Key permissions |
| --- | --- |
| **Admin** | everything (`*`) |
| **Analyst** | create process, run jobs, read/edit SOPs, submit for review, export, suggest |
| **Reviewer** | read, approve/reject steps, sign off, publish, suggest |
| **Viewer** | read, search, export/download, suggest |
| **Auditor** | read, read audit log, search |

The `/admin` URL carries Admin+Analyst+Reviewer rights (full authoring + review + publish); the
`/user` URL carries Viewer rights.

---

## 8. Feature Catalog — every feature

This is the complete list. Features marked **Admin** appear in the `/admin` experience; **User**
features appear in `/user`; **Platform** features apply to everyone / the whole system.

### 8.1 Admin features

**Ingestion & screenshots**
- Create a process with a **name** and one-line **instruction** describing the workflow.
- **Upload multiple screenshots** at once — PNG, JPG, JPEG, WEBP, GIF, or BMP. Every image is
  re-encoded to a Gemini-safe PNG server-side (max 15 MB each).
- **Drag-and-drop reorder** thumbnails in any direction; order defines the step sequence.
- **Enlarge** any thumbnail in a full-size lightbox (click to open, Esc / backdrop to close).
- **Remove** an individual screenshot (✕); remaining screenshots are renumbered automatically.
- Perceptual-hash (average-hash) computed per image for de-duplication and drift signals.

**AI generation**
- **Run the AI pipeline** — one click sends all screenshots + your instruction to the vision-LLM and
  returns a structured SOP.
- **Live progress** — an animated progress bar with staged status messages while the job runs (also
  available as a raw Server-Sent-Events stream).
- **Agent trace** — a table of which agent/model ran, latency, and status for the run.
- **Learned guidance** — accepted corrections and an approved exemplar are folded into the prompt so
  later generations improve automatically.

**Visual perception viewer**
- Center panel shows each screenshot with detected elements / OCR boxes.
- **Click a step → highlights the exact control** on its screenshot (auto-scrolls to it).
- Thumbnail strip to switch screens; **double-click a screen to enlarge** it.

**SOP editing & review** (every change creates a new immutable version)
- Inline **edit** a step's action & description.
- **Add** a step (optionally after a chosen step, optionally referencing a screenshot).
- **Delete** a step; steps renumber automatically.
- **Approve** a flagged step; **reject** a step with a reason; open a **review**; **sign off**.
- **Publish** — gated: any flagged step must be approved first, or publish is blocked (409).
- Per-step **confidence meter** and **needs-review / ok** badges.

**Refine & improve**
- **Refine with AI** — type a plain-English change ("add a logout step", "make descriptions more
  detailed") and regenerate a new version; the old one is kept in history.
- **Improvement inbox** — read every user suggestion on the open SOP (author, target step, status).
  - **Edit / curate** the wording of a suggestion before acting on it.
  - **Resolve**, **Dismiss**, or **Reopen** a suggestion.
  - **Generate improved version from open suggestions** — folds the curated suggestions into one
    instruction, regenerates a new version, and marks those suggestions resolved against it.

**UI drift check**
- Upload the **current** screenshots of a process; ProcessIQ compares them (perceptual-hash Hamming
  distance) to the ones the SOP was built from, reports which screens changed and which steps are
  likely affected, and offers a one-click **regenerate from the updated screenshots**.

**Versioning, export & chat**
- **Version history** — list every version (steps, confidence, state); **view** or **download** any
  past version.
- **Export / download** the SOP or any version in: **PDF, HTML, DOCX, Markdown, JSON, XML, BPMN, test
  cases, RPA skeleton**. PDF/HTML/DOCX embed each screenshot with the click-box drawn.
- **Chat about this SOP** — grounded Q&A assistant with per-SOP conversation history.
- 👍 / 👎 **rating** feedback on a SOP.

### 8.2 User features

- **Browse all SOPs** in the tenant (title, step count, confidence, state) and open any one.
- **Read the full SOP** — objective, prerequisites, numbered steps (action + description),
  exception handling, validation, output, and confidence — all read-only.
- **Version history** — see and open every version of a SOP.
- **Screenshots** — view the perception viewer; **click a step** to highlight its control;
  **double-click / click to enlarge** any screenshot in the lightbox.
- **Submit an improvement suggestion:**
  - **Per step** — a **💡 Suggest** button on each step opens an inline box targeting that step.
  - **Whole SOP** — a general suggestion box.
- **Track your suggestions** — a "Your suggestions" list shows each one's status (Open → Resolved /
  Dismissed) and, once applied, the version number it was folded into ("✓ Applied in v3").
- **Export / download** the SOP or a version (read consumption) in any supported format.
- **Chat about the SOP** — ask the grounded assistant questions.

> The authoring surfaces (upload, run pipeline, agent trace, step editing, publish, refine, drift,
> improvement inbox) are hidden **and** blocked server-side for the User role.

### 8.3 Platform features (shared)

- **Two role-scoped URLs** (`/admin`, `/user`) plus a default `/app`; role persists per browser.
- **Async job pipeline** with polling **and** an SSE progress stream (`/v1/stream/jobs/{id}`).
- **Durable storage** — in-memory for speed with atomic JSON snapshots (`data/store.json`); survives
  restarts. Images persisted in an on-disk object store.
- **Immutable versioning** — every edit/publish/refine snapshots a new version.
- **Confidence & flags** — per-step + overall confidence; flags for `LOW_CONFIDENCE`,
  `POSSIBLE_HALLUCINATION`, `MISSING_STEP`, `NEEDS_REVIEW`.
- **Knowledge search** — full-text search across published SOPs, plus a knowledge-base chat endpoint.
- **Integrations** — register webhooks (HMAC-signed payloads) and "publish-to" external targets.
- **Notifications** — streamed job progress events.
- **Security** — RBAC per action, tenant isolation, PII redaction, and prompt-injection sanitization
  of any text pulled from screenshots (treated as data, never as instructions).
- **Tamper-evident audit log** — every action is recorded in a SHA-256 hash-chained log with a
  verify-chain check; admins/auditors can read it.
- **Observability** — Prometheus metrics at `/metrics`; interactive API docs at `/docs`.
- **Hardware-agnostic inference** — one gateway, four profiles (mock / local-6gb / server-24gb /
  cloud), selectable by env var.

---

## 9. The Generated SOP — document format

Every SOP (on screen and in exports) follows this structure:

```
STANDARD OPERATING PROCEDURE (SOP)
Process: <name>

1. OBJECTIVE            — the purpose of the process
2. PRE-REQUISITES       — required credentials, permissions, input info
3. STEP-BY-STEP         — for each step: the action (naming the exact button/field),
                          the expected system response, and the associated screenshot
                          (rendered as paragraph → screenshot → next paragraph → …)
4. EXCEPTION HANDLING   — invalid login, missing fields, validation failures, system
                          errors — each with a suggested resolution
5. VALIDATION & CHECKS  — mandatory fields, correct formats, completion verification
6. OUTPUT               — the expected final result on success
7. CONFIDENCE SCORE     — overall confidence in the reconstructed workflow
```

---

## 10. API Reference

All endpoints are under `/v1`, require identity headers (`X-Tenant`, `X-User`, `X-Roles` — injected
automatically by the web UI), and are permission-gated. Full interactive docs: **`/docs`**.

**Processes & screenshots**
| Method & path | Purpose |
| --- | --- |
| `POST /v1/processes` | create a process |
| `POST /v1/processes/{id}/uploads:file` | upload a screenshot (multipart) |
| `POST /v1/processes/{id}/uploads` | register a screenshot by metadata (tests/pre-signed) |
| `GET /v1/processes/{id}` | get a process + its artifacts |
| `GET /v1/processes/{id}/artifacts/{aid}/image` | fetch the processed PNG |
| `POST /v1/processes/{id}/artifacts:reorder` | set a new screenshot order |
| `DELETE /v1/processes/{id}/artifacts/{aid}` | remove a screenshot + renumber |

**Jobs (AI pipeline)**
| Method & path | Purpose |
| --- | --- |
| `POST /v1/jobs` | run generation / refine (`options.refine_sop_id`, `instruction`, `async`) |
| `GET /v1/jobs/{id}` | job status |
| `GET /v1/jobs/{id}/progress` | progress events |
| `GET /v1/jobs/{id}/perception` | per-screen elements + text |
| `GET /v1/jobs/{id}/trace` | agent execution trace |
| `GET /v1/stream/jobs/{id}` | **SSE** live progress stream |

**SOPs, review & versions**
| Method & path | Purpose |
| --- | --- |
| `GET /v1/sops` · `GET /v1/sops/{id}` | list / read SOPs |
| `GET /v1/sops/{id}/versions` · `/versions/{v}` | list / read versions |
| `PATCH /v1/sops/{id}/steps/{no}` | edit a step (new version) |
| `POST /v1/sops/{id}/steps` · `DELETE …/steps/{no}` | add / delete a step |
| `POST /v1/sops/{id}/reviews` | open a review |
| `POST /v1/sops/{id}/steps/{no}:approve` · `:reject` | approve / reject a step |
| `POST /v1/sops/{id}:signoff` · `:publish` | sign off / publish |

**Improvement loop, drift, chat, export**
| Method & path | Purpose |
| --- | --- |
| `POST /v1/sops/{id}/suggestions` | submit an improvement suggestion (whole-SOP or per-step) |
| `GET /v1/sops/{id}/suggestions` | list suggestions (+ open count) |
| `PATCH /v1/sops/{id}/suggestions/{sid}` | curate: edit wording / resolve / dismiss (admin) |
| `POST /v1/sops/{id}/drift` | UI-drift compare vs a new process's screenshots |
| `GET /v1/sops/{id}/chat` · `POST …/chat` | grounded SOP chat |
| `GET /v1/sops/{id}/exports/formats` · `POST …/exports` | list formats / export a SOP or version |

**Feedback, search, integrations, admin, ops**
| Method & path | Purpose |
| --- | --- |
| `POST /v1/feedback` · `GET /v1/feedback` | rating/correction memory |
| `GET /v1/search` · `POST /v1/chat` | knowledge search / KB chat |
| `POST /v1/integrations` · `POST /v1/sops/{id}/publish-to/{target}` | webhooks / external publish |
| `POST /v1/tenants` · `GET|PUT /v1/policies` · `GET /v1/audit` | admin: tenants, policy, audit log |
| `GET /v1/health` · `GET /metrics` | health · Prometheus metrics |

---

## 11. Configuration Reference

All settings live in `.env` (copy from `.env.example`). The important ones:

| Variable                          | Default            | Meaning                                                             |
| --------------------------------- | ------------------ | ------------------------------------------------------------------- |
| `HOSTED_VLM_BASE_URL`             | Gemini endpoint    | OpenAI-compatible vision-LLM base URL                               |
| `HOSTED_VLM_API_KEY`              | _(empty)_          | **your** Gemini key — required for real SOPs                        |
| `HOSTED_MODEL`                    | `gemini-2.5-flash` | which hosted model to use                                           |
| `INFERENCE_MODE`                  | `hosted`           | `hosted` = use the API key; `mock` = fake output (no key)           |
| `MODEL_PROFILE`                   | `mock`             | hardware profile: `mock`/`local-6gb`/`server-24gb`/`cloud`          |
| `GROUND_BBOX`                     | `1`                | `1` = OCR-snap boxes (needs PaddleOCR); `0` = VLM boxes only (fast) |
| `WARMUP_OCR`                      | `1`                | preload OCR at boot so the first request never waits                |
| `OCR_DEVICE`                      | `cpu`              | `cpu` on Windows; `cuda` on a Linux GPU server                      |
| `OCR_DET_MODEL` / `OCR_REC_MODEL` | server models      | `PP-OCRv5_mobile_*` (fast) or `_server_*` (accurate)                |
| `CONFIDENCE_THRESHOLD`            | `0.75`             | steps below this are flagged for review                             |
| `DATA_DIR`                        | `data`             | where the JSON snapshot + object store live                        |

> In Docker, the compose file forces `MODEL_PROFILE=mock`, `GROUND_BBOX=0`, `WARMUP_OCR=0` (lean, no
> OCR) — your `.env` key is still used for generation.

---

## 12. Project Structure

```
processiq_shared/       Pydantic contracts: SOP schema, agent state, events, enums, security
apps/
  api/                  FastAPI control plane + web UI (static/) + store, audit, security_ctx
    routers/            processes · jobs · sops · review · improvements · drift · chat ·
                        exports · search · integrations · notifications · feedback · admin · health
  orchestrator/         the agent pipeline runners (run_pipeline / run_vlm_pipeline)
  inference_gateway/    unified model access: profiles, adapters, VRAM governor, cache
agents/                 vision, ocr, layout, reasoning, generation, validation, confidence
  sop_vlm.py            the real VLM SOP generator (Gemini) + OCR box grounding
services/               export (PDF/DOCX/…), preprocess, integration workers
frontend/               production Next.js app [scaffold]
infra/docker/           Dockerfile(s)
scripts/                demo + smoke utilities (omniparser_smoke, ocr_smoke)
tests/                  pytest suite (offline/mocked)
docker-compose.yml      one-command app run
docker-compose.infra.yml  optional Postgres/Mongo/Redis/… stack
requirements.txt        core app deps (no GPU/ML)
requirements-ai.txt     optional local model deps (torch, paddle, …)
.env.example            copy to .env and add your key
```

---

## 13. Hardware Profiles & Deployment

ProcessIQ runs the same code from a laptop to a GPU server, selected by `MODEL_PROFILE`:

| Profile       | Vision/SOP                    | OCR             | Where               |
| ------------- | ----------------------------- | --------------- | ------------------- |
| `mock`        | fake                          | none            | tests / Docker demo |
| `local-6gb`   | hosted Gemini                 | PaddleOCR (CPU) | 6 GB dev laptop     |
| `server-24gb` | self-hosted Qwen2.5-VL (vLLM) | PaddleOCR (GPU) | 24 GB Linux server  |
| `cloud`       | external pools                | external        | GA scale            |

On a GPU Linux server the OCR grounding runs ~10× faster than CPU — that's the recommended target for
accurate boxes at speed.

---

## 14. Security, Audit & Governance

- **RBAC per action** — every endpoint is gated by a permission (e.g. `sop:edit`, `sop:publish`,
  `feedback:manage`); roles map to permission sets. The UI only shows what your role can do, and the
  server rejects anything it can't (403).
- **Tenant isolation** — all data is scoped by `X-Tenant`; one tenant never sees another's SOPs.
- **PII redaction** — emails, auth tokens, card and phone numbers can be redacted from extracted text.
- **Prompt-injection defense** — text read from screenshots is sanitized and treated strictly as
  data; embedded "ignore previous instructions"-style content is neutralized.
- **Tamper-evident audit** — every meaningful action (create, upload, edit, approve, publish,
  suggest, curate, export…) is appended to a **SHA-256 hash-chained** log with a `verify_chain()`
  integrity check. Readable by Admin/Auditor via `GET /v1/audit`.
- **Secrets** — the Gemini key lives only in `.env` (git-ignored); it is never logged or committed.

---

## 15. Testing

```bash
pip install -r requirements.txt
pytest -q          # offline/mocked — never uses your API key
ruff check .       # lint
```

The suite covers security (PII/injection), RBAC, the review/publish gate, all export formats,
webhooks, search, the audit chain, the eval harness, UI-drift detection, multi-format upload +
reorder/delete, and the role-based improvement-suggestion loop.

> Note: the DOCX export test needs `python-docx` (in `requirements.txt`) — install it if you see a
> `No module named 'docx'` skip/failure.

---

## 16. Troubleshooting

| Symptom                                | Fix                                                                                                                 |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| SOP says "mock" / generic text         | Your Gemini key isn't set. Check `HOSTED_VLM_API_KEY` in `.env` and `INFERENCE_MODE=hosted`.                        |
| Chat replies "needs a hosted model"    | Same cause — set the Gemini key and `INFERENCE_MODE=hosted`.                                                        |
| `http://localhost:8000/app` won't load | The server isn't running, or port 8000 is busy. Check the terminal for errors; try another port with `--port 8001`. |
| Docker: "port is already allocated"    | Something else uses 8000. Stop it, or change the port mapping in `docker-compose.yml` to `"8001:8000"`.             |
| First run is slow                      | Docker builds the image once; Python's OCR (if enabled) downloads models once. Later runs are fast.                 |
| Boxes are a bit off                    | You're using VLM-only boxes. Enable OCR grounding (`GROUND_BBOX=1` + PaddleOCR) for pixel-perfect boxes.            |
| "Rate limit" from Gemini               | Free tier is ~20/day. Wait, or use a different key. Re-running the same screenshots is cached.                      |

---

## 17. Status & Roadmap

**Working today:** real Gemini-powered SOP generation from screenshots + instruction; grounded
click-boxes (OCR); the full 7-section SOP document format; embedded-screenshot exports across nine
formats (PDF/HTML/DOCX/Markdown/JSON/XML/BPMN/test-cases/RPA); per-step + overall confidence with
flags; review/approve/reject/sign-off/publish gate; immutable versioning with history +
per-version download; AI refine-from-changes; the learned-guidance feedback loop; **role-based access
(Admin/User) with the improvement-suggestion loop** (per-step + whole-SOP suggestions, admin
curation, regenerate-improved-version); UI-drift detection; grounded SOP chat; knowledge search;
webhooks/integrations; SSE progress; PII redaction + prompt-injection defense; a hash-chained audit
log; durable JSON persistence; a professional web UI; Docker one-command run; and a CI-clean pytest
suite.

**Next:** production datastores (Postgres/Mongo/Redis/Qdrant/Neo4j/MinIO per design §9); SSO/OIDC in
place of header-based identity; the production Next.js frontend; and richer analytics.

See [`docs/gap-analysis.md`](docs/gap-analysis.md) for target-vs-built detail and
[`../processiq-design/`](../processiq-design) for the full design.

---

<div align="center">
<sub>ProcessIQ — See it. Understand it. Document it. Improve it. — all with agentic AI.</sub>
</div>
