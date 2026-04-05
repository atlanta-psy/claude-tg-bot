"""
Telegram-бот, который общается с Claude AI.
Загружает контекст о Лене из GitHub-репозитория.
"""

import os
import logging
import httpx
from anthropic import AsyncAnthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TG_TOKEN = os.environ["TG_TOKEN"]
CLAUDE_API_KEY = os.environ["CLAUDE_API_KEY"]
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", "0"))

GITHUB_RAW = "https://raw.githubusercontent.com/atlanta-psy/elena-claude-context/main"
CONTEXT_FILES = [
    "CLAUDE.md",
    "ПАСПОРТ_БРЕНДА.md",
    "ЭКСПЕРТИЗА.md",
    "СТИЛЬ_РЕЧИ.md",
    "СТИЛЬ_ТЕКСТА.md",
    "СТРАТЕГИЯ_ПРОДУКТОВ.md",
    "карточка клиента клауд.md",
    "БОТЫ_И_АВТОМАТИЗАЦИЯ.md",
]

client = AsyncAnthropic(api_key=CLAUDE_API_KEY)

# История сообщений по каждому пользователю (сбрасывается при рестарте)
histories: dict[int, list] = {}


def load_context() -> str:
    """Загружает файлы контекста с GitHub."""
    parts = []
    for filename in CONTEXT_FILES:
        url = f"{GITHUB_RAW}/{httpx.URL(filename)}"
        try:
            r = httpx.get(url, timeout=15, follow_redirects=True)
            if r.status_code == 200:
                parts.append(f"## {filename}\n\n{r.text}")
                log.info(f"Загружен: {filename}")
            else:
                log.warning(f"Не удалось загрузить {filename}: {r.status_code}")
        except Exception as e:
            log.warning(f"Ошибка при загрузке {filename}: {e}")
    return "\n\n---\n\n".join(parts)


log.info("Загружаю контекст с GitHub...")
SYSTEM_PROMPT = f"""Ты — персональный ИИ-ассистент Лены Василенко. Помогаешь ей с задачами: написать текст, разобраться с ботами и автоматизацией, ответить на вопросы, придумать контент.

Ниже — полный контекст о Лене, её проекте и инструментах. Используй его в работе.

{load_context()}

---

Правила работы:
- Отвечай на русском языке
- Будь конкретным и практичным
- Если задача большая — разбивай на шаги
- Если нужна уточняющая информация — спрашивай
"""
log.info("Контекст загружен!")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        return
    histories[user_id] = []
    await update.message.reply_text(
        "Привет! Я Клод, твой ИИ-ассистент 👋\n\n"
        "Пиши задание — помогу с текстами, ботами, контентом, автоматизацией — всем, что нужно.\n\n"
        "/clear — очистить историю разговора"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        return
    histories[user_id] = []
    await update.message.reply_text("История очищена ✅")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        log.warning(f"Отклонён незнакомый пользователь: {user_id}")
        return

    user_text = update.message.text
    if not user_text:
        return

    # Добавляем сообщение в историю
    if user_id not in histories:
        histories[user_id] = []
    histories[user_id].append({"role": "user", "content": user_text})

    # Ограничиваем историю последними 20 сообщениями
    if len(histories[user_id]) > 20:
        histories[user_id] = histories[user_id][-20:]

    await update.message.chat.send_action("typing")

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=histories[user_id],
        )
        reply = response.content[0].text

        # Сохраняем ответ в историю
        histories[user_id].append({"role": "assistant", "content": reply})

        # Telegram ограничивает сообщение 4096 символами — разбиваем если нужно
        if len(reply) <= 4096:
            await update.message.reply_text(reply)
        else:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(reply[i:i+4096])

    except Exception as e:
        log.error(f"Ошибка Claude API: {e}")
        await update.message.reply_text("Что-то пошло не так, попробуй ещё раз 🙏")


def main():
    app = Application.builder().token(TG_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    log.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message"])


if __name__ == "__main__":
    main()
