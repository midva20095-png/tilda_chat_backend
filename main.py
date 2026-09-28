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

# Хранилище активных подключений и истории неотправленных сообщений
active_connections: dict[str, WebSocket] = {}
pending_messages: dict[str, list[str]] = {}

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(dp.start_polling(bot))

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket

    # Если для этого клиента есть накопившиеся ответы из Telegram, отправляем их
    if client_id in pending_messages and pending_messages[client_id]:
        for msg in pending_messages[client_id]:
            await websocket.send_text(msg)
        pending_messages[client_id] = []

    try:
        while True:
            data = await websocket.receive_text()
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=f"💬 Сообщение от клиента ({client_id}):\n{data}\n\nОтветьте на это сообщение в Telegram."
            )
    except WebSocketDisconnect:
        if client_id in active_connections:
            del active_connections[client_id]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply("Бот активен и готов пересылать сообщения!")

@dp.message()
async def handle_admin_reply(message: types.Message):
    if message.reply_to_message and message.reply_to_message.text:
        orig_text = message.reply_to_message.text
        match = re.search(r"💬 Сообщение от клиента \((.*?)\):", orig_text)
        
        if match:
            client_id = match.group(1)
            reply_text = message.text

            # Если клиент сейчас на сайте — отправляем сразу
            if client_id in active_connections:
                try:
                    await active_connections[client_id].send_text(reply_text)
                    await message.reply("✅ Ответ отправлен на сайт!")
                    return
                except Exception:
                    pass

            # Если клиент обновил страницу или временно оффлайн — сохраняем ответ
            if client_id not in pending_messages:
                pending_messages[client_id] = []
            pending_messages[client_id].append(reply_text)
            await message.reply("📥 Сообщение сохранено! Клиент получит его, как только откроет страницу.")
