import logging
from datetime import datetime, timezone, timedelta

from config import openai_client, SENDGRID_API_KEY, FROM_EMAIL
from db.queries import (
    get_active_users, get_user_stats, get_go_deep_items,
    clear_go_deep_flags,
    mark_items_in_digest, get_digest_pending_items, get_items_saved_since,
    get_skipped_this_week, get_never_surfaced,
)
from intelligence.clustering import cluster_items
from intelligence.scoring import _extract_url
from notifications.digest_template import build_digest_html, build_followup_html

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


def _current_window_minutes() -> tuple[int, int]:
    now_ist = datetime.now(IST)
    total_minutes = now_ist.hour * 60 + now_ist.minute
    window_start = (total_minutes // 30) * 30
    return window_start, window_start + 29


def _digest_day() -> str | None:
    weekday = datetime.now(IST).weekday()
    if weekday == 5:
        return "saturday"
    if weekday == 6:
        return "sunday"
    return None


def _generate_deep_dive(extracted_text: str, title: str = "", category_name: str = "") -> str:
    if not openai_client or not extracted_text:
        return ""
    try:
        user_prompt = (
            f"Category: {category_name}\n"
            f"Title: {title}\n"
            f"Content: {extracted_text[:8000]}\n\n"
            "Based on the category, provide the most useful deep dive:\n\n"
            "If article/book: Summarize the key arguments in detail. "
            "What's the core thesis? What evidence or examples does it use? "
            "What are potential counterpoints? What should the reader take away?\n\n"
            "If job posting: What skills and experience does this need? "
            "What kind of person are they looking for? What should someone prep to apply? "
            "What questions should they ask in the interview?\n\n"
            "If business idea: What's the market opportunity? Who's already doing something similar? "
            "What are the biggest risks? What would a first step look like?\n\n"
            "If recipe: Break down the technique. What are the tricky parts? "
            "What substitutions work? Any tips for someone making this the first time?\n\n"
            "If poem/creative writing: What themes are at play? What similar works explore this? "
            "How could this be expanded or developed further?\n\n"
            "If random thought/other: Expand on this idea. What are the implications? "
            "What related concepts connect to it? What would exploring this further look like?\n\n"
            "Keep it under 300 words. Be specific, not generic."
        )
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert analyst. Based on the content and its category, "
                        "provide a deep dive that's genuinely useful. Adapt your response format "
                        "to what makes sense for this type of content. Write in clear, direct prose. "
                        "No markdown, no asterisks, no backticks."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )
        logger.info(f"Generated deep dive for: {title}")
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Deep dive generation failed for '{title}': {type(e).__name__}: {e}")
        return ""


def _date_range_str() -> str:
    now = datetime.now(IST)
    end = now
    start = end - timedelta(days=6)
    return f"{start.strftime('%B %d')} — {end.strftime('%B %d, %Y')}"


def _send_email(html: str, subject: str, to_email: str = "", display_name: str = ""):
    if not SENDGRID_API_KEY or not FROM_EMAIL:
        logger.info("SendGrid not configured — skipping email send")
        return False
    if not to_email:
        logger.warning(f"DIGEST: No email set for {display_name}, skipping")
        return False
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail, Content

        sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=Content("text/html", html),
        )
        response = sg.send(message)
        logger.info(f"Digest email sent to {display_name} ({to_email}) | Status: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Digest email FAILED for {display_name} | Error: {type(e).__name__}: {e}")
        return False


def generate_full_digest(user_id: str, display_name: str = "", user_email: str = "") -> str | None:
    logger.info(f"Generating Saturday full digest for {display_name or user_id}")

    cluster_data = cluster_items(user_id)
    go_deep_items = get_go_deep_items(user_id)
    skipped = get_skipped_this_week(user_id, limit=3)
    unseen = get_never_surfaced(user_id, limit=1)
    stats = get_user_stats(user_id)

    logger.info(
        f"Building digest for {display_name or user_id} — "
        f"{cluster_data.get('total_clusters', 0)} clusters, "
        f"{len(go_deep_items)} deep dives, "
        f"{len(skipped)} skipped, {len(unseen)} unseen"
    )

    deep_dives = []
    go_deep_ids = []
    for item in go_deep_items:
        title = item.get("title", "Untitled")
        content = _generate_deep_dive(item.get("extracted_text") or item.get("summary") or "", title, item.get("category_name", ""))
        url = _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None
        deep_dives.append({
            "title": title,
            "deep_dive_content": content,
            "url": url,
            "category_name": item.get("category_name"),
        })
        go_deep_ids.append(item["id"])

    for item in skipped:
        item["url"] = _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None
    for item in unseen:
        item["url"] = _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None

    date_range = _date_range_str()
    data = {
        "clusters": cluster_data.get("clusters", []),
        "standalone": cluster_data.get("standalone", []),
        "deep_dives": deep_dives,
        "skipped_items": skipped,
        "unseen_items": unseen,
        "stats": stats,
        "date_range": date_range,
    }
    html = build_digest_html(data)

    _send_email(html, f"📬 Dropzone Weekly — {date_range}", to_email=user_email, display_name=display_name)

    all_item_ids = []
    for cluster in cluster_data.get("clusters", []):
        for item in cluster.get("items", []):
            all_item_ids.append(item["id"])
    for item in cluster_data.get("standalone", []):
        all_item_ids.append(item["id"])
    if all_item_ids:
        mark_items_in_digest(all_item_ids)
        logger.info(f"Marked {len(all_item_ids)} items as included in digest")

    if go_deep_ids:
        clear_go_deep_flags(go_deep_ids)
        logger.info(f"Cleared go_deep flags for {len(go_deep_ids)} items")

    return html


def generate_followup_digest(user_id: str, display_name: str = "", user_email: str = "") -> str | None:
    logger.info(f"Generating Sunday follow-up digest for {display_name or user_id}")

    pending = get_digest_pending_items(user_id)
    new_items = get_items_saved_since(user_id, since_hours=24)
    stats = get_user_stats(user_id)

    logger.info(
        f"Building follow-up for {display_name or user_id} — "
        f"{len(pending)} pending, {len(new_items)} new"
    )

    for item in pending:
        item["url"] = _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None
    for item in new_items:
        item["url"] = _extract_url(item.get("raw_content")) if item.get("content_type") == "url" else None

    data = {
        "pending_items": pending,
        "new_items": new_items,
        "stats": stats,
    }
    html = build_followup_html(data)

    _send_email(html, "📬 Dropzone Follow-up — still pending", to_email=user_email, display_name=display_name)

    return html


def generate_digest_for_user(user_id: str) -> str | None:
    return generate_full_digest(user_id)


async def send_weekly_digest(context):
    import traceback

    logger.info(f"Weekly digest check running at {datetime.now(IST)} IST")

    day = _digest_day()
    if not day:
        logger.info("Digest: Today is weekday — skipping")
        return

    logger.info(f"Digest: Today is {day.title()}")
    window_start, window_end = _current_window_minutes()

    users = get_active_users()
    logger.info(f"Digest: Active users found: {len(users)}")

    for user in users:
        user_nudge = user.get("nudge_time", "08:30")
        if len(user_nudge) > 5:
            user_nudge = user_nudge[:5]
        nudge_parts = user_nudge.split(":")
        nudge_h, nudge_m = int(nudge_parts[0]), int(nudge_parts[1])
        user_minutes = nudge_h * 60 + nudge_m

        is_match = window_start <= user_minutes <= window_end
        logger.info(
            f"Digest: User {user['display_name']}: nudge_time={user_nudge}, "
            f"current_window={window_start}-{window_end}, match={is_match}"
        )

        if not is_match:
            continue

        user_email = user.get("email")
        if not user_email:
            logger.info(f"DIGEST: Skipping {user['display_name']} — no email set")
            continue

        try:
            digest_type = "full" if day == "saturday" else "follow-up"
            logger.info(f"Digest: Sending {digest_type} digest to {user['display_name']} ({user_email})")

            if day == "saturday":
                generate_full_digest(user["id"], user["display_name"], user_email)
            else:
                generate_followup_digest(user["id"], user["display_name"], user_email)

            logger.info(f"Digest: {digest_type.title()} digest completed for {user['display_name']}")
        except Exception as e:
            logger.error(f"Digest ERROR for {user['display_name']}: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
