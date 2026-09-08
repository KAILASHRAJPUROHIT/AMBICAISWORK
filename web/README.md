# Headwind MDM — Modern Admin UI (scaffold)

A minimal React + Vite + TypeScript admin frontend that proves the pipe to the
existing Headwind MDM Java server REST API. It currently ships a **login screen**
and a **device list view** — the seed of a future modern admin UI.

The legacy admin is an AngularJS app served by the Java server. This project does
not replace it; it talks to the same REST API.

## Stack

- React 18 + TypeScript
- Vite 5 (dev server + build)
- react-router v6 (protected route + auth context)
- `spark-md5` for the legacy MD5 password hashing (see security note below)
- Hand-written CSS (no component library)

## Run

```bash
cd web
cp .env.example .env        # optional; defaults work with the dev proxy
npm install
npm run dev                 # http://localhost:5173
```

Build for production:

```bash
npm run build               # type-checks then emits to dist/
npm run preview             # serve the production build locally
```

## Dev proxy & how it talks to the server

Authentication is **session-cookie based** (the server stores the user in the
`HttpSession` and the browser gets a `JSESSIONID` cookie). To make that work from
the Vite dev server without CORS headaches, `vite.config.ts` proxies everything
under `/rest` to the running Java server:

```
/rest/**  ->  http://localhost:8080/rest/**   (cookies forwarded)
```

So you need the Headwind server running locally on `:8080` (its default). Change
the target with the `VITE_DEV_PROXY_TARGET` env var if it runs elsewhere.

All API calls are sent with `credentials: 'include'` so the session cookie rides
along.

## Environment variables

| Variable                 | Default                 | Used by        | Purpose                                                                 |
| ------------------------ | ----------------------- | -------------- | ----------------------------------------------------------------------- |
| `VITE_API_BASE`          | `/rest`                 | app (runtime)  | URL prefix for API calls. Keep `/rest` to use the proxy / same origin. Set to an absolute URL to hit a remote server (requires server CORS). |
| `VITE_DEV_PROXY_TARGET`  | `http://localhost:8080` | `vite.config`  | Where the dev proxy forwards `/rest`.                                   |

See `.env.example`.

## Server endpoints targeted

All paths are relative to `VITE_API_BASE` (default `/rest`).

| Action          | Method & path                  | Server source                                                        |
| --------------- | ------------------------------ | ------------------------------------------------------------------- |
| Login options   | `GET  /public/auth/options`    | `AuthResource#options`                                              |
| Login           | `POST /public/auth/login`      | `AuthResource#login` — body `{ login, password }`                  |
| Logout          | `POST /public/auth/logout`     | `AuthResource#logout`                                              |
| Device search   | `POST /private/devices/search` | `DeviceResource#getAllDevices` — body `DeviceSearchRequest`        |

Response envelope (every endpoint): `{ status, message, data }` where `status`
is `"OK"` on success — see `com.hmdm.rest.json.Response`.

Device search `data` is a `DeviceListView`:
`{ configurations: { [id]: ... }, devices: { items: DeviceView[], totalItemsCount } }`.

## Security note (MD5 password hashing) — TODO

The legacy AngularJS client hashes the password with **MD5 (hex, upper-cased)**
before sending it (`login.controller.js`), and the server re-hashes to compare.
This scaffold replicates that scheme in `src/api/auth.ts` purely to stay
wire-compatible with the unmodified server.

**MD5 is cryptographically broken** and a client-side MD5 is effectively a
password-equivalent token in transit. The server also supports an optional RSA
"transmit.password" mode (advertised via `/public/auth/options` → `publicKey`);
this scaffold does **not** yet implement that path. A future hardening pass
should prefer RSA and/or move to a proper token-based auth flow.

## Project layout

```
web/
├── index.html
├── vite.config.ts          # dev proxy: /rest -> :8080
├── package.json
├── tsconfig*.json
├── .env.example
└── src/
    ├── main.tsx            # React entry
    ├── App.tsx             # router + providers
    ├── styles.css
    ├── api/
    │   ├── client.ts       # fetch wrapper + Response envelope handling
    │   ├── auth.ts         # login / logout / options (MD5 hashing)
    │   └── devices.ts      # device search
    ├── auth/
    │   ├── AuthContext.tsx # auth state + persistence hint
    │   └── ProtectedRoute.tsx
    └── pages/
        ├── LoginPage.tsx
        └── DevicesPage.tsx
```
