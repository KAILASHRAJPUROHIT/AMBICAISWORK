# Leaderboard collector

Runs on the shop server (SERVER2K22). Every 30 seconds it reads today's sales per salesperson from the Ornate SQL Server
database (read-only login) and pushes them to the MDM server, which shows them as the "Today's sales" card on the kiosk
tablets. The shop LAN is not reachable from AWS, so push is the only workable direction.

- Data model and the verified query: `C:\AradhanaSystems\projects\LEADERBOARD-HANDOVER.md` (section 2 and 3; do not re-derive).
- MDM endpoint: `POST /rest/public/collector/v1/leaderboard`, header `X-Collector-Token`
  (server env `MDM_COLLECTOR_TOKEN`).
- Ranking: total amount, descending (change the `ORDER BY` in `SQL` to rank by bill count).

## Install (once, on the Dell, elevated PowerShell)

    powershell -ExecutionPolicy Bypass -File install-collector.ps1

Rotates the SQL login password (generated on the Dell, never displayed), stores settings in the machine environment,
proves one push, and registers the `AradhanaLeaderboardCollector` startup task (SYSTEM, restarts itself).
Log: `C:\ProgramData\AradhanaLeaderboard\collector.log`.

Settings (machine environment only, never files): `ORNATE_SQL_SERVER`, `ORNATE_SQL_USER`, `ORNATE_SQL_PASSWORD`,
`ORNATE_SQL_DATABASE` (optional), `LEADERBOARD_ENDPOINT`, `LEADERBOARD_TOKEN`, `LEADERBOARD_INTERVAL_SECONDS`,
`LEADERBOARD_LOG_FILE`, `LEADERBOARD_CA_BUNDLE` (only for a private CA; TLS verification is never disabled).

Do not commit a copy of `install-collector.ps1` with a token filled in.
