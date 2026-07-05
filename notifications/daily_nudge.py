from datetime import datetime, timezone, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from db.queries import get_active_users, update_after_surface
from intelligence.scoring import get_daily_items
from notifications.nudge_session import set_session, get_session


_ACTED_MARKER = {
    "done": ("✅", "done"),
    "archived": ("📦", "archived"),
    "kept": ("🔖", "kept, back in 7 days"),
    "remind": ("⏰", "remind in 3 days"),
}


def escape_html(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _current_window_minutes() -> tuple[int, int]:
    now_ist = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    total_minutes = now_ist.hour * 60 + now_ist.minute
    window_start_minutes = (total_minutes // 30) * 30
    window_end_minutes = window_start_minutes + 29
    return window_start_minutes, window_end_minutes


def _list_line(number: int, item: dict) -> str:
    has_url = bool(item.get("url"))
    title = escape_html(item["title"])
    title_display = f"<a href='{escape_html(item['url'])}'>{title}</a>" if has_url else title
    arrow = " ↗" if has_url else ""
    category = escape_html(item["category_name"])
    return (
        f"{number}. {item['emoji']} {title_display}{arrow}\n"
        f"   {category} · {item['age_days']:.0f}d ago"
    )


def build_list_view(session: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    order = session["order"]
    items = session["items"]
    acted = session["acted"]

    pending_ids = [item_id for item_id in order if item_id not in acted]
    if not pending_ids:
        return "☀️ All done for today! 🎉", None

    lines = [session["header"], ""]
    number_buttons = []
    for idx, item_id in enumerate(order, start=1):
        item = items[item_id]
        if item_id in acted:
            marker, word = _ACTED_MARKER.get(acted[item_id], ("✅", "done"))
            lines.append(f"{idx}. {marker} {escape_html(item['title'])} — {word}")
        else:
            lines.append(_list_line(idx, item))
            number_buttons.append(
                InlineKeyboardButton(f"  {idx}  ", callback_data=f"nudgelist_{item_id}")
            )

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup([number_buttons]) if number_buttons else None
    return text, keyboard


def _detail_body(item: dict) -> str:
    title = escape_html(item["title"])
    content_type = item.get("content_type")
    if content_type == "url":
        header_line = f"{item['emoji']} <a href='{escape_html(item['url'])}'>{title}</a>"
        content = escape_html(item.get("summary") or "")
    elif content_type == "voice":
        header_line = f"{item['emoji']} {title}"
        content = f"🎤 Transcription:\n{escape_html(item.get('extracted_text') or '')}"
    elif content_type == "image":
        header_line = f"{item['emoji']} {title}"
        content = escape_html((item.get("extracted_text") or "")[:500])
    else:
        header_line = f"{item['emoji']} {title}"
        content = escape_html(item.get("raw_content") or "")

    meta_line = f"{escape_html(item['category_name'])} · {item['age_days']:.0f}d ago"
    return f"{header_line}\n{meta_line}\n\n{content}"


def _detail_keyboard(item: dict) -> InlineKeyboardMarkup:
    item_id = item["id"]
    if item["is_escalation"]:
        rows = [
            [
                InlineKeyboardButton("Keep — remind in 7 days", callback_data=f"nudge_keep_{item_id}"),
                InlineKeyboardButton("Drop — archive it", callback_data=f"nudge_drop_{item_id}"),
            ],
        ]
    else:
        rows = [
            [
                InlineKeyboardButton("✅ Done", callback_data=f"nudge_done_{item_id}"),
                InlineKeyboardButton("📦 Archive", callback_data=f"nudge_archive_{item_id}"),
                InlineKeyboardButton("⏰ Later", callback_data=f"nudge_remind_{item_id}"),
            ],
        ]
    rows.append([InlineKeyboardButton("← Back to list", callback_data=f"nudge_back_{item_id}")])
    return InlineKeyboardMarkup(rows)


def build_detail_view(item: dict) -> tuple[str, InlineKeyboardMarkup]:
    return _detail_body(item), _detail_keyboard(item)


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

        print(f"Time matched for {user['display_name']}, fetching nudge items...")

        try:
            result = get_daily_items(user["id"])
            print(f"get_daily_items returned: {len(result.get('items', []))} items")
            items = result.get("items", [])
            if not items:
                print(f"No items to nudge for {user['display_name']}")
                continue

            chat_id = user["chat_id"]

            if result.get("is_first_week"):
                header = "Getting started — here are your items to look at:"
            elif result.get("is_weekend_catchup"):
                header = f"📦 Weekend catch-up — you have {result['total_pending']} unseen items"
            else:
                header = f"☀️ Your {len(items)} items for today"

            set_session(chat_id, items, header)
            text, keyboard = build_list_view(get_session(chat_id))

            await context.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML"
            )

            for item in items:
                update_after_surface(item["id"])

            print(f"Sent {len(items)} nudge items to {user['display_name']}")
            print(f"Successfully sent nudge to {user['display_name']}")
        except Exception as e:
            print(f"ERROR sending nudge to {user['display_name']}: {type(e).__name__}: {e}")

    if not any_match:
        print("No users matched current time window")
