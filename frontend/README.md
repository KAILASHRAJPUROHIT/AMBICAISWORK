# AMBIC Payment Auditor Frontend

Vite/React/TypeScript interface served by `backend.review_api` from `frontend/dist`.

```powershell
npm install
npm run dev     # frontend development only
npm run lint
npm run build   # required before the FastAPI server can serve the SPA
```

## Current integration constraints

- API calls use the current origin in most screens, but several inherited screens still hardcode `http://127.0.0.1:8000`.
- Auth state uses `session_token`; the dashboard also reads the obsolete `aradhana_session_token` key. These must be unified.
- The frontend does not send `X-Business-Slug` or derive a tenant from the hostname. It works only when exactly one business is registered.
- Reports, escalation, and audit-log screens are not launch proof: some call mock/disconnected backend paths or render an empty state.

Do not present those screens as production SaaS functionality until the corresponding launch gates in `../LAUNCH_READINESS_AUDIT.md` are complete.
