import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS
from pipeline.router import process_message
from db.queries import update_item_rating, get_item


def _is_authorized(update: Update) -> bool:
    return update.effective_user.id in AUTHORIZED_USER_IDS

_INTEREST_EMOJI = {3: "🔥", 2: "👍", 1: "🤷"}
_GOAL_EMOJI = {3: "🎯", 2: "↔️", 1: "❌"}


def _rating_keyboard(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔥 High", callback_data=f"interest_3_{item_id}"),
            InlineKeyboardButton("👍 Medium", callback_data=f"interest_2_{item_id}"),
            InlineKeyboardButton("🤷 Low", callback_data=f"interest_1_{item_id}"),
        ],
        [
            InlineKeyboardButton("🎯 Aligned", callback_data=f"goal_3_{item_id}"),
            InlineKeyboardButton("↔️ Somewhat", callback_data=f"goal_2_{item_id}"),
            InlineKeyboardButton("❌ Nope", callback_data=f"goal_1_{item_id}"),
        ],
    ])


async def _send_save_response(message, result):
    if isinstance(result, list):
        saved = []
        skipped = []
        for i, r in enumerate(result, 1):
            if r.get("status") == "needs_screenshot":
                skipped.append(r["message"])
            else:
                saved.append(r)

        if saved:
            lines = [f"Saved {len(saved)} item{'s' if len(saved) > 1 else ''}:"]
            for i, r in enumerate(saved, 1):
                lines.append(f"{i}. {r['category_name']}: {r['title']}")
            await message.reply_text("\n".join(lines))

            for r in saved:
                await message.reply_text(
                    f"Rate: {r['title']}",
                    reply_markup=_rating_keyboard(r["item_id"]),
                )

        for msg in skipped:
            await message.reply_text(msg)
        return

    tags = ", ".join(result["tags"])
    await message.reply_text(
        f"Saved under {result['category_name']}: {result['title']}\n\nTags: {tags}"
    )
    await message.reply_text(
        "Interest level? / Goal alignment?",
        reply_markup=_rating_keyboard(result["item_id"]),
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    await update.message.reply_text(
        "Hey! I'm your Resurface bot. Send me anything — "
        "ideas, links, screenshots, voice notes — and I'll "
        "organize it for you."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    try:
        result = process_message(update.message.text, content_type="text")
        if isinstance(result, dict) and result.get("status") == "needs_screenshot":
            await update.message.reply_text(result["message"])
            return
        await _send_save_response(update.message, result)
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
        tmp.close()
        await file.download_to_drive(tmp.name)

        result = process_message(
            raw_content="",
            content_type="voice",
            file_path=tmp.name,
        )
        await _send_save_response(update.message, result)
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.close()
        await file.download_to_drive(tmp.name)

        caption = update.message.caption or ""
        result = process_message(
            raw_content=caption,
            content_type="image",
            file_path=tmp.name,
        )
        await _send_save_response(update.message, result)
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")


async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.callback_query.answer("Not authorized.")
        return
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    rating_type = parts[0]
    value = int(parts[1])
    item_id = parts[2]

    if rating_type == "interest":
        update_item_rating(item_id, "interest", value)
    elif rating_type == "goal":
        update_item_rating(item_id, "goal_alignment", value)

    item = get_item(item_id)
    if not item:
        await query.edit_message_text("Could not find item.")
        return

    interest = item.get("interest")
    goal = item.get("goal_alignment")
    interest_changed = interest is not None and interest != 2
    goal_changed = goal is not None and goal != 1

    if rating_type == "interest":
        interest_changed = True
    if rating_type == "goal":
        goal_changed = True

    if interest_changed and goal_changed:
        i_emoji = _INTEREST_EMOJI.get(interest, "👍")
        g_emoji = _GOAL_EMOJI.get(goal, "❌")
        await query.edit_message_text(f"Rated: {i_emoji} interest, {g_emoji} goal ✓")
    else:
        if rating_type == "interest":
            emoji = _INTEREST_EMOJI.get(value, "👍")
        else:
            emoji = _GOAL_EMOJI.get(value, "❌")
        await query.edit_message_text(
            f"Got {emoji} — tap the other when you're ready",
            reply_markup=_rating_keyboard(item_id),
        )


def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_rating))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running...")
    app.run_polling()
