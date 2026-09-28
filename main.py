import asyncio
import re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

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
last_active_client: str | None = None  # Запоминаем последнего написавшего клиента

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

    # Отправляем накопившиеся неотправленные сообщения
    if client_id in pending_messages and pending_messages[client_id]:
        for msg in pending_messages[client_id]:
            await websocket.send_text(msg)
        pending_messages[client_id] = []

    try:
        while True:
            data = await websocket.receive_text()
            last_active_client = client_id  # Обновляем последнего клиента
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💬 Сообщение от клиента ({client_id}):\n{data}"
            )
    except WebSocketDisconnect:
        if client_id in active_connections:
            del active_connections[client_id]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply("Бот активен! Отвечайте простыми сообщениями последнему клиенту.")

@dp.message()
async def handle_admin_reply(message: types.Message):
    global last_active_client
    target_client_id = None

    # 1. Если ответили через Reply на конкретное сообщение
    if message.reply_to_message and message.reply_to_message.text:
        orig_text = message.reply_to_message.text
        match = re.search(r"💬 Сообщение от клиента \((.*?)\):", orig_text)
        if match:
            target_client_id = match.group(1)

    # 2. Если написали просто текстом — отправляем последнему активному клиенту
    if not target_client_id:
        target_client_id = last_active_client

    if not target_client_id:
        await message.reply("⚠️ Ни одного клиента еще не было или диалог не выбран.")
        return

    reply_text = message.text

    # Отправка на сайт
    if target_client_id in active_connections:
        try:
            await active_connections[target_client_id].send_text(reply_text)
            await message.reply(f"✅ Отправлено клиенту [{target_client_id}]")
            return
        except Exception:
            pass

    # Сохранение, если клиент оффлайн
    if target_client_id not in pending_messages:
        pending_messages[target_client_id] = []
    pending_messages[target_client_id].append(reply_text)
    await message.reply(f"📥 Сохранено для [{target_client_id}]. Сообщение придет при открытии сайта.")
