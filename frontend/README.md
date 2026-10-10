# Instagram Downloader — Frontend (Next.js 15 + shadcn-style)

Local web UI to drive the FastAPI backend, browse downloaded media, and
manage jobs.

## Stack

- Next.js 15 (App Router, TypeScript)
- React 19
- TanStack Query (data fetching + cache)
- Tailwind CSS (dark "Midnight" theme — pink accent)
- shadcn-style components (locally written, no CLI needed)
- WebSocket for live job logs
- Axios for HTTP

## Quick start

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api/*` and `/ws/*` to `http://localhost:8000`
(see `next.config.js`). Make sure the backend is running first.

## Pages

| Route | Purpose |
|---|---|
| `/` | Dashboard — stats, quick actions |
| `/accounts` | List + search accounts |
| `/accounts/[id]` | Account detail, rescan, gallery |
| `/media` | Browse all indexed media (filter by type, search) |
| `/jobs` | Job history with status filter |
| `/jobs/[id]` | Live log stream + stop/delete controls |
| `/settings` | Cookie upload, view storage / rate limit settings |

## Build for production

```bash
npm run build
npm run start
```

Outputs a standalone server (no Node.js needed at runtime if you also
import the `next` runtime).

## Customising the theme

- Colors: `tailwind.config.ts` (`primary`, `accent`, `success`, etc.)
- Fonts: `app/layout.tsx` (currently Inter + JetBrains Mono)
- Components: `components/ui/*`
