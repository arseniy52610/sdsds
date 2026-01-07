import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from mistralai.client import MistralClient
import re

# ================= CONFIG =================
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TG_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))  # id администратора
MEMORY_FILE = "memory.txt"
PHOTO_FOLDER = "photos"
# =========================================

# Инициализация клиента Mistral
mistral = MistralClient(api_key=MISTRAL_API_KEY)

# Сессии пользователей с оператором
operator_sessions = {}

# Хранение состояния ожидания фото от ИИ
awaiting_photo = {}

# Загрузка памяти бота
def load_memory():
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        return f.read()

# Конвертация **текста** в <b> для Telegram
def markdown_to_html(text: str) -> str:
    return re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

# ===== Стартовая команда =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте! Я бот технической поддержки VPN сервиса - <b>BynexVPN!</b>\n\nКакой у вас вопрос?", 
        parse_mode='HTML'
    )

# ===== Обработка сообщений пользователей =====
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    text_lower = text.lower()

    # ===== Проверка на мат =====
    BAD_WORDS = [
        "блядь", "блять", "ебать", "пизда", "хуй",
        "заебать", "заебись", "заеб", "выебать",
        "ёбан", "ёбнуть", "ёб", "нахуй",
        "пиздец", "еблан", "гавно", "дерьмо",
        "хуё", "хуя", "хуёк", "похуист",
        "похуй", "похую", "ебать", "ёбнутый",
        "заеби", "заебал", "заебать",
        "ебано", "ебать", "ебрик", "бля",
        "выёб", "выеб", "пиздатый", "ебаться", "Даун",
        "пизд", "хyй", "xyй", "бл@дь", "бл*дь", "бл**ь", "ёбaн", "ёбaть",
        "заeб", "заeбись", "пиздeц", "ёбaнный", "похyй", "нахyй", "нахyя",
        "хуe", "хуeвый", "хуяк", "пиздато", "пиздануть", "пиздюк", "ебаться",
        "мудак", "мудила", "гандон", "шлюха", "шалава", "дрочить", "дрочка"
    ]
    if any(bad_word in text_lower for bad_word in BAD_WORDS):
        await update.message.reply_text(
            "⚠️ Ваше сообщение содержит ненормативную лексику. "
            "За повторные нарушения мы можем ограничить работу нашего сервиса."
        )
        return

    # ===== Если пользователь уже общается с оператором =====
    if user_id in operator_sessions:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"<b>Ответ от пользователя</b> {user_id}:\n<blockquote>{text}</blockquote>", 
            parse_mode='HTML'
        )
        return

    # ===== Ручной запрос оператора =====
    if "оператор" in text_lower or "человек" in text_lower:
        operator_sessions[user_id] = True
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"<b>Пользователь</b> {user_id} <b>зовет на помощь!</b>\n<blockquote>{text}</blockquote>", 
            parse_mode='HTML'
        )
        await update.message.reply_text(
            "<b>Я передал ваш вопрос оператору. Ожидайте ответа.</b>"
            "<blockquote>Режим работы операторов:\nC <u>10:00</u> до <u>00:00</u> по МСК</blockquote>", 
            parse_mode='HTML'
        )
        return

    # ===== Генерация ответа через Mistral =====
    system_prompt = load_memory()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]

    try:
        # ===== Статус "печатает..." =====
        await context.bot.send_chat_action(chat_id=user_id, action="typing")

        response = mistral.chat(
            model="mistral-large-latest",
            messages=messages,
            temperature=0.3
        )

        answer = response.choices[0].message.content
        formatted_answer = markdown_to_html(answer)

        # ===== Проверка на запрос фото ИИ =====
        if "пожалуйста, пришлите скрин" in answer.lower() or "пожалуйста, пришлите фото" in answer.lower():
            awaiting_photo[user_id] = True
            await update.message.reply_text(
                "<b>Пожалуйста, пришлите скрин чека или документ.</b>",
                parse_mode="HTML"
            )
            return

        # ===== Авто-перевод на оператора по ответу ИИ =====
        if "переведу вас на оператора" in answer.lower() or "свяжу вас с оператором" in answer.lower():
            operator_sessions[user_id] = True
            # Пересылаем сообщение админу
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"<b>Пользователь</b> {user_id} <b>переведён на оператора.</b>\n<blockquote>{text}</blockquote>",
                parse_mode="HTML"
            )
            await update.message.reply_text(
                "<b>Я передал ваш вопрос оператору. Ожидайте ответа.</b>",
                parse_mode="HTML"
            )
            return

        # ===== Обычный ответ ИИ =====
        await update.message.reply_text(
            formatted_answer,
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
        print(e)

# ===== Обработка фото =====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # Получаем файл
    photo_file = await update.message.photo[-1].get_file()
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    file_path = f"{PHOTO_FOLDER}/{user_id}_{photo_file.file_id}.jpg"
    await photo_file.download_to_drive(file_path)

    # ===== Фото по запросу ИИ =====
    if awaiting_photo.get(user_id, False):
        operator_sessions[user_id] = True
        awaiting_photo[user_id] = False
        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=open(file_path, "rb"),
            caption=f"<b>Фото от пользователя {user_id} по запросу ИИ</b>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            "<b>Фото получено. Ваш вопрос будет обработан оператором.</b>",
            parse_mode="HTML"
        )
        return

    # ===== Фото в активной сессии оператора =====
    if user_id in operator_sessions:
        await context.bot.send_photo(
            chat_id=ADMIN_CHAT_ID,
            photo=open(file_path, "rb"),
            caption=f"<b>Фото от пользователя {user_id}</b>",
            parse_mode="HTML"
        )
        await update.message.reply_text(
            "<b>Спасибо! Фото получено. Оператор его увидит.</b>",
            parse_mode="HTML"
        )
        return

    # ===== Если фото пришло просто так =====
    await update.message.reply_text(
        "Спасибо! Какой у вас вопрос?",
        parse_mode="HTML"
    )

# ===== Команда администратора /reply =====
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_CHAT_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /reply user_id текст ответа")
        return

    try:
        user_id = int(context.args[0])
        message = " ".join(context.args[1:])

        if user_id not in operator_sessions:
            await update.message.reply_text("Этот пользователь не ожидает ответа оператора.")
            return

        await context.bot.send_message(
            chat_id=user_id,
            text=f"<b>Сообщение от оператора:</b>\n<blockquote>{message}</blockquote>",
            parse_mode="HTML"
        )

        await update.message.reply_text(f"Ответ отправлен пользователю {user_id}")

    except ValueError:
        await update.message.reply_text("user_id должен быть числом")

# ===== Команда администратора /done =====
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id != ADMIN_CHAT_ID:
        return

    if len(context.args) != 1:
        await update.message.reply_text("Использование: /done user_id")
        return

    try:
        user_id = int(context.args[0])

        if user_id not in operator_sessions:
            await update.message.reply_text("У этого пользователя нет активного диалога.")
            return

        # Удаляем пользователя из сессии оператора
        del operator_sessions[user_id]

        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "<b>Тема обращения закрыта.</b>\n"
                "Если у вас появятся новые вопросы, я с радостью помогу 🤖"
            ),
            parse_mode="HTML"
        )

        await update.message.reply_text(f"Диалог с пользователем {user_id} завершён.")

    except ValueError:
        await update.message.reply_text("user_id должен быть числом")

# ===== Запуск бота =====
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reply", reply))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_user_message))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))

    print("БОТ ЗАПУЩЕН!")
    app.run_polling()