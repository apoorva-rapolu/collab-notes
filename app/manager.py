"""
Tracks live WebSocket connections per document and handles broadcasting +
presence (who's currently viewing a document).
"""

from typing import Dict, List, Optional

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        # document_id -> list of {"ws": WebSocket, "username": str}
        self.active_connections: Dict[str, List[dict]] = {}

    async def connect(self, websocket: WebSocket, document_id: str, username: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(document_id, []).append(
            {"ws": websocket, "username": username}
        )
        print(f"  [manager] doc '{document_id}' now has {self.count(document_id)} connection(s)")

    def disconnect(self, websocket: WebSocket, document_id: str) -> None:
        conns = self.active_connections.get(document_id, [])
        self.active_connections[document_id] = [c for c in conns if c["ws"] is not websocket]
        if not self.active_connections[document_id]:
            del self.active_connections[document_id]
        print(f"  [manager] doc '{document_id}' now has {self.count(document_id)} connection(s)")

    def usernames(self, document_id: str) -> List[str]:
        return [c["username"] for c in self.active_connections.get(document_id, [])]

    def count(self, document_id: str) -> int:
        return len(self.active_connections.get(document_id, []))

    async def broadcast(
        self, document_id: str, message: dict, exclude: Optional[WebSocket] = None
    ) -> None:
        """Send `message` to every client viewing `document_id`. Any connection
        that has gone stale (send fails) is cleaned up automatically."""
        dead: List[WebSocket] = []
        for conn in list(self.active_connections.get(document_id, [])):
            if conn["ws"] is exclude:
                continue
            try:
                await conn["ws"].send_json(message)
            except Exception:
                dead.append(conn["ws"])
        for ws in dead:
            self.disconnect(ws, document_id)

    async def broadcast_presence(self, document_id: str) -> None:
        await self.broadcast(
            document_id,
            {"type": "presence", "users": self.usernames(document_id)},
        )
