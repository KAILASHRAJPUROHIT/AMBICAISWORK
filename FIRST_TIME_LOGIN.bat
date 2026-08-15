@echo off
REM ====== One-time setup: log into the 3 engine accounts on a NEW PC ======
REM Run this ONCE after unzipping on a new machine, before using
REM LAUNCH_CATALOG_UI.bat. It opens the same 3 Chrome profiles the tool
REM uses day-to-day, but VISIBLE (the normal launcher opens them off-screen,
REM which only works once you're already logged in). Log into each service,
REM then just close the windows — the login persists in that Chrome profile
REM for every future run of LAUNCH_CATALOG_UI.bat, on this PC, indefinitely.
cd /d "%~dp0"

echo ================================================================
echo  FIRST-TIME SETUP — log into 3 accounts, one browser window each
echo ================================================================
echo.
echo Opening ChatGPT, Gemini, and Copilot in separate Chrome windows.
echo Log into each with the account you want this tool to use, then
echo just CLOSE the window (no need to log out). Do this once per PC.
echo.
pause

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --user-data-dir="%LOCALAPPDATA%\AutoCatalogueChrome" ^
    --no-first-run --no-default-browser-check ^
    https://chatgpt.com

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9223 ^
    --user-data-dir="%LOCALAPPDATA%\GeminiCatalogChrome" ^
    --no-first-run --no-default-browser-check ^
    https://gemini.google.com/app

start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9224 ^
    --user-data-dir="%LOCALAPPDATA%\CopilotCatalogChrome" ^
    --no-first-run --no-default-browser-check ^
    https://copilot.microsoft.com

echo.
echo Three Chrome windows should now be open. Log into each, then close them.
echo.
echo ================================================================
echo  Also needed (one-time, do these manually — see FIRST_RUN_SETUP.md):
echo    1. Copy keys.py.example to keys.py and fill in your Gemini API key
echo    2. Run:  npx @openai/codex login   (needs Node.js installed)
echo ================================================================
echo.
pause
