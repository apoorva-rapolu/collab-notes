# Real-Time Collaborative Notes

A stripped-down, Google-Docs-style notes app: multiple people join the same
document, type at the same time, and see each other's edits and presence
live over a WebSocket connection. State is persisted to PostgreSQL, so a
page refresh (or a server restart) doesn't lose anything.

**Live demo:** https://collab-notes-jx78.onrender.com/

## Stack

- **FastAPI** + native `WebSocket` support (Starlette under the hood)
- **PostgreSQL** via `asyncpg` (no ORM — one table, raw SQL, kept intentionally simple)
- **Docker Compose** for local dev (app + DB together)
- Deployed on **Render** (app) + **Supabase** (managed Postgres)
- Plain HTML/JS client (`static/index.html`) — no build step, no framework

## Project layout

```
collab-notes/
├── app/
│   ├── main.py         # FastAPI app + WebSocket endpoint (the core logic)
│   ├── manager.py      # Tracks connections per document, broadcasts, presence
│   └── database.py     # asyncpg pool, get_document / save_document
├── static/
│   └── index.html      # Client: join screen, editor, presence sidebar, conflict banner
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Local Setup

### Prerequisites

Make sure the following are installed:

- Docker
- Docker Compose
- Git

### Run the application

Clone the repository:

```bash
git clone https://github.com/apoorva-rapolu/collab-notes.git
cd collab-notes
```

Build and start the containers:

```bash
docker compose up --build
```

The application runs on:

```
http://localhost:8000
```

### Test with multiple users

Open the app in two browser tabs:

```
http://localhost:8000/static/index.html
http://localhost:8000/static/index.html
```

Each tab shows a join screen asking for a **document name** and **your
name** — enter the same document name in both tabs (e.g. `meeting-notes`)
and a different name in each (e.g. `apoorva` and `riya`). Both tabs are now
connected to the same document under different usernames, and you'll see
each other in the "Viewing now" sidebar and each other's edits live.

(You can still pre-fill the document field by visiting
`?doc=meeting-notes`, but the username is always entered through the join
screen now, not a URL parameter.)

## How sync works

1. On connect, the server sends the client an `init` message with the
   document's current `content` and `version`.
2. As you type, the client **debounces edits by 300ms** — a burst of
   keystrokes collapses into a single edit sent after you pause, rather than
   one message per keypress.
3. The client only ever has **one of its own edits in flight at a time**. If
   you type again before the previous edit's acknowledgment comes back, the
   new content is queued and sent the instant that ack arrives, using the
   now-confirmed version number. This is what makes the sync race-free:
   without it, an acknowledgment for an older edit can arrive after a newer
   one was already sent, and naively applying it would revert the textarea
   to stale content.
4. The server compares the edit's `base_version` to the document's current
   version in the DB. If the client was behind, that's a genuine conflict —
   the edit is still saved (last-write-wins), but the server sends a
   `conflict_notice` back to that one client explaining what happened.
5. The accepted state is **broadcast to every connected client, including
   the sender**, so everyone converges on the same content and version
   number.
6. Presence: on connect/disconnect the server rebroadcasts the list of
   usernames currently viewing the document. A lightweight `typing` message
   type drives a "so-and-so is typing…" indicator without touching the DB.
7. The client reconnects automatically (with exponential backoff, capped at
   10s) if the WebSocket drops, and sends a `ping` every 20 seconds to keep
   the connection alive through reverse proxies (e.g. Render) that close
   idle sockets.

## Conflict resolution: why Last-Write-Wins (LWW), not OT

I picked **LWW over Operational Transform** for this project, deliberately:

- **The unit of sync is the whole document, not individual keystrokes.**
  The client sends the full current text after a debounce pause, rather
  than streaming character-level insert/delete operations. OT is built to
  transform *operations* against each other (e.g. "insert 'x' at position
  5" vs "delete position 3") so they can be merged without stepping on each
  other. With whole-document snapshots, there's nothing to transform — two
  concurrent snapshots are just two candidate final states, and one has to
  be picked. That's exactly the problem LWW is designed for.
- **Complexity budget.** A correct OT implementation needs a transform
  function for every pair of operation types, careful handling of operation
  ordering, and usually a central sequencer — it's a multi-week project on
  its own (or you reach for a library/CRDT like Yjs or Automerge). For a
  medium-difficulty portfolio project, implementing "fake OT" badly would be
  worse than implementing real LWW well.
- **The failure mode is honest and visible.** If two people edit within the
  same debounce window, the second edit to reach the server wins and the
  first is overwritten — but the losing client is explicitly told via
  `conflict_notice`, rather than silently losing their change with no
  explanation.

**Known limitation / explicit trade-off:** if two users edit in genuinely
overlapping windows, one user's change is overwritten, not merged. For a
notes app where edits are typically "a paragraph at a time" rather than
"the same sentence, same second," this is an acceptable trade-off. The
natural next step, if you wanted to remove this limitation entirely, is to
replace whole-document LWW with a CRDT (e.g. Yjs/Automerge), which merges
concurrent edits automatically at the character level instead of picking a
winner.

## Deployment

The application is deployed using Render, while Supabase provides the
hosted PostgreSQL database. The production architecture is:

```
                  Internet
                     │
          ┌──────────▼──────────┐
          │       Render        │
          │                     │
          │   FastAPI Server    │
          │   WebSocket Server  │
          └──────────┬──────────┘
                     │
              PostgreSQL
                     │
          ┌──────────▼──────────┐
          │      Supabase       │
          │    PostgreSQL DB    │
          └─────────────────────┘
```

- The GitHub repository is connected to Render. When changes are pushed to
  `main`, Render automatically builds and deploys the updated application.
- The `Dockerfile` is what Render uses to build the application container.
- The app reads Render's dynamically assigned `PORT` environment variable
  so the FastAPI server binds to the correct port in production:
  ```dockerfile
  CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
  ```
- Render's direct connection to Supabase failed because Supabase's default
  endpoint is IPv6-only; the fix is to use **Supabase's Session Pooler**
  connection string instead, which is IPv4-compatible.
- The `@` in the database password needs to be URL-encoded (`%40`) for the
  connection string to parse correctly.

### Production application

```
https://collab-notes-jx78.onrender.com/
```



