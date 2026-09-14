import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")  # куда падают аварии и дайджест

# Кнопка "Обменять" ведёт сюда — основной бот МенялоФФ
EXCHANGE_URL = os.environ.get("EXCHANGE_URL", "https://t.me/USDT_X_RUB_BOT")

# Одно напоминание тем, кто застрял, не дойдя до обмена (в секундах)
REMINDER_DELAY_SEC = 24 * 60 * 60
