from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.queries import get_active_users, update_after_surface
from intelligence.scoring import get_daily_items


def _current_window_minutes() -> tuple[int, int]:
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    total_minutes = now_ist.hour * 60 + now_ist.minute
    window_start_minutes = (total_minutes // 30) * 30
    window_end_minutes = window_start_minutes + 29
    return window_start_minutes, window_end_minutes


def _build_keyboard(item: dict) -> InlineKeyboardMarkup:
    item_id = item["id"]

    if item.get("is_escalation"):
        buttons = [
            [
                InlineKeyboardButton("Keep", callback_data=f"nudge_keep_{item_id}"),
                InlineKeyboardButton("Drop", callback_data=f"nudge_drop_{item_id}"),
            ]
        ]
    else:
        row = [
            InlineKeyboardButton("Archive", callback_data=f"nudge_archive_{item_id}"),
            InlineKeyboardButton("Remind later", callback_data=f"nudge_remind_{item_id}"),
            InlineKeyboardButton("Done", callback_data=f"nudge_done_{item_id}"),
        ]
        buttons = [row]
        if item.get("url"):
            buttons.append([InlineKeyboardButton("Open link", url=item["url"])])

    return InlineKeyboardMarkup(buttons)


def _format_item_text(item: dict) -> str:
    line = f"{item['emoji']} *{item['title']}* · {item['category_name']} · {item['age_days']:.0f}d ago"
    if item.get("is_escalation"):
        line += f"\n⚠️ You've seen this {item['times_surfaced']} times. Keep or drop?"
    return line


async def send_daily_nudge(context):
    print(f"Nudge check running at {datetime.utcnow()} UTC")

    window_start_minutes, window_end_minutes = _current_window_minutes()
    window_start_h, window_start_m = divmod(window_start_minutes, 60)
    window_end_h, window_end_m = divmod(window_end_minutes, 60)
    users = get_active_users()
    print(f"Active users found: {len(users)}")

    any_match = False

    for user in users:
        user_nudge = user.get("nudge_time", "08:30")
        nudge_parts = user_nudge.split(":")
        nudge_h, nudge_m = int(nudge_parts[0]), int(nudge_parts[1])
        user_minutes = nudge_h * 60 + nudge_m
        is_match = window_start_minutes <= user_minutes <= window_end_minutes
        print(
            f"User {user['display_name']}: nudge_time={user_nudge}, "
            f"current_window={window_start_h:02d}:{window_start_m:02d}-{window_end_h:02d}:{window_end_m:02d}, "
            f"match={is_match}"
        )
        if not is_match:
            continue

        any_match = True

        result = get_daily_items(user["id"])
        items = result.get("items", [])
        if not items:
            continue

        chat_id = user["chat_id"]

        if result.get("is_first_week"):
            header = "Getting started — here are your items to look at:"
        elif result.get("is_weekend_catchup"):
            header = (
                f"\U0001f4e6 Weekend catch-up — you have {result['total_pending']} unseen items\n\n"
                f"Top {len(items)} to review:"
            )
        else:
            header = f"☀️ Your {len(items)} item{'s' if len(items) != 1 else ''} for today"

        try:
            await context.bot.send_message(chat_id=chat_id, text=header)
        except Exception:
            continue

        for item in items:
            text = _format_item_text(item)
            keyboard = _build_keyboard(item)
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                update_after_surface(item["id"])
            except Exception:
                pass

        print(f"Sent {len(items)} nudge items to {user['display_name']}")

    if not any_match:
        print("No users matched current time window")
