import io
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, ConversationHandler, filters,
)

from config import TELEGRAM_BOT_TOKEN, AUTHORIZED_USER_IDS
from pipeline.router import process_message
from db.queries import (
    update_item_rating, get_item, upsert_user, get_user_by_telegram_id,
    update_last_active, set_user_active, update_reminder_time, update_nudge_time,
    archive_item, done_item, remind_later, keep_item, get_image_bytes,
    get_pending_items,
)
from intelligence.scoring import _get_emoji, _extract_url, _PRIORITY_MATRIX
from notifications.daily_nudge import build_list_view, build_detail_view, escape_html, _list_line
from notifications.nudge_session import get_session, set_session
from notifications.pinned_queue import update_pinned_queue


def _is_authorized(update: Update) -> bool:
    return update.effective_user.id in AUTHORIZED_USER_IDS


async def _update_pinned(bot, telegram_user_id: int):
    user = get_user_by_telegram_id(telegram_user_id)
    if user:
        try:
            await update_pinned_queue(bot, user)
        except Exception as e:
            print(f"Pinned queue update error: {e}")


def _get_user_id(update: Update) -> str:
    update_last_active(update.effective_user.id)
    user = get_user_by_telegram_id(update.effective_user.id)
    if not user:
        user = upsert_user(
            telegram_user_id=update.effective_user.id,
            chat_id=update.effective_chat.id,
            display_name=update.effective_user.first_name,
        )
    if not user:
        raise ValueError("Could not create or find user")
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


def _truncate(text: str, limit: int = 3500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "... (truncated)"


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
            await message.reply_text(_truncate("\n".join(lines)))

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
            "<b>Commands:</b>\n"
            "/review — see your pending items\n"
            "/categories — view your categories\n"
            "/search [keyword] — find saved items\n"
            "/stats — your numbers\n"
            "/nudgetime HH:MM — set morning nudge time (on the hour or half hour)\n"
            "/remindertime HH:MM — set nightly reminder time (on the hour or half hour)\n"
            "/stop — pause all nudges\n"
            "/start — resume nudges",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "Welcome to Dropzone! \U0001f4e6\n\n"
            "Your second brain. Dump everything, forget nothing.\n\n"
            "Send me anything — screenshots, links, voice notes, ideas — "
            "and I'll organize it, remember it, and remind you when it matters.\n\n"
            "<b>What I can handle:</b>\n"
            "\U0001f4f8 Screenshots — I read the text, ignore the clutter\n"
            "\U0001f517 Links — articles, YouTube, Substack\n"
            "\U0001f3a4 Voice notes — transcribed and categorized\n"
            "\U0001f4ac Text — ideas, thoughts, anything\n\n"
            "After each save, I'll ask you to rate:\n"
            "→ How interested are you?\n"
            "→ Does it align with your goals?\n\n"
            "<b>Commands:</b>\n"
            "/review — see your pending items\n"
            "/categories — view your categories\n"
            "/search [keyword] — find saved items\n"
            "/stats — your numbers\n"
            "/nudgetime HH:MM — set morning nudge time (on the hour or half hour)\n"
            "/remindertime HH:MM — set nightly reminder time (on the hour or half hour)\n"
            "/stop — pause all nudges\n"
            "/start — resume nudges\n\n"
            "Just start sharing. I'll handle the rest.",
            parse_mode="HTML",
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


AWAITING_REMINDER_TIME, AWAITING_NUDGE_TIME = range(2)

_TIME_INVALID_MSG = "That doesn't look right. Send a time like 08:00 or 08:30"


def _parse_time(time_str: str) -> str | None:
    try:
        parts = time_str.strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and m in (0, 30)):
            return None
        return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        return None


async def remindertime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return ConversationHandler.END
    if context.args:
        formatted = _parse_time(context.args[0])
        if not formatted:
            await update.message.reply_text(
                "Invalid time. Use HH:MM on the hour or half hour (e.g. 22:00, 22:30)"
            )
            return ConversationHandler.END
        update_reminder_time(update.effective_user.id, formatted)
        await update.message.reply_text(f"Nightly reminder set to {formatted} ✓")
        return ConversationHandler.END

    await update.message.reply_text(
        "What time should I send your nightly reminder?\n\n"
        "Send the time in HH:MM format (on the hour or half hour).\n"
        "Examples: 21:00, 21:30, 22:00"
    )
    return AWAITING_REMINDER_TIME


async def _receive_reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    formatted = _parse_time(update.message.text)
    if not formatted:
        await update.message.reply_text(_TIME_INVALID_MSG)
        return AWAITING_REMINDER_TIME
    update_reminder_time(update.effective_user.id, formatted)
    await update.message.reply_text(f"Nightly reminder set to {formatted} ✓")
    return ConversationHandler.END


async def nudgetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return ConversationHandler.END
    if context.args:
        formatted = _parse_time(context.args[0])
        if not formatted:
            await update.message.reply_text(
                "Invalid time. Use HH:MM on the hour or half hour (e.g. 08:00, 08:30)"
            )
            return ConversationHandler.END
        update_nudge_time(update.effective_user.id, formatted)
        await update.message.reply_text(f"Morning nudge set to {formatted} ✓")
        return ConversationHandler.END

    await update.message.reply_text(
        "What time should I send your morning nudge?\n\n"
        "Send the time in HH:MM format (on the hour or half hour).\n"
        "Examples: 08:00, 08:30, 09:00"
    )
    return AWAITING_NUDGE_TIME


async def _receive_nudge_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    formatted = _parse_time(update.message.text)
    if not formatted:
        await update.message.reply_text(_TIME_INVALID_MSG)
        return AWAITING_NUDGE_TIME
    update_nudge_time(update.effective_user.id, formatted)
    await update.message.reply_text(f"Morning nudge set to {formatted} ✓")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def _format_review_item(item: dict, now) -> dict:
    from dateutil.parser import isoparse
    created_at = isoparse(item["created_at"]) if isinstance(item.get("created_at"), str) else item.get("created_at", now)
    age_days = round((now - created_at).total_seconds() / 86400, 1)
    times_surfaced = item.get("times_surfaced", 0)
    interest = item.get("interest", 2)
    goal = item.get("goal_alignment", 1)
    return {
        "id": item["id"],
        "title": item.get("title") or "Untitled",
        "summary": item.get("summary"),
        "category_name": item.get("category_name"),
        "interest": interest,
        "goal_alignment": goal,
        "age_days": age_days,
        "times_surfaced": times_surfaced,
        "is_escalation": times_surfaced >= 3,
        "emoji": _get_emoji(item),
        "url": _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None,
        "content_type": item.get("content_type"),
        "raw_content": item.get("raw_content"),
        "extracted_text": item.get("extracted_text"),
        "image_path": item.get("image_path"),
        "_weight": _PRIORITY_MATRIX.get((interest, goal), 1),
    }


async def review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("Sorry, this is a private bot.")
        return
    user_id = _get_user_id(update)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    days = None
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /review or /review 7 (number of days)")
            return

    raw_items = get_pending_items(user_id, days=days)
    if not raw_items:
        await update.message.reply_text("Nothing pending! You're all caught up. 🎉")
        return

    formatted = [_format_review_item(item, now) for item in raw_items]
    formatted.sort(key=lambda x: (-int(x["times_surfaced"] == 0), -x["_weight"]))

    total = len(formatted)
    display_items = formatted[:10]

    if days:
        header = f"📋 Items from the last {days} days — {total} pending"
    else:
        header = f"📋 Your review queue — {total} item{'s' if total != 1 else ''} pending"

    set_session(update.effective_chat.id, display_items, header)
    session = get_session(update.effective_chat.id)
    text, _ = build_list_view(session)

    if total > 10:
        text += f"\n\nShowing 10 of {total}. Use /review 7 to filter by recent days."

    button_items = display_items[:5]
    row1 = []
    row2 = []
    for idx, item in enumerate(button_items, start=1):
        btn = InlineKeyboardButton(f"  {idx}  ", callback_data=f"nudgelist_{item['id']}")
        if idx <= 3:
            row1.append(btn)
        else:
            row2.append(btn)
    rows = [row1]
    if row2:
        rows.append(row2)
    keyboard = InlineKeyboardMarkup(rows)

    await update.message.reply_text(
        _truncate(text),
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


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
        await _update_pinned(context.bot, update.effective_user.id)
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
        await _update_pinned(context.bot, update.effective_user.id)
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
        await _update_pinned(context.bot, update.effective_user.id)
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


_EXPIRED_NUDGE_TEXT = "This nudge has expired. You'll get a fresh one next time!"

_NUDGE_ACTIONS = {
    "done": (done_item, "✅ {title} — marked as done", "done"),
    "archive": (archive_item, "📦 {title} — archived", "archived"),
    "remind": (lambda item_id: remind_later(item_id, days=3), "⏰ {title} — I'll remind you in 3 days", "remind"),
    "keep": (keep_item, "🔖 {title} — keeping it, back in 7 days", "kept"),
    "drop": (archive_item, "📦 {title} — dropped", "archived"),
}


async def _render_nudge_list(query, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    session = get_session(chat_id)
    if not session:
        text, keyboard = _EXPIRED_NUDGE_TEXT, None
    else:
        text, keyboard = build_list_view(session)

    if query.message.photo:
        try:
            await query.message.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=keyboard,
            parse_mode="HTML", disable_web_page_preview=True,
        )
    else:
        await query.edit_message_text(
            text=text, reply_markup=keyboard,
            parse_mode="HTML", disable_web_page_preview=True,
        )


async def handle_nudge_list_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.callback_query.answer("Not authorized.")
        return
    query = update.callback_query
    await query.answer()

    item_id = query.data.split("_", 1)[1]
    chat_id = query.message.chat_id
    session = get_session(chat_id)
    if not session or item_id not in session["items"]:
        await query.edit_message_text(_EXPIRED_NUDGE_TEXT)
        return

    item = session["items"][item_id]
    text, keyboard = build_detail_view(item)

    if item.get("content_type") == "image":
        image_bytes = get_image_bytes(item["image_path"]) if item.get("image_path") else None
        try:
            await query.message.delete()
        except Exception:
            pass
        if image_bytes:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=io.BytesIO(image_bytes),
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{text}\n\n<i>Original screenshot no longer available.</i>",
                reply_markup=keyboard,
                parse_mode="HTML", disable_web_page_preview=True,
            )
    else:
        await query.edit_message_text(
            text=text, reply_markup=keyboard,
            parse_mode="HTML", disable_web_page_preview=True,
        )


async def handle_nudge_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.callback_query.answer("Not authorized.")
        return
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_", 2)
    action = parts[1]
    chat_id = query.message.chat_id

    if action == "back":
        await _render_nudge_list(query, context, chat_id)
        return

    item_id = parts[2]
    meta = _NUDGE_ACTIONS.get(action)
    if meta is None:
        return
    fn, confirm_template, acted_status = meta

    fn(item_id)

    session = get_session(chat_id)
    if session and item_id in session["items"]:
        session["acted"][item_id] = acted_status

    try:
        await _render_nudge_list(query, context, chat_id)
    except Exception as e:
        if "not modified" not in str(e).lower():
            print(f"Edit error: {e}")

    await _update_pinned(context.bot, update.effective_user.id)


def run_bot():
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
    print("Bot is running...")
    app.run_polling()
