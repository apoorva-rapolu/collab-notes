# Real-Time Collaborative Notes

A stripped-down, Google-Docs-style notes app: multiple people open the same
document URL, type at the same time, and see each other's edits and presence
live over a WebSocket connection. State is persisted to Postgres so a page
refresh (or a server restart) doesn't lose anything.

## Stack

- **FastAPI** + native `WebSocket` support (Starlette under the hood)
- **PostgreSQL** via `asyncpg` (no ORM — one table, raw SQL, kept intentionally simple)
- **Docker Compose** to run the app + DB together
- Plain HTML/JS client (`static/index.html`) — no build step, just open it in
  two browser tabs

## Project layout

```
collab-notes/
├── app/
│   ├── main.py        # FastAPI app + WebSocket endpoint (the core logic)
│   ├── manager.py      # Tracks connections per document, broadcasts, presence
│   └── database.py     # asyncpg pool, get_document / save_document
├── static/
│   └── index.html      # Test client: editor, presence sidebar, conflict banner
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Running it

```bash
docker compose up --build
```

Then open two (or more) browser tabs at:

```
http://localhost:8000/static/index.html?doc=meeting-notes&user=apoorva
http://localhost:8000/static/index.html?doc=meeting-notes&user=riya
```

Same `doc` param = same document/room. Different `user` params = you'll see
each other in the "Viewing now" sidebar and each other's typing/edits live.

## How sync works

1. On connect, the server sends the client an `init` message with the
   document's current `content` + `version`.
2. As you type, the client **debounces edits by 300ms** and sends
   `{"type": "edit", "content": "...", "base_version": N}` — `base_version`
   is the version the client last saw.
3. The server compares `base_version` to the document's current version in
   the DB, saves the new content with `version + 1`, and **broadcasts the
   accepted state to every connected client** (including the sender), so
   everyone converges on the same content and version number.
4. Presence: on connect/disconnect the server rebroadcasts the list of
   usernames currently viewing the document. A lightweight `typing` message
   type shows a "so-and-so is typing…" indicator without touching the DB.

## Conflict resolution: why Last-Write-Wins (LWW), not OT

I picked **LWW over Operational Transform** for this project, deliberately:

- **The unit of sync is the whole document, not individual keystrokes.**
  The client debounces and sends the full current text every ~300ms, rather
  than streaming character-level insert/delete ops. OT is built to transform
  *operations* against each other (e.g., "insert 'x' at position 5" vs
  "delete position 3") so they can be merged without stepping on each other.
  With whole-document snapshots, there's nothing to transform — two
  concurrent snapshots are just two candidate final states, and one has to
  be picked. That's exactly the problem LWW is designed for.
- **Complexity budget.** A correct OT implementation needs a transform
  function for every pair of operation types, careful handling of operation
  ordering, and usually a central sequencer — it's a multi-week project on
  its own (or you reach for a library/CRDT like Yjs or Automerge). For a
  medium-difficulty portfolio project, implementing "fake OT" badly would be
  worse than implementing real LWW well.
- **The failure mode is honest and visible.** With LWW, if two people type
  in the same document within the same debounce window, the second edit to
  reach the server wins and the first is silently discarded *unless* we tell
  the user — which is why the server sends a `conflict_notice` back to the
  losing client ("your edit overwrote changes made by another user"). It
  doesn't recover the lost text, but it's transparent about what happened,
  which is the honest trade-off to make rather than pretending the merge is
  seamless.

**Known limitation / explicit trade-off:** if two users are typing in
overlapping debounce windows, one user's changes can be overwritten. For a
personal notes app where edits are more "paragraph at a time" than
"simultaneous same-sentence" (the realistic use case here), this is an
acceptable trade-off. The natural next step, if you wanted to remove this
limitation entirely, is to swap the whole-document LWW for a CRDT (e.g.
Yjs/Automerge), which merges concurrent edits automatically at the character
level instead of picking a winner.


