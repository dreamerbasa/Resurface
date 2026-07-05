import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS
from pipeline.router import process_message
from db.queries import (
    update_item_rating, get_item, upsert_user, get_user_by_telegram_id,
    update_last_active, set_user_active, update_reminder_time, update_nudge_time,
)


def _is_authorized(update: Update) -> bool:
    return update.effective_user.id in AUTHORIZED_USER_IDS


def _get_user_id(update: Update) -> str:
    update_last_active(update.effective_user.id)
    user = get_user_by_telegram_id(update.effective_user.id)
    if not user:
        user = upsert_user(
            telegram_user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            display_name=update.effective_user.first_name,
        )
    return user["id"]


_INTEREST_EMOJI = {3: "\U0001f525", 2: "\U0001f44d", 1: "\U0001f937"}
_GOAL_EMOJI = {3: "\U0001f3af", 2: "↔️", 1: "❌"}


def _rating_keyboard(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f525 High", callback_data=f"interest_3_{item_id}"),
            InlineKeyboardButton("\U0001f44d Medium", callback_data=f"interest_2_{item_id}"),
            InlineKeyboardButton("\U0001f937 Low", callback_data=f"interest_1_{item_id}"),
        ],
        [
            InlineKeyboardButton("\U0001f3af Aligned", callback_data=f"goal_3_{item_id}"),
            InlineKeyboardButton("↔️ Somewhat", callback_data=f"goal_2_{item_id}"),
            InlineKeyboardButton("❌ Nope", callback_data=f"goal_1_{item_id}"),
        ],
    ])


async def _send_save_response(message, result):
    if isinstance(result, list):
        saved = []
        skipped = []
        for r in result:
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
    user = get_user_by_telegram_id(update.effective_user.id)
    upsert_user(
        telegram_user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        display_name=update.effective_user.first_name,
    )
    if user:
        if not user.get("is_active"):
            set_user_active(update.effective_user.id, True)
        await update.message.reply_text(
            "Welcome back to Dropzone! \U0001f4e6 Nudges resumed.\n\n"
            "*Commands:*\n"
            "/review — see your pending items\n"
            "/categories — view your categories\n"
            "/search \\[keyword\\] — find saved items\n"
            "/stats — your numbers\n"
            "/nudgetime HH:MM — set morning nudge time\n"
            "/remindertime HH:MM — set nightly reminder time\n"
            "/stop — pause all nudges\n"
            "/start — resume nudges",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text(
            "Welcome to Dropzone! \U0001f4e6\n\n"
            "Your second brain. Dump everything, forget nothing.\n\n"
            "Send me anything — screenshots, links, voice notes, ideas — "
            "and I'll organize it, remember it, and remind you when it matters.\n\n"
            "*What I can handle:*\n"
            "\U0001f4f8 Screenshots — I read the text, ignore the clutter\n"
            "\U0001f517 Links — articles, YouTube, Substack\n"
            "\U0001f3a4 Voice notes — transcribed and categorized\n"
            "\U0001f4ac Text — ideas, thoughts, anything\n\n"
            "After each save, I'll ask you to rate:\n"
            "→ How interested are you?\n"
            "→ Does it align with your goals?\n\n"
            "*Commands:*\n"
            "/review — see your pending items\n"
            "/categories — view your categories\n"
            "/search \\[keyword\\] — find saved items\n"
            "/stats — your numbers\n"
            "/nudgetime HH:MM — set morning nudge time\n"
            "/remindertime HH:MM — set nightly reminder time\n"
            "/stop — pause all nudges\n"
            "/start — resume nudges\n\n"
            "Just start sharing. I'll handle the rest.",
            parse_mode="Markdown",
        )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    set_user_active(update.effective_user.id, False)
    await update.message.reply_text(
        "All nudges and reminders paused. Your saved items are safe. "
        "Send /start anytime to resume."
    )


async def remindertime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /remindertime HH:MM (e.g. /remindertime 22:00)")
        return
    time_str = context.args[0]
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        formatted = f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid time format. Use HH:MM (e.g. 22:00)")
        return
    update_reminder_time(update.effective_user.id, formatted)
    await update.message.reply_text(f"Nightly reminder set to {formatted}. I'll check in with you then.")


async def nudgetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /nudgetime HH:MM (e.g. /nudgetime 08:30)")
        return
    time_str = context.args[0]
    try:
        parts = time_str.split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
        formatted = f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        await update.message.reply_text("Invalid time format. Use HH:MM (e.g. 08:30)")
        return
    update_nudge_time(update.effective_user.id, formatted)
    await update.message.reply_text(f"Morning nudge set to {formatted}.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    user_id = _get_user_id(update)
    try:
        result = process_message(update.message.text, content_type="text", user_id=user_id)
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
    user_id = _get_user_id(update)
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
            user_id=user_id,
        )
        await _send_save_response(update.message, result)
    except Exception as e:
        await update.message.reply_text(f"Something went wrong: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    user_id = _get_user_id(update)
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
            user_id=user_id,
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
        i_emoji = _INTEREST_EMOJI.get(interest, "\U0001f44d")
        g_emoji = _GOAL_EMOJI.get(goal, "❌")
        await query.edit_message_text(f"Rated: {i_emoji} interest, {g_emoji} goal ✓")
    else:
        if rating_type == "interest":
            emoji = _INTEREST_EMOJI.get(value, "\U0001f44d")
        else:
            emoji = _GOAL_EMOJI.get(value, "❌")
        await query.edit_message_text(
            f"Got {emoji} — tap the other when you're ready",
            reply_markup=_rating_keyboard(item_id),
        )


def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("remindertime", remindertime))
    app.add_handler(CommandHandler("nudgetime", nudgetime))
    app.add_handler(CallbackQueryHandler(handle_rating))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running...")
    app.run_polling()
