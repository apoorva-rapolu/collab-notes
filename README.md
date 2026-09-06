# Real-Time Collaborative Notes

A real-time collaborative notes application that allows multiple users to open the same document and edit it through a shared browser interface. Users can see who is currently viewing the document, receive typing indicators, and synchronize document changes through WebSockets. Documents are persisted in PostgreSQL so that data remains available after refreshing the page or restarting the application.

## Features

- Real-time collaborative text editing
- Multiple users can work on the same document
- WebSocket-based two-way communication
- User presence tracking
- Live typing indicators
- Persistent document storage using PostgreSQL
- Document version tracking
- Last-Write-Wins (LWW) conflict resolution
- Conflict notifications for concurrent edits
- Docker-based local development
- Cloud deployment using Render and Supabase

## Technology Stack

- **Backend:** Python, FastAPI
- **Real-time communication:** WebSockets
- **Database:** PostgreSQL
- **Database driver:** asyncpg
- **Frontend:** HTML, CSS, JavaScript
- **Containerization:** Docker, Docker Compose
- **Deployment:** Render
- **Cloud Database:** Supabase

## Project Structure

```text
collab-notes/
│
├── app/
│   ├── main.py          # FastAPI application and WebSocket endpoint
│   ├── manager.py       # Connection management, broadcasting and presence
│   ├── database.py      # PostgreSQL connection and document operations
│   └── __init__.py
│
├── static/
│   └── index.html       # Frontend editor and WebSocket client
│
├── Dockerfile           # Container configuration
├── docker-compose.yml   # Local application + PostgreSQL setup
├── requirements.txt     # Python dependencies
└── README.md
```

## How the Application Works

When a user opens a document, the browser establishes a WebSocket connection with the FastAPI server.

The basic flow is:

```text
Browser
   │
   │ WebSocket
   ▼
FastAPI Server
   │
   ├── Connection Manager
   │       ├── Active users
   │       ├── Broadcasting
   │       └── Presence
   │
   └── PostgreSQL
           │
           └── Document state
```

When a user edits the document, the browser sends the updated content to the server. The server stores the new document state in PostgreSQL and broadcasts the accepted update to users connected to the same document.

This allows connected clients to receive document updates without manually refreshing the page.

## WebSocket Communication

WebSockets are used instead of normal HTTP requests because collaboration requires continuous two-way communication.

With normal HTTP:

```text
Client → Request → Server
Client ← Response ← Server
```

With WebSockets:

```text
Client ⇄ Server
```

The connection remains open, allowing the server to immediately send updates to connected users.

The application uses several WebSocket message types:

- `init` – sends the current document state when a user connects
- `edit` – sends a document edit to the server
- `update` – broadcasts the accepted document state
- `typing` – informs other users that someone is typing
- `presence` – updates the list of currently connected users
- `conflict_notice` – informs a user when their edit overwrites a newer change
- `user_joined` / `user_left` – tracks users entering or leaving a document

## Document Persistence

Documents are stored in a PostgreSQL table containing information such as:

```text
id
content
version
updated_by
updated_at
```

The document ID is taken from the URL. This allows different URLs to represent different collaborative documents.

For example:

```text
?doc=meeting-notes
```

means that users with the same document ID are working in the same document.

## User Identification

Users can specify a username through the URL:

```text
http://localhost:8000/static/index.html?doc=meeting-notes&user=apoorva
```

Another user can join the same document with:

```text
http://localhost:8000/static/index.html?doc=meeting-notes&user=riya
```

The users will then appear in the **Viewing now** section.

## Conflict Resolution

The application uses a **Last-Write-Wins (LWW)** strategy for concurrent edits.

Each document has a version number. When a client makes an edit, it sends the version of the document that it was working from.

The server compares that version with the current database version.

If another edit has already been saved, a conflict is detected. The incoming edit is still accepted, and the document receives a new version. The latest accepted write becomes the current document state.

For example:

```text
Initial document
Version 5
     │
     ├── User A edits
     │
     └── User B edits
           │
           ▼
      Server receives edits
           │
           ▼
      Latest accepted edit wins
```

The application displays a conflict notification when an edit overwrites changes made by another user.

### Why LWW?

The application sends the complete document content rather than individual character-level operations. This makes LWW a simple and understandable conflict-resolution strategy for the project.

A more advanced collaborative editor could use techniques such as **Operational Transformation (OT)** or **CRDTs** to merge simultaneous edits at a finer level.

## Local Setup

### Prerequisites

Make sure the following are installed:

- Docker
- Docker Compose
- Git

### Run the Application

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

```text
http://localhost:8000
```

### Test Multiple Users

Open the same document in two browser tabs:

```text
http://localhost:8000/static/index.html?doc=meeting-notes&user=apoorva
```

```text
http://localhost:8000/static/index.html?doc=meeting-notes&user=riya
```

Both users are connected to the same document but have different usernames.

## Deployment

The application is deployed using **Render**, while **Supabase** provides the hosted PostgreSQL database.

The production architecture is:

```text
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

The GitHub repository is connected to Render. When changes are pushed to the repository, Render can automatically build and deploy the updated application.

The Dockerfile is used by Render to build the application container.

The application uses Render's assigned `PORT` environment variable so that the FastAPI server can run correctly in the deployment environment.

## Production Application

The deployed application is available at:

```text
https://collab-notes-jx78.onrender.com/
```

A specific user and document can be opened using:

```text
https://collab-notes-jx78.onrender.com/static/index.html?doc=meeting-notes&user=apoorva
```

## Testing

The application can be tested by opening the same document in multiple browser tabs or devices.

Example:

```text
User 1:
?doc=test&user=apoorva

User 2:
?doc=test&user=riya
```

The test should verify:

1. Both users can connect to the same document.
2. Both users appear in the presence list.
3. Typing indicators are displayed.
4. Document edits are sent through WebSockets.
5. Changes are persisted in PostgreSQL.
6. Updates are broadcast to connected clients.
7. Concurrent edits trigger the LWW conflict mechanism.
8. Refreshing the page loads the persisted document state.

## Limitations

The current implementation uses whole-document synchronization with Last-Write-Wins conflict resolution. Therefore, if multiple users make conflicting edits at the same time, one user's changes may overwrite another user's changes.

This is a deliberate design choice that keeps the implementation simple and demonstrates the fundamentals of:

- WebSockets
- asynchronous communication
- client-server synchronization
- database persistence
- presence tracking
- versioning
- conflict detection
- containerization
- cloud deployment

A future version could use a CRDT or Operational Transformation to merge concurrent edits instead of choosing a single winning version.

## Future Improvements

Possible improvements include:

- Character-level collaborative editing
- CRDT-based synchronization
- User authentication
- Document sharing and permissions
- Rich-text editing
- Document history and version rollback
- Automatic reconnection after WebSocket failure
- Improved conflict resolution
- Redis or another shared state layer for horizontal scaling

## Summary

This project demonstrates how a real-time collaborative application can be built using **FastAPI, WebSockets, PostgreSQL, Docker, Render, and Supabase**. The backend manages WebSocket connections and document synchronization, while PostgreSQL provides persistent storage. The frontend provides a lightweight collaborative editor with presence and typing indicators.

The project combines real-time communication, asynchronous programming, database management, conflict handling, containerization, and cloud deployment into a single application.

