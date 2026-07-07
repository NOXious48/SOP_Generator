# ProcessIQ Frontend (owner: Ayush)

Next.js + TypeScript + Tailwind + shadcn/ui. Implements the ProcessIQ web app (design Section 11).

## Scaffold this app
```bash
# from repo root
npx create-next-app@latest frontend --ts --tailwind --eslint --app --src-dir --use-npm
cd frontend
npx shadcn@latest init
npm i @tanstack/react-query zustand konva react-konva @tiptap/react @tiptap/starter-kit recharts msw
```

## Pages to build (design §11.2–11.3)
- `/` Dashboard (KPI cards, recent projects, AI insights)
- `/upload` Upload Center (multi-source, drag-drop, streaming progress)
- `/projects/[id]` Process detail + SOP Editor (3-pane: flow / screenshot canvas / AI + editor)
- `/sops`, `/knowledge`, `/analytics`, `/integrations`, `/team`, `/audit`, `/settings`

## Talk to the API
Base URL `http://localhost:8000`. Start against MSW mocks, then switch to real endpoints
(design §10). Health check: `GET /v1/health`.
