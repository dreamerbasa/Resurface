from datetime import datetime, timedelta, timezone

from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
)

from config import TELEGRAM_BOT_TOKEN
from bot.capture_bot import (
    start, stop, remindertime, nudgetime, cancel, review,
    _receive_reminder_time, _receive_nudge_time,
    AWAITING_REMINDER_TIME, AWAITING_NUDGE_TIME,
    handle_text, handle_voice, handle_photo, handle_rating,
    handle_nudge_action, handle_nudge_list_tap,
)
from notifications.nightly_reminder import send_nightly_reminder
from notifications.daily_nudge import send_daily_nudge


def _seconds_until_next_boundary() -> float:
    now = datetime.now(timezone.utc)
    if now.minute < 30:
        next_boundary = now.replace(minute=30, second=0, microsecond=0)
    else:
        next_boundary = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    delay = (next_boundary - now).total_seconds()
    print(f"Jobs aligned to clock. First run in {delay:.0f} seconds at {next_boundary} UTC")
    return delay


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    reminder_conv = ConversationHandler(
        entry_points=[CommandHandler("remindertime", remindertime)],
        states={
            AWAITING_REMINDER_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_reminder_time),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    nudge_conv = ConversationHandler(
        entry_points=[CommandHandler("nudgetime", nudgetime)],
        states={
            AWAITING_NUDGE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_nudge_time),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(reminder_conv)
    app.add_handler(nudge_conv)
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
