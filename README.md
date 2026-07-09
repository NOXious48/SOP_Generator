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
7. [Using the App](#7-using-the-app)
8. [Configuration Reference](#8-configuration-reference)
9. [Project Structure](#9-project-structure)
10. [Hardware Profiles & Deployment](#10-hardware-profiles--deployment)
11. [Testing](#11-testing)
12. [Troubleshooting](#12-troubleshooting)
13. [Status & Roadmap](#13-status--roadmap)

---

## 1. Introduction

Every company runs on **Standard Operating Procedures (SOPs)** — the step-by-step guides that explain
how to do a task in an internal tool ("how to add a new employee", "how to create an order"). Today
these are written by hand: someone screenshots each screen, pastes them into a document, and types
"click the Save button." It's slow, and the moment the software changes, the document is wrong.

**ProcessIQ automates this.** You upload the screenshots of a workflow, describe the process in one
line, and ProcessIQ produces a complete, professional SOP: an objective, prerequisites, numbered
steps, each step showing the exact screenshot **with a box drawn on the button to click**, plus
confidence scores and a human review/approval flow.

It is **not an OCR tool.** OCR (reading text) is only one small part. The core is **visual process
intelligence** — understanding the _workflow_ across a sequence of screens, the way a human business
analyst would.

> Full design set: [`../processiq-design/`](../processiq-design) (Sections 00–22).

---

## 2. What ProcessIQ Does

- 📤 **Ingests visuals** — upload one or many screenshots (PNG/JPG) of a workflow, in order.
- 👁️ **Sees the UI** — detects text, buttons, form fields, menus, and layout.
- 🧠 **Understands the workflow** — infers the sequence of actions, transitions, and business intent.
- 📝 **Generates a structured SOP** — title, objective, prerequisites, numbered steps, exceptions,
  validations, and expected outcomes.
- 🎯 **Grounds every step to evidence** — each step points at the exact screenshot region / control,
  drawn as a box on the image.
- 📊 **Scores confidence** — per-step and overall; low-confidence steps are flagged for review.
- ✅ **Human-in-the-loop** — review, approve, and publish; nothing is "final" until a human signs off.
- 📎 **Exports anywhere** — PDF, HTML, Markdown, DOCX, JSON, BPMN, test cases, RPA skeletons.

---

## 3. How It Works

```
  You upload screenshots + a one-line description of the process
                          │
                          ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 1  INGEST     validate · preprocess · store each image     │
   │ 2  UNDERSTAND a vision-LLM reads all screenshots at once,   │
   │              infers the steps, and picks the control to     │
   │              click on each screen                           │
   │ 3  GROUND     (optional) OCR snaps each step's box onto the │
   │              exact button/label on the screenshot           │
   │ 4  ASSEMBLE   structured SOP + per-step confidence + flags   │
   │ 5  REVIEW     you edit / approve / publish                  │
   │ 6  EXPORT     PDF · HTML · DOCX · Markdown · BPMN · …        │
   └──────────────────────────────────────────────────────────┘
                          │
                          ▼
        A professional SOP with screenshots + click-boxes
```

**Key design idea:** instead of dumping raw pixels into one giant prompt, ProcessIQ sends all
screenshots + your instruction to a vision model in **a single call**, gets back a structured SOP,
then (optionally) uses OCR to pin each step's box onto the exact control. This is cheaper, more
accurate, auditable, and works on the free tier of a hosted model.

---

## 4. Architecture

ProcessIQ is split into a fast **control plane** (the API + web UI you interact with) and an
**AI pipeline** of specialized agents. Everything is contract-first (typed Pydantic models), so
each piece is swappable.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         WEB UI  (/app)                                │
│      upload · live progress · screenshot overlays · SOP editor        │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  REST + async jobs
┌───────────────────────────────▼─────────────────────────────────────┐
│                 CONTROL PLANE  (FastAPI modular monolith)             │
│   processes · jobs · sops · review · search · exports · admin · health│
└───────────────────────────────┬─────────────────────────────────────┘
                                 │  runs a job
┌───────────────────────────────▼─────────────────────────────────────┐
│                        AI PIPELINE  (agents)                          │
│   VLM SOP generation  ──►  validation  ──►  confidence                │
│   (perception agents: vision / OCR / layout available for local GPU)  │
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

---

## 5. Technology Stack

| Area                        | Technology                                                | Why                                                            |
| --------------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| API / backend               | **FastAPI** (Python 3.12)                                 | async, fast, shares typed models with the AI plane             |
| Contracts                   | **Pydantic v2**                                           | one typed source of truth across API + agents                  |
| Vision-LLM (SOP generation) | **Google Gemini** (`gemini-2.5-flash`), OpenAI-compatible | free tier, strong UI/document understanding                    |
| OCR (box grounding)         | **PaddleOCR** (PP-OCRv5)                                  | accurate text + boxes; mobile (fast) / server (precise) models |
| UI element detection        | **OmniParser v2** (local GPU option)                      | screenshot-purpose element detection                           |
| Model serving               | **Inference Gateway** + hardware profiles                 | swap models by env var; agents stay hardware-agnostic          |
| Web UI                      | **HTML + Tailwind (CDN)** served by the API               | zero build step; professional light theme                      |
| Exports                     | **reportlab** (PDF), **python-docx** (DOCX), Jinja        | multi-format SOP rendering with embedded screenshots           |
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
3. Open `.env` in any text editor and set these two lines (paste your key):
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
3. Open your browser to **http://localhost:8000/app**
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
5. Open **http://localhost:8000/app**
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

## 7. Using the App

Open **http://localhost:8000/app** and:

1. **Describe & Upload** — type a **process name** and a one-line **instruction** (e.g. _"Log in to
   OrangeHRM, open Recruitment, and add a new candidate."_), then **drag-drop your screenshots in
   order**.
2. **Run AI pipeline** — click Run. A progress bar shows the stages; a SOP appears in ~15–90s
   depending on settings.
3. **Review** — the center panel shows each screenshot with detected elements / OCR boxes; **click a
   step** to highlight the exact control on its screenshot. The right panel shows the SOP with
   per-step confidence.
4. **Approve & Publish** — approve flagged steps, then Publish.
5. **Export** — choose a format (PDF/HTML/DOCX/Markdown/BPMN/…) and download. PDF/HTML embed each
   screenshot with the click-box drawn.

---

## 8. Configuration Reference

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

> In Docker, the compose file forces `MODEL_PROFILE=mock`, `GROUND_BBOX=0`, `WARMUP_OCR=0` (lean, no
> OCR) — your `.env` key is still used for generation.

---

## 9. Project Structure

```
processiq_shared/       Pydantic contracts: SOP schema, agent state, events, enums
apps/
  api/                  FastAPI control plane + web UI (static/)
  orchestrator/         the agent pipeline runners (run_pipeline / run_vlm_pipeline)
  inference_gateway/    unified model access: profiles, adapters, VRAM governor, cache
agents/                 vision, ocr, layout, reasoning, generation, validation, confidence
  sop_vlm.py            the real VLM SOP generator (Gemini) + OCR box grounding
services/               export (PDF/DOCX/…), preprocess, integration workers
frontend/               production Next.js app [scaffold — see Path B]
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

## 10. Hardware Profiles & Deployment

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

## 11. Testing

```bash
pip install -r requirements.txt
pytest -q          # ~40 tests, fully offline/mocked — never uses your API key
ruff check .       # lint
```

---

## 12. Troubleshooting

| Symptom                                | Fix                                                                                                                 |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| SOP says "mock" / generic text         | Your Gemini key isn't set. Check `HOSTED_VLM_API_KEY` in `.env` and `INFERENCE_MODE=hosted`.                        |
| `http://localhost:8000/app` won't load | The server isn't running, or port 8000 is busy. Check the terminal for errors; try another port with `--port 8001`. |
| Docker: "port is already allocated"    | Something else uses 8000. Stop it, or change the port mapping in `docker-compose.yml` to `"8001:8000"`.             |
| First run is slow                      | Docker builds the image once; Python's OCR (if enabled) downloads models once. Later runs are fast.                 |
| Boxes are a bit off                    | You're using VLM-only boxes. Enable OCR grounding (`GROUND_BBOX=1` + PaddleOCR) for pixel-perfect boxes.            |
| "Rate limit" from Gemini               | Free tier is ~20/day. Wait, or use a different key. Re-running the same screenshots is cached.                      |

---

## 13. Status & Roadmap

**Working today:** real Gemini-powered SOP generation from screenshots + instruction; grounded
click-boxes (OCR); embedded-screenshot exports (PDF/HTML/DOCX/…); confidence + review/publish; a
professional web UI; Docker one-command run; ~40 tests, CI-clean.

**Next:** persistent storage (currently in-memory), feedback-learning loop, rich correction editor,
UI-drift detection, and the production Next.js frontend.

See [`docs/gap-analysis.md`](docs/gap-analysis.md) for target-vs-built detail and
[`../processiq-design/`](../processiq-design) for the full design.

---

<div align="center">
<sub>ProcessIQ — See it. Understand it. Document it. Improve it. — all with agentic AI.</sub>
</div>
