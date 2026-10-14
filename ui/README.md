# Maestarr web UI

React 19 + TypeScript + Vite, styled with Tailwind v4 (CSS-first, no
`tailwind.config.js`). The production build goes into `../maestarr/web` and is
served by the Python app — nothing runs on Node in production.

```sh
npm install
npm run dev      # http://127.0.0.1:5173 — /api, /mcp and /health proxy to :8709
npm run verify   # lint + typecheck + unit tests
npm run build    # → ../maestarr/web
```

Run the backend next to it with `maestarr serve` from the repository root.

- `src/pages/` — Setup (onboarding), Login, Home, Chat, Discover, Settings
- `src/lib/services.ts` — one definition per integration; drives both the
  onboarding wizard and Settings
- `src/components/chat/` — message rendering, approval cards, release verdicts
- The chat speaks the Vercel AI SDK v6 UI message stream (`@ai-sdk/react`).
