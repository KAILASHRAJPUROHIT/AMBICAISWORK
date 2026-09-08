# vinext-starter

A clean full-stack starter running on
[vinext](https://github.com/cloudflare/vinext), with optional Cloudflare D1 and
Drizzle support.

## Prerequisites

- Node.js `>=22.13.0`

## Quick Start

```bash
npm install
npm run dev
npm run build
```

This starter does not use `wrangler.jsonc`.

## Included Shape

- edit site code under `app/`
- `.openai/hosting.json` declares optional Sites D1 and R2 bindings
- `vite.config.ts` simulates declared bindings for local development
- `db/schema.ts` starts intentionally empty
- `examples/d1/` contains an optional D1 example surface
- `drizzle.config.ts` supports local migration generation when needed

## Workspace Auth Headers

Signed-in visitors receive both `oai-authenticated-user-id` and `oai-authenticated-user-email`. Private Sites require every visitor to sign in; public Sites may also have anonymous visitors, for whom neither header is present.

The user ID is stable for the same user on the same Site and different across Sites. Email and name are intended for display or contact purposes.

SIWC-authenticated workspace sites may also receive
`oai-authenticated-user-full-name` when the user's SIWC profile has a non-empty
`name` claim. The full-name value is percent-encoded UTF-8 and is accompanied by
`oai-authenticated-user-full-name-encoding: percent-encoded-utf-8`.

Treat the full name as optional and fall back to email when it is absent:

```tsx
import { headers } from "next/headers";

export default async function Home() {
  const requestHeaders = await headers();
  const userId = requestHeaders.get("oai-authenticated-user-id");
  const email = requestHeaders.get("oai-authenticated-user-email");
  const encodedFullName = requestHeaders.get("oai-authenticated-user-full-name");
  const fullName =
    encodedFullName &&
    requestHeaders.get("oai-authenticated-user-full-name-encoding") ===
      "percent-encoded-utf-8"
      ? decodeURIComponent(encodedFullName)
      : null;

  const displayName = fullName ?? email;
  // ...
}
```

## Optional Dispatch-Owned ChatGPT Sign-In

Import the ready-to-use helpers from `app/chatgpt-auth.ts` when the site needs
optional or required ChatGPT sign-in:

- Use `getChatGPTUser()` for optional signed-in UI.
- Use `requireChatGPTUser(returnTo)` for server-rendered pages that should send
  anonymous visitors through Sign in with ChatGPT.
- Use `chatGPTSignInPath(returnTo)` and `chatGPTSignOutPath(returnTo)` for
  browser links or actions.
- Pass a same-origin relative `returnTo` path for the destination after sign-in
  or sign-out. The helper validates and safely encodes it.
- Mark protected pages with `export const dynamic = "force-dynamic"` because
  they depend on per-request identity headers.

Dispatch owns `/signin-with-chatgpt`, `/signout-with-chatgpt`, `/callback`, the
OAuth cookies, and identity header injection. Do not implement app routes for
those reserved paths. Routes that do not import and call the helper remain
anonymous-compatible.

SIWC establishes identity only; it does not prove workspace membership. Use the
Sites hosting platform's access policy controls for workspace-wide restrictions,
or enforce explicit server-side membership or allowlist checks.

Use SIWC for account pages, user-specific dashboards, saved records, and write
actions tied to the current ChatGPT user. Leave public content anonymous.

## Local Project/Repo Scanner

The supervisor chat (`app/api/supervisor/chat/route.ts`) can ground its answers
in a real, live index of the projects and Git repositories on this machine.
This is a separate, plain Node.js process (`scripts/scan-repos.mjs`) — the
Worker/`vinext dev` sandbox has no filesystem access, even locally, so a
companion process with real `fs` access is required, the same way a local
Ollama runtime is queried over `http://127.0.0.1:11434`.

Run it in its own terminal, alongside `npm run dev` and Ollama:

```bash
npm run scan
```

It walks every fixed drive by default (configurable via `PROJECT_SCAN_*` in
`.env`, see `.env.example`), skipping `node_modules`, `.git` internals,
`Windows`, `Program Files`, `AppData` and similar noise, and serves a
read-only JSON index on `http://127.0.0.1:8787`:

- `GET /health` — quick status (scanning now? how many repos/projects? how
  many are being live-watched? how many recent change events buffered?)
- `GET /index.json` — full index: path, git branch, remote, dirty status,
  last commit, and the first ~500 characters of each project's README
- `GET /changes.json?limit=100` — a rolling feed of real-time file
  add/change/delete events from the live watcher, most recent first
- `GET /blame?path=<absolute file path>` — the last commit's author, email,
  date and message for a file, if it's inside an indexed Git repo
- `POST /refresh` — trigger an immediate re-scan

**Live change tracking:** after each scan, the most recently active repos
and projects (capped by `PROJECT_WATCH_MAX_ROOTS`, default 200 — each
watched folder holds an OS watch handle) get a recursive `fs.watch` so file
adds/edits/deletes are captured as they happen, not just at the next scan.
This only watches folders the scanner already found — it is not a whole-disk
watcher. "Who" changed a file only resolves for Git-tracked files with
commit history (via `/blame`, or Qwen asking for it); uncommitted working-tree
edits have no author attribution beyond "this machine's user account" — Node
can't attribute writes to a specific process or user, only the OS's own
security auditing can, which this does not enable. Windows only reliably
supports `{recursive: true}` `fs.watch` on Windows and macOS; on Linux the
watcher is skipped with a warning (each project would need its own
non-recursive watcher, which isn't implemented here).

**What it does and does not do:**
- It only reads directory names, `git` command output, and a short README
  excerpt per project — it never reads or transmits arbitrary file contents.
- The index is cached to `.local/repo-index.json` (gitignored — it contains
  full local disk paths) so a restart doesn't require an immediate re-scan.
- A full-disk first scan can take a while; it re-scans automatically every
  `PROJECT_SCAN_RESCAN_MINUTES` (default 180) and stops early after
  `PROJECT_SCAN_MAX_MINUTES` (default 30), flagging the index as truncated
  rather than blocking indefinitely.
- The chat route fetches this index fresh on every message and folds a
  summary (most recently active repos first) into Qwen's system prompt, so
  it can be asked things like "what repos exist on this PC" or "what's the
  Aradhana dashboard project about" grounded in real data instead of
  refusing outright.
- The dashboard sidebar shows scanner status ("Project index: N repos") next
  to supervisor status.

## Useful Commands

- `npm run dev`: start local development
- `npm run scan`: start the local project/repo scanner companion process
- `npm run build`: verify the vinext build output
- `npm test`: build the starter and verify its rendered loading skeleton
- `npm run db:generate`: generate Drizzle migrations after schema changes

## Learn More

- [vinext Documentation](https://github.com/cloudflare/vinext)
- [Drizzle D1 Guide](https://orm.drizzle.team/docs/get-started/d1-new)
