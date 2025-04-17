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

# Настройка SQLite
conn = sqlite3.connect('chat.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS messages
                  (id TEXT, room TEXT, sender TEXT, text TEXT, timestamp TEXT)''')
conn.commit()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room: str):
        await websocket.accept()
        if room not in self.active_connections:
            self.active_connections[room] = []
        self.active_connections[room].append(websocket)

    def disconnect(self, websocket: WebSocket, room: str):
        if room in self.active_connections:
            self.active_connections[room].remove(websocket)

    async def broadcast(self, message: str, room: str):
        if room in self.active_connections:
            for connection in self.active_connections[room]:
                await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{room}")
async def websocket_endpoint(websocket: WebSocket, room: str):
    await manager.connect(websocket, room)
    
    cursor.execute("SELECT * FROM messages WHERE room=? ORDER BY timestamp LIMIT 50", (room,))
    for msg in cursor.fetchall():
        await websocket.send_text(f"[{msg[4]}] {msg[2]}: {msg[3]}")

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            msg_id = str(uuid.uuid4())
            timestamp = datetime.now().strftime("%H:%M")
            cursor.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                          (msg_id, room, message_data['sender'], message_data['text'], timestamp))
            conn.commit()
            await manager.broadcast(f"[{timestamp}] {message_data['sender']}: {message_data['text']}", room)
    except WebSocketDisconnect:
        manager.disconnect(websocket, room)
    except json.JSONDecodeError:
        await websocket.send_text("Ошибка: неверный формат сообщения")

# Статические файлы
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Главная страница
@app.get("/")
async def get_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Обработка ссылок вида /room123
@app.get("/{room}")
async def get_room(room: str):
    return FileResponse(os.path.join(static_dir, "index.html"))
