import asyncio
import re
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from aiogram import Bot, Dispatcher, types
from aiogram.types import BufferedInputFile, ReplyKeyboardRemove

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

            # Обработка закрытия диалога клиентом
            if data == "CLIENT_CLOSED_DIALOG":
                await websocket.send_text("SYSTEM_CLOSE_DIALOG")
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🔴 Клиент ({client_id}) завершил диалог.",
                    reply_markup=ReplyKeyboardRemove()
                )
                break

            # Прием фото от клиента
            if data.startswith("data:image"):
                _, encoded = data.split(",", 1)
                file_bytes = base64.b64decode(encoded)
                photo = BufferedInputFile(file_bytes, filename="photo.png")
                await bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photo,
                    caption=f"📷 Фото от клиента ({client_id})",
                    reply_markup=ReplyKeyboardRemove()
                )

            # Прием голосового от клиента
            elif data.startswith("data:audio"):
                _, encoded = data.split(",", 1)
                file_bytes = base64.b64decode(encoded)
                voice = BufferedInputFile(file_bytes, filename="voice.ogg")
                await bot.send_voice(
                    chat_id=ADMIN_ID,
                    voice=voice,
                    caption=f"🎙️ Голосовое от клиента ({client_id})",
                    reply_markup=ReplyKeyboardRemove()
                )

            # Обычный текст от клиента
            else:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"💬 Сообщение от клиента ({client_id}):\n{data}",
                    reply_markup=ReplyKeyboardRemove()
                )

    except WebSocketDisconnect:
        if active_connections.get(client_id) == websocket:
            del active_connections[client_id]

@dp.message()
async def handle_admin_reply(message: types.Message):
    global last_active_client
    target_client_id = None

    # Обработка команды /close от админа в Telegram для принудительного закрытия диалога
    if message.text and message.text.startswith("/close"):
        parts = message.text.split(" ", 1)
        if len(parts) >= 2:
            target_client_id = parts[1].strip()
        else:
            target_client_id = last_active_client

        if target_client_id and target_client_id in active_connections:
            try:
                ws = active_connections[target_client_id]
                await ws.send_text("SYSTEM_CLOSE_DIALOG")
                await ws.close()
                del active_connections[target_client_id]
                await message.reply(f"✅ Диалог с клиентом [{target_client_id}] успешно закрыт.", reply_markup=ReplyKeyboardRemove())
            except Exception as e:
                await message.reply(f"⚠️ Ошибка при закрытии диалога: {e}", reply_markup=ReplyKeyboardRemove())
        else:
            await message.reply("⚠️ Клиент не найден в активных соединениях.", reply_markup=ReplyKeyboardRemove())
        return

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
        await message.reply("⚠️ Нет активного клиента на сайте.", reply_markup=ReplyKeyboardRemove())
        return

    payload_to_send = None

    # Если админ отправил ФОТО
    if message.photo:
        file_id = message.photo[-1].file_id
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        encoded = base64.b64encode(file_bytes.read()).decode("utf-8")
        payload_to_send = f"data:image/png;base64,{encoded}"

    # Если админ отправил ГОЛОСОВОЕ
    elif message.voice:
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        encoded = base64.b64encode(file_bytes.read()).decode("utf-8")
        payload_to_send = f"data:audio/ogg;base64,{encoded}"

    # Если админ отправил ТЕКСТ
    elif message.text:
        payload_to_send = message.text

    if not payload_to_send:
        await message.reply("⚠️ Этот тип сообщений не поддерживается.", reply_markup=ReplyKeyboardRemove())
        return

    # Отправка напрямую в веб-сокет
    if target_client_id in active_connections:
        try:
            await active_connections[target_client_id].send_text(payload_to_send)
            await message.reply(f"✅ Отправлено клиенту [{target_client_id}]", reply_markup=ReplyKeyboardRemove())
            return
        except Exception:
            pass

    # Буферизация, если клиент временно не в сети
    if target_client_id not in pending_messages:
        pending_messages[target_client_id] = []
    pending_messages[target_client_id].append(payload_to_send)
    await message.reply(f"📥 Сохранено в очередь для [{target_client_id}].", reply_markup=ReplyKeyboardRemove())
