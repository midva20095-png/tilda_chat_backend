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

# Хранилище активных WebSocket-подключений
active_connections: dict[str, WebSocket] = {}

@app.on_event("startup")
async def on_startup():
    # Запускаем поллинг сообщений от Telegram в фоновом режиме
    asyncio.create_task(dp.start_polling(bot))

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
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

# Команда /start для проверки
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.reply("Бот активен и готов пересылать сообщения!")

# Обработчик любых ответов администратора в Telegram
@dp.message()
async def handle_admin_reply(message: types.Message):
    # Проверяем, что ответ отправлен с функцией Reply на сообщение бота
    if message.reply_to_message and message.reply_to_message.text:
        orig_text = message.reply_to_message.text
        
        # Извлекаем client_id из оригинального сообщения бота
        match = re.search(r"💬 Сообщение от клиента \((.*?)\):", orig_text)
        if match:
            client_id = match.group(1)
            
            if client_id in active_connections:
                # Отправляем ответ обратно клиенту через WebSocket
                await active_connections[client_id].send_text(message.text)
                await message.reply("✅ Ответ отправлен на сайт!")
            else:
                await message.reply("⚠️ Клиент закрыл вкладку или переподключается.")
