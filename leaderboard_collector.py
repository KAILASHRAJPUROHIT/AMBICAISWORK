"""Aradhana daily sales leaderboard collector (runs on the Dell, SERVER2K22).

Reads today's sales vouchers out of the Ornate SQL Server database, aggregates
them per salesman, and pushes the result to the MDM server so managed tablets can
show a leaderboard card.

Design notes
------------
* Credentials come from the MACHINE environment (ORNATE_SQL_USER / _PASSWORD /
  _SERVER / ORNATE_SQL_DATABASE). They are never written to a file, never passed
  on a command line, and never logged.
* Read-only: the login is a member of db_datareader only.
* The salesman named "None" is a placeholder in Ornate (SalesManMstID 10000002)
  that carries most of the shop's historical bills. It is excluded from the
  ranking and never shown.
* "Today" is the database server's own date, so the shop's books and the
  leaderboard always agree.
* A failed poll never stops the loop - it logs and tries again.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import sys
import time
import urllib.request
from datetime import datetime

import pyodbc

LOG = logging.getLogger("leaderboard")

DB_ENV = "ORNATE_SQL_DATABASE"
DEFAULT_DB = r"D:\ORNNX\ORNATENXDATA\DATA\ARADHANAJE\ARADHANAJE.MDF"
EXCLUDED_SALESMAN = "None"

# Source of truth for the leaderboard. Verified against live data 2026-09-29.
#
#   SPTran is one row per SOLD ITEM. The bill identity is SPMstID: several
#   rows can share one SPMstID (differing RowNo), and that whole set is a
#   single bill. So bills = COUNT(DISTINCT SPMstID), value = SUM(TotalAmt).
#
#   VouType 'SL' is a sale. 'PUR' is a purchase, 'CH'/'PCH' are challans,
#   'SRT' is a stock return - none of those are sales.
#
#   SalesManID = 0 is Ornate's "not recorded" marker, and a master row
#   literally named 'None' is the same idea. Both are dropped rather than
#   shown as a person.
#
#   Trans (voucher postings, 9,306 SL rows) is deliberately NOT used: it has no
#   salesman and its rows are per-account postings, not per-bill. IRMst is a
#   legacy table (132 rows) and is not the current ledger.
SQL = """
SET NOCOUNT ON;
SELECT sm.SalesManName AS name,
       COUNT(DISTINCT sp.SPMstID) AS bills,
       SUM(sp.TotalAmt)            AS total
FROM   SPTran sp
JOIN   SalesManMst sm ON sm.SalesManMstID = sp.SalesManID
WHERE  sp.VouType = 'SL'
  AND  sp.SalesManID <> 0
  AND  sm.SalesManName IS NOT NULL
  AND  sm.SalesManName <> ?
  AND  CAST(sp.VouDate AS date) = CAST(GETDATE() AS date)
GROUP BY sm.SalesManName
ORDER BY SUM(sp.TotalAmt) DESC;
"""


def connection_string() -> str:
    server = os.environ.get("ORNATE_SQL_SERVER", "").strip()
    user = os.environ.get("ORNATE_SQL_USER", "").strip()
    password = os.environ.get("ORNATE_SQL_PASSWORD", "")
    database = os.environ.get(DB_ENV, DEFAULT_DB).strip()
    if not server or not user or not password:
        raise RuntimeError(
            "ORNATE_SQL_SERVER / ORNATE_SQL_USER / ORNATE_SQL_PASSWORD are not set "
            "in the machine environment."
        )
    return ";".join([
        "DRIVER={ODBC Driver 17 for SQL Server}",
        f"SERVER={server}",
        f"DATABASE={database}",
        f"UID={user}",
        f"PWD={password}",
        "Encrypt=no",
        "TrustServerCertificate=yes",
        "Connection Timeout=15",
    ])


def fetch_today() -> dict:
    """Return the leaderboard for today. Raises on any failure.

    The business date is read on the same connection as the figures, so the label
    the tablets show is the database's own date rather than the collector PC's.
    """
    with pyodbc.connect(connection_string(), timeout=15) as conn:
        cursor = conn.cursor()
        cursor.execute(SQL, EXCLUDED_SALESMAN)
        rows = cursor.fetchall()
        cursor.execute("SELECT CAST(GETDATE() AS date) AS d")
        business_date = str(cursor.fetchone()[0])

    entries = []
    for name, bills, total in rows:
        entries.append({
            "name": str(name).strip(),
            "bills": int(bills or 0),
            "total": round(float(total or 0), 2),
        })
    entries.sort(key=lambda e: e["total"], reverse=True)
    for rank, entry in enumerate(entries, start=1):
        entry["rank"] = rank

    return {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "businessDate": business_date,
        "entries": entries,
        "totals": {
            "salesmen": len(entries),
            "bills": sum(e["bills"] for e in entries),
            "amount": round(sum(e["total"] for e in entries), 2),
        },
    }


def push(endpoint: str, token: str, payload: dict, timeout: int = 15) -> None:
    """POST the snapshot to the MDM ingest endpoint over verified TLS.

    Certificates are validated normally. If the MDM server uses a private CA,
    point LEADERBOARD_CA_BUNDLE at its .pem/.crt file; that is the only way to
    relax anything. Verification is never switched off.
    """
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    # MDM is behind Cloudflare, which rejects Python's default "Python-urllib" agent (error 1010).
    request.add_header("User-Agent", "AradhanaLeaderboardCollector/1.0")
    if token:
        request.add_header("X-Collector-Token", token)

    context = ssl.create_default_context(cafile=os.environ.get("LEADERBOARD_CA_BUNDLE") or None)
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        if response.status not in (200, 201, 202, 204):
            raise RuntimeError(f"endpoint returned HTTP {response.status}")


def setup_logging() -> None:
    """Log to stderr, and also to a size-capped rotating file when LEADERBOARD_LOG_FILE is set
    (the scheduled task runs under pythonw with no console, so the file is its only log)."""
    handlers = [logging.StreamHandler()]
    log_file = os.environ.get("LEADERBOARD_LOG_FILE", "").strip()
    if log_file:
        from logging.handlers import RotatingFileHandler
        handlers.append(RotatingFileHandler(log_file, maxBytes=512 * 1024, backupCount=3, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def main() -> int:
    setup_logging()
    endpoint = os.environ.get("LEADERBOARD_ENDPOINT", "").strip()
    token = os.environ.get("LEADERBOARD_TOKEN", "").strip()
    interval = max(10, int(os.environ.get("LEADERBOARD_INTERVAL_SECONDS", "30")))

    if not endpoint:
        LOG.error("LEADERBOARD_ENDPOINT is not set - nothing to push to.")
        return 2

    LOG.info("collector starting: every %ss -> %s", interval, endpoint)
    once = "--once" in sys.argv
    last_summary = None
    last_logged = 0.0
    failing = False

    while True:
        try:
            payload = fetch_today()
            push(endpoint, token, payload)
            summary = (payload["businessDate"], payload["totals"]["bills"], payload["totals"]["amount"])
            # One line per change (or every 10 minutes as a heartbeat), not one per 30-second poll.
            if once or summary != last_summary or failing or time.time() - last_logged > 600:
                LOG.info(
                    "pushed: %d salesman, %d bills, %.2f total (for %s)",
                    payload["totals"]["salesmen"],
                    payload["totals"]["bills"],
                    payload["totals"]["amount"],
                    payload["businessDate"],
                )
                last_summary, last_logged = summary, time.time()
            failing = False
        except Exception as exc:
            if not failing:  # log the first failure of a streak, not every retry
                LOG.warning("poll failed, will retry: %s", exc)
            failing = True

        if once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
