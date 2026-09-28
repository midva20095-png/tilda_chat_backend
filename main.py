import asyncio
import re
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile

TOKEN = "8882726880:AAHRNXQY8b0Da7QlrIppNPKUBRktRwoPALw"
ADMIN_ID = 5943987954

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

active_connections: dict[str, WebSocket] = {}
pending_messages: dict[str, list[str]] = {}
last_active_client: str | None = None

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    global last_active_client
    await websocket.accept()
    
    active_connections[client_id] = websocket
    last_active_client = client_id

    # Отправка накопленных сообщений из очереди
    if client_id in pending_messages and pending_messages[client_id]:
        for msg in pending_messages[client_id]:
            try:
                await websocket.send_text(msg)
            except Exception:
                break
        pending_messages[client_id] = []

    try:
        while True:
            data = await websocket.receive_text()
            last_active_client = client_id

            if data.startswith("data:image"):
                _, encoded = data.split(",", 1)
                file_bytes = base64.b64decode(encoded)
                photo = BufferedInputFile(file_bytes, filename="photo.png")
                await bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photo,
                    caption=f"📷 Фото от клиента ({client_id})"
                )

            elif data.startswith("data:audio"):
                _, encoded = data.split(",", 1)
                file_bytes = base64.b64decode(encoded)
                voice = BufferedInputFile(file_bytes, filename="voice.ogg")
                await bot.send_voice(
                    chat_id=ADMIN_ID,
                    voice=voice,
                    caption=f"🎙️ Голосовое от клиента ({client_id})"
                )

            else:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💬 Сообщение от клиента ({client_id}):\n{data}"
                )

    except WebSocketDisconnect:
        if active_connections.get(client_id) == websocket:
            del active_connections[client_id]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply("Чат-бот активен и готов к пересылке сообщений.")

@dp.message()
async def handle_admin_reply(message: types.Message):
    global last_active_client
    target_client_id = None

    # Поиск ID клиента из ответного сообщения (reply)
    if message.reply_to_message:
        text_to_search = message.reply_to_message.caption or message.reply_to_message.text or ""
        match = re.search(r"\(user_.*?\)", text_to_search)
        if match:
            target_client_id = match.group(0).replace("(", "").replace(")", "")

    # Если ответ без цитирования — берем последнего активного
    if not target_client_id:
        target_client_id = last_active_client

    if not target_client_id:
        await message.reply("⚠️ Нет активного клиента на сайте.")
        return

    reply_text = message.text or "Сообщение"

    # Отправка напрямую в веб-сокет
    if target_client_id in active_connections:
        try:
            await active_connections[target_client_id].send_text(reply_text)
            await message.reply(f"✅ Отправлено клиенту [{target_client_id}]")
            return
        except Exception:
            pass

    # Буферизация, если клиент на мгновение отключился
    if target_client_id not in pending_messages:
        pending_messages[target_client_id] = []
    pending_messages[target_client_id].append(reply_text)
    await message.reply(f"📥 Сохранено в очередь для [{target_client_id}] (клиент заберет при обновлении страницы).")
