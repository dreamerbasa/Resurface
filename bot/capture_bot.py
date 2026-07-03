from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from config import TELEGRAM_BOT_TOKEN
from pipeline.router import process_message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! I'm your Resurface bot. Send me anything — "
        "ideas, links, screenshots, voice notes — and I'll "
        "organize it for you."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        result = process_message(update.message.text, content_type="text")
        if result.get("status") == "needs_screenshot":
            await update.message.reply_text(result["message"])
            return
        tags = ", ".join(result["tags"])
        await update.message.reply_text(
            f"Saved under {result['category_name']}: {result['title']}\n\nTags: {tags}"
        )
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")


def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running...")
    app.run_polling()
