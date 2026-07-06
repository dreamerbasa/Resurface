from datetime import datetime, timedelta

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import TELEGRAM_BOT_TOKEN
from bot.capture_bot import (
    start, stop, remindertime, nudgetime,
    handle_text, handle_voice, handle_photo, handle_rating,
    handle_nudge_action, handle_nudge_list_tap,
)
from notifications.nightly_reminder import send_nightly_reminder
from notifications.daily_nudge import send_daily_nudge


def _seconds_until_next_boundary() -> float:
    now = datetime.utcnow()
    if now.minute < 30:
        next_boundary = now.replace(minute=30, second=0, microsecond=0)
    else:
        next_boundary = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    delay = (next_boundary - now).total_seconds()
    print(f"Jobs aligned to clock. First run in {delay:.0f} seconds at {next_boundary} UTC")
    return delay


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("remindertime", remindertime))
    app.add_handler(CommandHandler("nudgetime", nudgetime))
    app.add_handler(CallbackQueryHandler(handle_nudge_list_tap, pattern="^nudgelist_"))
    app.add_handler(CallbackQueryHandler(handle_nudge_action, pattern="^nudge_(done|archive|remind|keep|drop|back)_"))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern="^(interest_|goal_)"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    delay = _seconds_until_next_boundary()

    app.job_queue.run_repeating(
        send_nightly_reminder,
        interval=1800,
        first=delay,
    )

    app.job_queue.run_repeating(
        send_daily_nudge,
        interval=1800,
        first=delay,
    )

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
