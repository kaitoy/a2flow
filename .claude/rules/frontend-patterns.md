---
paths:
  - "frontend/**/*.{ts,tsx}"
---

# Frontend Implementation Patterns

Conventions for organizing and testing the Next.js frontend. Paths below are relative to `frontend/`.

## Project structure

```
scripts/
└── download-a2ui-schema.mjs   # Downloads basic_catalog.json at build time (predev/prebuild)
src/
├── app/
│   ├── layout.tsx        # Root layout — wraps tree in StoreProvider
│   ├── page.tsx          # Entry point
│   └── globals.css       # Tailwind directives
├── components/
│   ├── Chat.tsx          # Top-level chat screen
│   ├── MessageList.tsx   # Scrollable message history
│   ├── MessageBubble.tsx # Individual message bubble (text or A2UI)
│   ├── A2uiRenderer.tsx  # A2UI surface renderer
│   └── ChatInput.tsx     # Textarea with Enter-to-send
├── generated/
│   └── basic_catalog.json     # Downloaded at build time (gitignored)
├── hooks/
│   └── useChat.ts        # Session init + SSE streaming logic
├── store/
│   ├── chatSlice.ts      # Redux slice (messages, session, streaming state)
│   ├── index.ts          # Store configuration
│   ├── hooks.ts          # Typed useAppDispatch / useAppSelector
│   └── provider.tsx      # Client-side Redux Provider
└── lib/
    ├── api.ts            # listSessions(), createChatAgent() with A2UIMiddleware; withCredentials + X-CSRF-Token via axios interceptor; 401 → /login
    └── logger.ts         # pino logger instance
```

## Testing

Unit tests are implemented with [Vitest](https://vitest.dev/), [Testing Library](https://testing-library.com/), and [MSW](https://mswjs.io/).

### Test structure

| Tool | Purpose |
|---|---|
| Vitest | Test runner |
| @testing-library/react | Rendering and assertions for components and hooks |
| @testing-library/user-event | User interaction simulation |
| MSW (Mock Service Worker) | Backend API mocking |

Test files live next to the source files they cover, named `*.test.ts(x)`.

New UI components must ship with a co-located `*.test.tsx` in the same change — not just when modifying existing markup (see root `CLAUDE.md` "Keeping tests in sync" for the modification-time rule).

Shared test infrastructure (custom renderer, MSW server, mocks) lives under `src/test/`:

```
src/test/
├── setup.ts           # Global setup (MSW server, jest-dom matchers)
├── test-utils.tsx     # Custom render wrapped in Redux Provider
├── mocks/
│   ├── next-navigation.ts  # Stub for next/navigation
│   └── next-font.ts        # Stub for next/font/google
└── msw/
    ├── handlers.ts    # MSW request handlers for the backend API
    └── server.ts      # MSW server instance
```

### Mocking strategy

- **Backend REST API** — intercepted via MSW
- **Agent streaming** (`/agent` endpoint) — `HttpAgent` from `@ag-ui/client` is mocked at the module level (SSE streaming is not practical to simulate with MSW in jsdom)
- **`next/navigation`** — replaced with a stub via `resolve.alias` in `vitest.config.ts`
- **`@a2ui/react` / `@a2ui/web_core`** — mocked per test file with `vi.mock()` at the `A2uiRenderer` boundary to avoid the complex dependency chain
