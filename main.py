import logging

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

from datetime import datetime, timedelta, timezone

from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, filters,
)

from config import TELEGRAM_BOT_TOKEN, SENDGRID_API_KEY, FROM_EMAIL
from bot.capture_bot import (
    start, stop, remindertime, nudgetime, email, cancel, review,
    categories, search, stats,
    _receive_reminder_time, _receive_nudge_time, _receive_email,
    _receive_search_keyword,
    AWAITING_REMINDER_TIME, AWAITING_NUDGE_TIME, AWAITING_EMAIL,
    AWAITING_SEARCH_KEYWORD,
    handle_text, handle_voice, handle_photo, handle_rating,
    handle_nudge_action, handle_nudge_list_tap, handle_remind_tonight,
    handle_go_deep, handle_review_page, handle_search_page,
)
from notifications.nightly_reminder import send_nightly_reminder
from notifications.daily_nudge import send_daily_nudge
from notifications.weekly_digest import send_weekly_digest


logger = logging.getLogger(__name__)


def _seconds_until_next_boundary() -> float:
    now = datetime.now(timezone.utc)
    if now.minute < 30:
        next_boundary = now.replace(minute=30, second=0, microsecond=0)
    else:
        next_boundary = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    delay = (next_boundary - now).total_seconds()
    logger.info(f"Jobs aligned to clock. First run in {delay:.0f} seconds at {next_boundary} UTC")
    return delay


def main():
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set — weekly digest emails will not send")
    if not FROM_EMAIL:
        logger.warning("FROM_EMAIL not set — weekly digest emails will not send")

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

    email_conv = ConversationHandler(
        entry_points=[CommandHandler("email", email)],
        states={
            AWAITING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_email),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    search_conv = ConversationHandler(
        entry_points=[CommandHandler("search", search)],
        states={
            AWAITING_SEARCH_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, _receive_search_keyword),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(CommandHandler("categories", categories))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(reminder_conv)
    app.add_handler(nudge_conv)
    app.add_handler(email_conv)
    app.add_handler(search_conv)
    app.add_handler(CallbackQueryHandler(handle_search_page, pattern="^search_(more|prev)_"))
    app.add_handler(CallbackQueryHandler(handle_review_page, pattern="^review_(more|prev)_"))
    app.add_handler(CallbackQueryHandler(handle_nudge_list_tap, pattern="^nudgelist_"))
    app.add_handler(CallbackQueryHandler(handle_go_deep, pattern="^nudge_godeep_"))
    app.add_handler(CallbackQueryHandler(handle_nudge_action, pattern="^nudge_(done|archive|remind|keep|drop|back)_"))
    app.add_handler(CallbackQueryHandler(handle_remind_tonight, pattern="^remind_tonight_"))
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

    app.job_queue.run_repeating(
        send_weekly_digest,
        interval=1800,
        first=delay,
    )

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
