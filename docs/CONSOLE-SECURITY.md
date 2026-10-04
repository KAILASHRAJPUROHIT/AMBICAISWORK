# Console security: allowed computers, emailed code, automatic sign-out

## Allowed computers (first login binds the computer)
* After the password is right, a computer the user has not signed in from before must enter a 6-digit code. The code is emailed to `MDM_CONSOLE_OTP_EMAIL` (default `info@aradhanajewellers.com`), is valid for 10 minutes, works once, and allows 5 wrong tries.
* When the code is entered, the computer's fingerprint is added to that user's allowed list; the next sign-in from it needs no code. Settings > Security lists the allowed computers and can remove one (it then needs a new code).
* The fingerprint is built in the browser from what a browser can see of the machine (CPU threads, memory, screen, graphics card, time zone, canvas rendering) plus a random id kept in that browser. Browsers cannot read a hardware serial number. Only a SHA-256 of it leaves the browser and the server stores a SHA-256 of that. Clearing the browser's site data makes it a "new" computer again.
* Limits: 1 email per 30 s per computer, 5 per hour per user.

### Mode: `MDM_CONSOLE_DEVICE_BINDING`
| value | behaviour |
|---|---|
| `auto` (default) | enforced only while outgoing email is configured (`SMTP_HOST` set). With no SMTP the check is inactive, the server logs a warning and Settings > Security says so. This cannot lock anyone out. |
| `on` | always enforced; fails closed (if the email cannot be sent, a new computer cannot sign in). |
| `off` | disabled. This is the emergency switch if the owner is locked out: set it, restart the server. |

The server needs working SMTP for the code to arrive: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USERNAME`, `SMTP_PASSWORD` in `.env` (AWS SES SMTP works). **Until SMTP is set, the allowed-computers check is not active.**

## Automatic sign-out
The console signs out after 30 s without mouse, keyboard, touch or scroll activity (warning for the last 10 s). Change it in Settings > Security (15 s to 1 h, per browser). A console tab left idle past the limit is signed out when reopened.

## Not verified yet
* The server Java (guard, mapper, resource, `AuthResource` change, Liquibase changeset) was written without a local Maven build: build and run the server tests before deploying (`docker compose build server` or the usual release build).
* No test email has been sent.
