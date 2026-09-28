import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types, F

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

@dp.message(F.reply_to_message)
async def handle_admin_reply(message: types.Message):
    orig_text = message.reply_to_message.text or ""
    if "💬 Сообщение от клиента (" in orig_text:
        try:
            client_id = orig_text.split("💬 Сообщение от клиента (")[1].split(")")[0]
            if client_id in active_connections:
                await active_connections[client_id].send_text(message.text)
            else:
                await message.reply("Клиент отключился.")
        except Exception as e:
            await message.reply(f"Ошибка отправки: {e}")
