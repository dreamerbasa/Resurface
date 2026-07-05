import datetime

import pytz
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import TELEGRAM_BOT_TOKEN
from bot.capture_bot import (
    start, stop, remindertime, nudgetime,
    handle_text, handle_voice, handle_photo, handle_rating, handle_nudge_action,
)
from notifications.nightly_reminder import send_nightly_reminder
from notifications.daily_nudge import send_daily_nudge


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("remindertime", remindertime))
    app.add_handler(CommandHandler("nudgetime", nudgetime))
    app.add_handler(CallbackQueryHandler(handle_nudge_action, pattern="^nudge_"))
    app.add_handler(CallbackQueryHandler(handle_rating))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.job_queue.run_repeating(
        send_nightly_reminder,
        interval=datetime.timedelta(minutes=30),
        first=datetime.timedelta(seconds=10),
    )

    app.job_queue.run_repeating(
        send_daily_nudge,
        interval=datetime.timedelta(minutes=30),
        first=datetime.timedelta(seconds=15),
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
