# -*- coding: utf-8 -*-
"""
Telegram-бот-магнит МенялоФФ: воронка для обмена USDT↔RUB.

Главный принцип: кнопка "Обменять сейчас" доступна с первого сообщения и на
каждом экране. Ничего не блокирует путь к ней.

Запуск: python bot.py  (см. README.md)
"""
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

import config
import db
import texts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def kb(rows):
    """rows: список списков (text, callback_data) или (text, url, "url") для ссылок."""
    def make_button(item):
        if len(item) == 3 and item[2] == "url":
            return InlineKeyboardButton(item[0], url=item[1])
        return InlineKeyboardButton(item[0], callback_data=item[1])
    return InlineKeyboardMarkup([[make_button(item) for item in row] for row in rows])


async def send_and_log(update_or_query, context, text, reply_markup=None, telegram_id=None):
    if telegram_id:
        db.log_history(telegram_id, f"bot: {text[:120]}")
    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=reply_markup)
    else:
        await context.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)


def welcome_buttons():
    return kb([
        [(texts.BTN_EXCHANGE_NOW, "exchange_now")],
        [(texts.BTN_BUY, "pick_buy")],
        [(texts.BTN_SELL, "pick_sell")],
        [(texts.BTN_DONT_KNOW, "dont_know")],
    ])


def direction_buttons(action_label, rate_label, direction, other_label, other_callback):
    return kb([
        [(action_label, f"exchange_now_{direction}")],
        [(rate_label, f"exchange_now_{direction}")],
        [(other_label, other_callback)],
    ])


# ---------------------------------------------------------------------------
# Точки входа
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    existing = db.get_or_create_user(user.id, user.username, user.first_name)

    if args and existing["source"] == "organic" and existing["current_step"] == "entry" and existing["stage"] == "новый":
        source = args[0] if args[0] in ("v1", "v2", "v3") else "organic"
        db.update_user(user.id, source=source)

    existing = db.get_or_create_user(user.id, user.username, user.first_name)

    if existing["stopped"]:
        db.update_user(user.id, stopped=0)

    if existing["current_step"] != "entry":
        await resume(update, context, existing)
        return

    db.log_history(user.id, "start")
    await update.message.reply_text(texts.WELCOME_TEXT, reply_markup=welcome_buttons())
    db.update_user(user.id, current_step="welcome_shown")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE, user_row):
    step = user_row["current_step"]
    telegram_id = user_row["telegram_id"]
    if step == "buy_shown":
        await send_buy(update, context, telegram_id)
    elif step == "sell_shown":
        await send_sell(update, context, telegram_id)
    else:
        await update.message.reply_text(texts.WELCOME_TEXT, reply_markup=welcome_buttons())
        db.update_user(telegram_id, current_step="welcome_shown")


async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)
    db.mark_stopped(user.id)
    await update.message.reply_text(texts.STOP_TEXT)


# ---------------------------------------------------------------------------
# Экраны направлений
# ---------------------------------------------------------------------------

async def send_buy(update_or_query, context, telegram_id):
    buttons = direction_buttons(
        texts.BTN_BUY_ACTION, texts.BTN_RATE_AND_BUY, "buy",
        texts.BTN_SELL, "pick_sell",
    )
    await send_and_log(update_or_query, context, texts.BUY_TEXT, buttons, telegram_id)
    db.update_user(telegram_id, direction="buy", current_step="buy_shown", stage="ответил")


async def send_sell(update_or_query, context, telegram_id):
    buttons = direction_buttons(
        texts.BTN_SELL_ACTION, texts.BTN_RATE_AND_SELL, "sell",
        texts.BTN_BUY, "pick_buy",
    )
    await send_and_log(update_or_query, context, texts.SELL_TEXT, buttons, telegram_id)
    db.update_user(telegram_id, direction="sell", current_step="sell_shown", stage="ответил")


# ---------------------------------------------------------------------------
# Callback-роутер
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    telegram_id = user.id
    row = db.get_or_create_user(telegram_id, user.username, user.first_name)
    if row["stopped"]:
        return

    db.log_history(telegram_id, f"user_click: {data}")

    if data == "pick_buy":
        await send_buy(query, context, telegram_id)

    elif data == "pick_sell":
        await send_sell(query, context, telegram_id)

    elif data == "dont_know":
        text_with_note = f"{texts.WHICH_DIRECTION_TEXT}\n\n{texts.WHICH_DIRECTION_CTA_NOTE}"
        buttons = kb([[(texts.BTN_EXCHANGE_NOW, "exchange_now")]])
        await query.message.reply_text(text_with_note, reply_markup=buttons)

    elif data in ("exchange_now", "exchange_now_buy", "exchange_now_sell"):
        db.log_exchange_click(telegram_id)
        db.update_user(telegram_id, stage="обмен", current_step="exchanged")
        buttons = kb([[("💱 Открыть МенялоФФ", config.EXCHANGE_URL, "url")]])
        await query.message.reply_text(
            "Жми кнопку ниже — откроется бот МенялоФФ, там выбираешь направление "
            "(купить/продать), вводишь сумму и реквизиты — обмен занимает пару минут.",
            reply_markup=buttons,
        )

    elif data == "trouble_menu":
        buttons = kb([
            [(texts.TROUBLE_BUTTONS["money_not_received"], "trouble_money_not_received")],
            [(texts.TROUBLE_BUTTONS["rate_mismatch"], "trouble_rate_mismatch")],
            [(texts.TROUBLE_BUTTONS["transfer_stuck"], "trouble_transfer_stuck")],
        ])
        await query.message.reply_text(texts.TROUBLE_MENU_TEXT, reply_markup=buttons)

    elif data in ("trouble_money_not_received", "trouble_rate_mismatch", "trouble_transfer_stuck"):
        etype = data.replace("trouble_", "")
        await query.message.reply_text(texts.TROUBLE_PROMPTS[etype])
        context.user_data["awaiting_trouble_type"] = etype


# ---------------------------------------------------------------------------
# Свободный текст: только аварийный канал (без каталога — тут не сервисы)
# ---------------------------------------------------------------------------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    row = db.get_or_create_user(telegram_id, user.username, user.first_name)
    if row["stopped"]:
        return

    text = update.message.text.strip()
    db.log_history(telegram_id, f"user_text: {text[:200]}")

    if context.user_data.get("awaiting_trouble_type"):
        etype = context.user_data.pop("awaiting_trouble_type")
        db.log_emergency(telegram_id, etype, text, row["source"], row["direction"])
        await update.message.reply_text("Принял, передал в приоритет.")
        if config.ADMIN_CHAT_ID:
            type_ru = texts.TROUBLE_BUTTONS[etype]
            alert = (
                "⚠️ АВАРИЯ\n"
                f"Тип: {type_ru}\n"
                f"Источник: {row['source']} / Направление {row['direction'] or '-'}\n"
                f"@{user.username or '-'} (ID: {telegram_id})\n"
                f"Текст: «{text}»"
            )
            await context.bot.send_message(chat_id=config.ADMIN_CHAT_ID, text=alert)
        return

    # Любой другой текст — не гадаем, просто показываем стартовый экран с CTA
    await update.message.reply_text(texts.WELCOME_TEXT, reply_markup=welcome_buttons())
    db.update_user(telegram_id, current_step="welcome_shown")


# ---------------------------------------------------------------------------
# Админ: счётчик проблем к переходам
# ---------------------------------------------------------------------------

async def admin_breakage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_chat.id) != str(config.ADMIN_CHAT_ID):
        return
    ratio = db.breakage_ratio()
    if ratio is None:
        await update.message.reply_text("Пока нет переходов на обмен — соотношение не посчитать.")
    else:
        await update.message.reply_text(f"Аварии / переходы на обмен: {ratio:.2%}")


# ---------------------------------------------------------------------------
# Периодическая задача: одно напоминание застрявшим
# ---------------------------------------------------------------------------

async def job_reminders(context: ContextTypes.DEFAULT_TYPE):
    with db.get_conn() as conn:
        cutoff = int(time.time()) - config.REMINDER_DELAY_SEC
        rows = conn.execute(
            "SELECT telegram_id FROM users WHERE stage='ответил' AND reminded=0 "
            "AND stopped=0 AND first_seen <= ?",
            (cutoff,),
        ).fetchall()
    for r in rows:
        try:
            await context.bot.send_message(chat_id=r["telegram_id"], text=texts.REMINDER_TEXT)
        except Exception as e:
            log.warning("Reminder failed for %s: %s", r["telegram_id"], e)
        db.update_user(r["telegram_id"], reminded=1)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    if not config.BOT_TOKEN:
        raise RuntimeError("Задайте BOT_TOKEN в переменных окружения")

    db.init_db()

    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_cmd))
    app.add_handler(CommandHandler("breakage", admin_breakage))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    if app.job_queue:
        app.job_queue.run_repeating(job_reminders, interval=60 * 60, first=120)

    log.info("Бот-магнит запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
