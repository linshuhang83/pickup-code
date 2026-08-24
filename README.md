# Pickup Code — Automatic Parcel Pickup-Code Collection and Alerts

Pickup Code monitors parcel-notification messages synced to a Mac through iMessage, extracts pickup locations and codes, and presents them in a small web app. New codes can optionally trigger Bark notifications on an iPhone.

The application is local-first: the Messages database and SQLite data remain on the Mac. Use it from a Mac browser, or install it as an iPhone PWA.

## Architecture

```text
iPhone SMS ── iMessage sync ──> Mac ~/Library/Messages/chat.db
                                       |
                                Python background service
                                ├─ sms_monitor  watches chat.db
                                ├─ parser       extracts locations and pickup codes
                                ├─ database     SQLite storage and deduplication
                                ├─ notifier     Bark notifications
                                └─ FastAPI      API and static frontend
                                       |
                        Mac browser / iPhone PWA / Vercel frontend
```

For remote access, Vercel serves only the static frontend. Requests under `/api/*` are securely rewritten through Tailscale Funnel to the FastAPI service that continues running on the Mac.

## Requirements

- macOS with Messages signed in to iMessage
- Python 3.10 or later
- An iPhone with SMS forwarding enabled for the Mac
- Optional: [Bark](https://apps.apple.com/app/id1403753865) for push notifications
- Optional: Tailscale and Vercel for secure remote access

## Quick Start

```bash
./scripts/run.sh
```

1. Open `http://localhost:8787` in a browser.
2. Grant Messages access the first time you run the service (see below).
3. On an iPhone in the same local network, open `http://<mac-lan-ip>:8787`, tap **Share** in Safari, then choose **Add to Home Screen**.

## Grant Full Disk Access

macOS privacy controls can block access to `~/Library/Messages/chat.db`. If the log says that the Messages database cannot be opened, or the API returns no data:

1. Open **System Settings → Privacy & Security → Full Disk Access**.
2. Add and enable **Terminal**, plus the app you use to run the service (such as VS Code).
3. Restart the service with `./scripts/run.sh`.
4. Check `http://localhost:8787/api/packages?status=pending` for parsed records.

## Enable iPhone-to-Mac Message Sync

- In macOS **Messages**, confirm that you are signed in to iMessage.
- On iPhone, go to **Settings → Messages → Text Message Forwarding** and enable this Mac.
- Confirm that `~/Library/Messages/chat.db` exists and that new messages appear in Messages on the Mac.

## Features

- Pending and picked-up tabs; picked-up records can be restored.
- Pickup-station grouping, newest-first ordering, and pagination.
- One-click pickup status changes and confirmed record deletion.
- Manual entry for parcel messages that do not include a code.
- Automatic deduplication of matching station-and-code records on the same day.
- Background message monitoring plus a 30-second browser refresh.

## Optional Bark Notifications

1. Install [Bark](https://apps.apple.com/app/id1403753865) from the App Store.
2. Copy the device key from the URL shown in the Bark app.
3. In Pickup Code, open **Settings**, paste the key, and send a test notification.

Leaving the field blank does not affect the web app.

## Optional Access Token

By default, no access token is required, which is suitable only for a trusted local network. To protect the service, set the `QJK_TOKEN` environment variable to a strong random value before running `./scripts/run.sh`.

When protection is enabled, enter the same value in **Settings → Access Token** on each browser or device. The value is stored only in that browser's local storage and is sent with API requests.

Never commit a real access token, Bark device key, or other credential to the repository.

## iPhone PWA Notes

- Adding the site to the Home Screen opens it in an app-like standalone window.
- iOS permits service workers only on HTTPS. A local-network HTTP address therefore has no offline cache, but normal online use is unaffected.
- If a page loads slowly, pull to refresh or reopen it.

## GitHub + Vercel + Tailscale Funnel

The complete backend cannot run on Vercel: iMessage access, SQLite storage, and SMS monitoring must remain on the Mac. The production layout is **Vercel static frontend + Tailscale Funnel + Mac FastAPI**.

1. Start the protected Mac service after setting a strong `QJK_TOKEN` value. Keep the Mac powered on and the service running.
2. Install the standalone macOS version of Tailscale, sign in, install its CLI integration, and run:

   ```bash
   tailscale funnel --bg 8787
   tailscale funnel status
   ```

   Funnel should expose only the local FastAPI service on `127.0.0.1:8787` over HTTPS.

3. Import the private GitHub repository into Vercel with these settings:

   - **Root Directory:** `web`
   - **Framework Preset:** `Other`
   - **Build Command:** leave unset
   - **Output Directory:** `.`

4. In the deployed app, save the same access token in **Settings**.

If the Funnel hostname changes, update the rewrite origin in `web/vercel.json` and redeploy.

## Limitations

- Some parcel messages, such as messages containing only a tracking number, do not include a pickup code. Add those records manually if a later pickup-code message does not arrive.
- The monitor imports only the most recent 30 days of messages.
- If iMessage stops syncing to the Mac, no new codes can be collected until sync resumes.
- A phone can access the Vercel site over cellular data, but the Mac backend must still be online and reachable through Funnel.

## Tests

```bash
.venv/bin/python -m pytest server/tests/ -q
```

The suite contains 99 tests covering message parsing, deduplication, grouping and pagination, monitor recovery, API routes, authentication, state changes, and mocked Bark notifications.

## Stack

Python, FastAPI, SQLite, watchdog, vanilla JavaScript, PWA, Bark, Tailscale Funnel, and Vercel. The app has no frontend CDN dependency; Bark is the only outbound integration when notifications are enabled.

## Security

- Keep the GitHub repository private if it contains deployment details.
- Do not expose the FastAPI service directly to the public internet; use Tailscale Funnel as configured.
- Never commit `QJK_TOKEN`, Bark keys, `data/`, `~/Library/Messages/chat.db`, or real SMS contents.
- Do not place secrets in source files, README examples, commits, or screenshots.
