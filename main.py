from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
from typing import Dict, List
import sqlite3
import json
import uuid
import os

app = FastAPI()

# SQLite
conn = sqlite3.connect('chat.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS messages
                  (id TEXT, room TEXT, sender TEXT, text TEXT, timestamp TEXT)''')
conn.commit()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.usernames: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, room: str, username: str):
        await websocket.accept()
        self.usernames[websocket] = username
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)
        await self.broadcast_users(room)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.active_connections:
            self.active_connections[room].remove(websocket)
        if websocket in self.usernames:
            del self.usernames[websocket]

    async def broadcast(self, message: str, room: str):
        if room in self.active_connections:
            for conn in self.active_connections[room]:
                await conn.send_text(message)

    async def broadcast_users(self, room: str):
        if room in self.active_connections:
            users = [self.usernames[ws] for ws in self.active_connections[room] if ws in self.usernames]
            for conn in self.active_connections[room]:
                await conn.send_text(json.dumps({"users": users}))

manager = ConnectionManager()

@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await websocket.accept()
    init = await websocket.receive_text()
    try:
        data = json.loads(init)
        username = data.get("username", "Аноним")
    except:
        username = "Аноним"

    await manager.connect(websocket, room, username)

    # История сообщений
    cursor.execute("SELECT * FROM messages WHERE room=? ORDER BY timestamp LIMIT 50", (room,))
    for msg in cursor.fetchall():
        await websocket.send_text(f"[{msg[4]}] {msg[2]}: {msg[3]}")

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            msg_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%H:%M")
            cursor.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                          (msg_id, room, data['sender'], data['text'], timestamp))
            conn.commit()

            await manager.broadcast(f"[{timestamp}] {data['sender']}: {data['text']}", room)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room)
        await manager.broadcast_users(room)

    except json.JSONDecodeError:
        await websocket.send_text("Ошибка: неверный формат сообщения")

# Статика
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/{room}")
def get_room(room: str):
    return FileResponse(os.path.join(static_dir, "index.html"))
