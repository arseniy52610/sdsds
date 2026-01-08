import os
import re
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters
)
from mistralai.client import MistralClient

# ================= CONFIG =================

TELEGRAM_TOKEN = "8577515890:AAFlBSqsjpq5eE1oHlCtTZjtxb38_LZ8MS8"
MISTRAL_API_KEY = "kBRWeCcqICY8Q20fKADOAE6HxZ07OeU6"
ADMIN_CHAT_ID = 1947766225  # ID администратора (int!)

MEMORY_FILE = "memory.txt"
PHOTO_FOLDER = "photos"

# =========================================

# Инициализация клиента Mistral
mistral = MistralClient(api_key=MISTRAL_API_KEY)

# Сессии пользователей с оператором
operator_sessions = {}

# Хранение состояния ожидания фото от ИИ
awaiting_photo = {}

# ===== Загрузка памяти бота =====
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return ""
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return f.read()

# ===== Конвертация **текста** в <b> =====
def markdown_to_html(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

# ===== Стартовая команда =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! Я бот технической поддержки VPN сервиса — <b>BynexVPN!</b>\n\n"
        "Какой у вас вопрос?",
        parse_mode="HTML"
    )

# ===== Обработка текстовых сообщений =====
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    text_lower = text.lower()

    # ===== Фильтр мата =====
    BAD_WORDS = [
        "блядь", "блять", "ебать", "пизда", "хуй", "нахуй", "пиздец",
        "мудак", "мудила", "гандон", "шлюха", "шалава", "дрочить",
        "похуй", "еблан", "заебал", "бля"
    ]

    if any(word in text_lower for word in BAD_WORDS):
        await update.message.reply_text(
            "⚠️ Сообщение содержит ненормативную лексику. "
            "Пожалуйста, соблюдайте корректный стиль общения."
        )
        return

    # ===== Если уже общается с оператором =====
    if user_id in operator_sessions:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"<b>Сообщение от пользователя {user_id}:</b>\n"
                f"<blockquote>{text}</blockquote>"
            ),
            parse_mode="HTML"
        )
        return

    # ===== Запрос оператора =====
    if "оператор" in text_lower or "человек" in text_lower:
        operator_sessions[user_id] = True

        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=(
                f"<b>Пользователь {user_id} вызывает оператора:</b>\n"
                f"<blockquote>{text}</blockquote>"
            ),
            parse_mode="HTML"
        )

        await update.message.reply_text(
            "<b>Я передал ваш вопрос оператору.</b>\n<blockquote>График: с 10:00 до 00:00 (МСК)</blockquote>",
            parse_mode="HTML"
        )
        return

    # ===== Ответ через Mistral =====
    system_prompt = load_memory()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]

    try:
        await context.bot.send_chat_action(chat_id=user_id, action="typing")

        response = mistral.chat(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.3
        )

        answer = response.choices[0].message.content
        formatted_answer = markdown_to_html(answer)

        # ===== Запрос фото =====
        if "пришлите фото" in answer.lower() or "пришлите скрин" in answer.lower():
            awaiting_photo[user_id] = True
            await update.message.reply_text(
                "<b>Пожалуйста, отправьте фото или скрин.</b>",
                parse_mode="HTML"
            )
            return

        # ===== Перевод на оператора =====
        if "переведу вас на оператора" in answer.lower():
            operator_sessions[user_id] = True
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"<b>Пользователь {user_id} переведён на оператора.</b>",
                parse_mode="HTML"
            )
            await update.message.reply_text(
                "<b>Я передал ваш запрос оператору.</b>",
                parse_mode="HTML"
            )
            return

        await update.message.reply_text(formatted_answer, parse_mode="HTML")

    except Exception as e:
        print(e)
        await update.message.reply_text(
            "Произошла ошибка. Попробуйте позже."
        )

# ===== Обработка фото =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    os.makedirs(PHOTO_FOLDER, exist_ok=True)

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = f"{PHOTO_FOLDER}/{user_id}_{file.file_id}.jpg"
    await file.download_to_drive(file_path)

    # ===== Фото по запросу ИИ =====
    if awaiting_photo.get(user_id):
        awaiting_photo[user_id] = False
        operator_sessions[user_id] = True

        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=open(file_path, "rb"),
            caption=f"<b>Фото от пользователя {user_id}</b>",
            parse_mode="HTML"
        )

        await update.message.reply_text(
            "<b>Фото получено. Оператор рассмотрит его.</b>",
            parse_mode="HTML"
        )
        return

    # ===== Фото оператору =====
    if user_id in operator_sessions:
        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=open(file_path, "rb"),
            caption=f"<b>Фото от пользователя {user_id}</b>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            "<b>Фото отправлено оператору.</b>",
            parse_mode="HTML"
        )
        return

    await update.message.reply_text(
        "Фото получено. Опишите ваш вопрос.",
        parse_mode="HTML"
    )

# ===== Команда /reply (админ) =====
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_CHAT_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /reply user_id текст")
        return

    user_id = int(context.args[0])
    text = " ".join(context.args[1:])

    if user_id not in operator_sessions:
        await update.message.reply_text("Нет активного диалога.")
        return

    await context.bot.send_message(
        chat_id=user_id,
        text=f"<b>Сообщение от оператора:</b>\n<blockquote>{text}</blockquote>",
        parse_mode="HTML"
    )

    await update.message.reply_text("Ответ отправлен.")

# ===== Команда /done (админ) =====
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /done user_id")
        return

    user_id = int(context.args[0])

    if user_id not in operator_sessions:
        await update.message.reply_text("Диалог не найден.")
        return

    del operator_sessions[user_id]

    await context.bot.send_message(
        chat_id=user_id,
        text=(
            "<b>Диалог закрыт.</b>\n"
            "Если появятся вопросы — обращайтесь 🤖"
        ),
        parse_mode="HTML"
    )

    await update.message.reply_text("Диалог завершён.")

# ===== Запуск =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_user_message))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))

    print("БОТ ЗАПУЩЕН")
    app.run_polling()

