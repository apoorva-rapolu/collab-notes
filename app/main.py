import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import database as db
from .manager import ConnectionManager

app = FastAPI(title="Real-Time Collaborative Notes")
manager = ConnectionManager()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")


@app.on_event("startup")
async def on_startup() -> None:
    await db.init_db()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await db.close_db()


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.websocket("/ws/{document_id}")
async def document_socket(
    websocket: WebSocket, document_id: str, username: str = Query(default="anonymous")
):
    await manager.connect(websocket, document_id, username)

    # Send the current state to the newly-connected client immediately.
    doc = await db.get_document(document_id)
    await websocket.send_json(
        {
            "type": "init",
            "content": doc["content"],
            "version": doc["version"],
            "updated_by": doc["updated_by"],
        }
    )

    await manager.broadcast_presence(document_id)
    await manager.broadcast(
        document_id, {"type": "user_joined", "username": username}, exclude=websocket
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            print(f"  [{document_id}] from {username}: {msg_type}")

            if msg_type == "edit":
                content = data.get("content", "")
                # base_version = the version this client last saw before typing.
                base_version = data.get("base_version", 0)

                current = await db.get_document(document_id)

                # --- Conflict detection (LWW) -------------------------------
                # If someone else's edit has landed since this client last
                # synced, base_version will be behind current["version"].
                # We don't attempt to merge -- we just accept the incoming
                # edit and overwrite, then let the sender know a conflict
                # occurred so the UI can surface it. See README.md.
                conflict = base_version < current["version"]

                new_version = current["version"] + 1
                saved = await db.save_document(document_id, content, new_version, username)

                # Broadcast the *accepted* state to everyone, sender included,
                # so all clients converge on the same content + version number.
                await manager.broadcast(
                    document_id,
                    {
                        "type": "update",
                        "content": saved["content"],
                        "version": saved["version"],
                        "updated_by": saved["updated_by"],
                    },
                )

                if conflict:
                    await websocket.send_json(
                        {
                            "type": "conflict_notice",
                            "message": (
                                "Your edit overwrote changes made by another "
                                "user while you were typing (last-write-wins)."
                            ),
                            "version": saved["version"],
                        }
                    )

            elif msg_type == "typing":
                await manager.broadcast(
                    document_id, {"type": "typing", "username": username}, exclude=websocket
                )

            elif msg_type == "ping":
                # Heartbeat from the client, purely to keep the connection
                # looking "active" to any reverse proxy sitting in front of
                # this server (e.g. Render) that closes idle WebSockets.
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, document_id)
        await manager.broadcast_presence(document_id)
        await manager.broadcast(document_id, {"type": "user_left", "username": username})
