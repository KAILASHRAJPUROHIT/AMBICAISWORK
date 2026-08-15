# First-time setup on a new PC

This tool is now fully portable — no hardcoded paths tied to any specific
Windows username. Everything below is a one-time step per PC; after that,
just double-click `LAUNCH_CATALOG_UI.bat`.

## Prerequisites (install once, if not already present)

1. **Python 3.11** — https://www.python.org/downloads/ (check "Add to PATH",
   or make sure the `py` launcher is installed, which the Python installer
   does by default).
2. **Google Chrome** — must be at the standard install location
   (`C:\Program Files\Google\Chrome\...` or the per-user AppData location).
3. **Node.js** — https://nodejs.org/ (only needed for the Codex engine login
   below, via `npx`).

## One-time setup steps

1. Unzip this folder anywhere (Desktop, D:\, wherever).
2. Copy `keys.py.example` to `keys.py` and fill in a real Gemini API key
   (free tier is fine — get one at https://aistudio.google.com/app/apikey).
3. Open a terminal in this folder and run:
   ```
   npx @openai/codex login
   ```
   This opens a browser OAuth flow for your ChatGPT Plus account and saves
   a token to `~/.codex/auth.json` — this is what the Codex engine uses,
   completely separate from the Chrome-based engines below.
4. Double-click `FIRST_TIME_LOGIN.bat`. It opens 3 visible Chrome windows
   (ChatGPT, Gemini, Copilot) — log into each with the account you want
   this tool to use, then just close the windows. No need to log out later;
   the login persists in that Chrome profile for every future run.
5. From now on, just double-click `LAUNCH_CATALOG_UI.bat`. It installs any
   missing Python dependencies automatically on first run, opens the 3
   Chrome engine sessions off-screen (already logged in from step 4), starts
   the server, and opens the tool in your browser.

## What's already included, no setup needed

- The model library (`models/`) and studio backgrounds (`backgrounds/`) —
  ready to use immediately.
- The Aradhana logo (`assets/logo.png`) for watermarking.

## What can't be pre-packaged (and why)

Every credential above is tied to a specific logged-in account — there is
no way to "package" a working login for someone else's PC, by design (these
are real user sessions, not shareable API keys). This is unavoidable: a
fresh PC always needs its own one-time login per engine, same as installing
any app that requires signing in.

## Verifying it worked

Once running, visit `http://127.0.0.1:7654/api/health` — every engine
should show `"ok": true`. If Copilot shows signed out, re-run
`FIRST_TIME_LOGIN.bat` for just that one.
