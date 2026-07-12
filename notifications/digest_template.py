import re
from html import escape


def _esc(text) -> str:
    if text is None:
        return ""
    return escape(str(text))


def _extract_url(raw_content):
    if not raw_content:
        return None
    match = re.search(r'https?://\S+', raw_content)
    return match.group(0) if match else None


def _worth_another_look_card(item: dict) -> str:
    title = _esc(item.get("title", "Untitled"))
    cat = _esc(item.get("category_name", ""))
    summary = _esc(item.get("summary", ""))
    age = item.get("age_days", 0)
    url = item.get("url")
    if item.get("content_type") == "url" and url:
        title_display = f'<a href="{_esc(url)}" style="color: #2563eb; text-decoration: none; font-weight: 600;">{title}</a>'
    else:
        title_display = f'<span style="font-weight: 600;">{title}</span>'
    return f"""
    <div style="background: #ffffff; border-radius: 8px; padding: 16px; margin-bottom: 12px; border: 1px solid #e5e7eb;">
        <div style="font-size: 15px; color: #1f2937; margin-bottom: 4px;">{title_display}</div>
        <div style="font-size: 12px; color: #9ca3af; margin-bottom: 8px;">{cat} · {age:.0f}d ago</div>
        <div style="font-size: 14px; color: #374151; line-height: 1.5;">{summary}</div>
    </div>
    """


def build_digest_html(data: dict) -> str:
    clusters = data.get("clusters", [])
    deep_dives = data.get("deep_dives", [])
    date_range = data.get("date_range", "")

    sections = []

    # --- HEADER ---
    sections.append(f"""
    <div style="background: #2563eb; padding: 32px 24px; border-radius: 12px 12px 0 0; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #ffffff;">📬 Dropzone Weekly</div>
        <div style="font-size: 14px; color: #bfdbfe; margin-top: 8px;">{_esc(date_range)}</div>
    </div>
    """)

    # --- SECTION 1: QUICK CATCH-UP (skipped + never surfaced) ---
    skipped_items = data.get("skipped_items", [])
    unseen_items = data.get("unseen_items", [])
    if skipped_items or unseen_items:
        section_html = ""

        if skipped_items:
            section_html += '<div style="font-size: 13px; color: #6b7280; margin-bottom: 16px;">These came up this week but you haven\'t acted on them:</div>'
            for item in skipped_items:
                section_html += _worth_another_look_card(item)

        if unseen_items:
            if skipped_items:
                section_html += '<div style="border-top: 1px solid #e5e7eb; margin: 16px 0;"></div>'
            section_html += '<div style="font-size: 13px; color: #6b7280; margin-bottom: 16px;">You haven\'t seen this one yet:</div>'
            for item in unseen_items:
                section_html += _worth_another_look_card(item)

        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 16px;">📋 Quick catch-up</div>
            {section_html}
        </div>
        <div style="border-top: 1px solid #e5e7eb;"></div>
        """)

    # --- SECTION 2: DEEP DIVES ---
    if deep_dives:
        dive_cards = ""
        for dive in deep_dives:
            title = _esc(dive.get("title", "Untitled"))
            cat = _esc(dive.get("category_name", ""))
            content = dive.get("deep_dive_content", "")
            url = dive.get("url")
            status = dive.get("status")
            if url:
                title_display = f'<a href="{_esc(url)}" style="color: #2563eb; text-decoration: none; font-weight: 600;">{title}</a>'
            else:
                title_display = f'<span style="font-weight: 600;">{title}</span>'
            status_note = ""
            if status == "acted_on":
                status_note = '<div style="font-size: 12px; color: #059669; margin-bottom: 6px;">✅ You acted on this — here\'s the deep dive you requested</div>'
            elif status == "archived":
                status_note = '<div style="font-size: 12px; color: #6b7280; margin-bottom: 6px;">📦 Archived — deep dive still generated as requested</div>'
            cat_html = f'<div style="font-size: 12px; color: #9ca3af; margin-bottom: 8px;">{cat}</div>' if cat else ""
            content_html = _esc(content).replace("\n", "<br>")
            dive_cards += f"""
            <div style="background: #fffbeb; border-radius: 8px; padding: 16px; margin-bottom: 12px; border: 1px solid #fde68a;">
                <div style="font-size: 16px; color: #1f2937; margin-bottom: 4px;">{title_display}</div>
                {status_note}
                {cat_html}
                <div style="font-size: 14px; color: #374151; line-height: 1.6;">{content_html}</div>
            </div>
            """
        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 16px;">🧠 Deep dives you requested</div>
            {dive_cards}
        </div>
        <div style="border-top: 1px solid #e5e7eb;"></div>
        """)

    # --- SECTION 3: PATTERNS THIS WEEK (themed clusters) ---
    if clusters:
        cluster_cards = ""
        for cluster in clusters:
            items_html = ""
            for item in cluster.get("items", []):
                title = _esc(item.get("title", "Untitled"))
                cat = _esc(item.get("category_name", ""))
                url = item.get("url")
                if item.get("content_type") == "url" and url:
                    title_display = f'<a href="{_esc(url)}" style="color: #2563eb; text-decoration: none;">{title}</a>'
                else:
                    title_display = title
                items_html += f"""
                <div style="padding: 4px 0;">
                    <span style="color: #1f2937;">• {title_display}</span>
                    <span style="color: #9ca3af; font-size: 12px;"> — {cat}</span>
                </div>
                """
            count = len(cluster.get("items", []))
            cluster_cards += f"""
            <div style="background: #f9fafb; border-radius: 8px; padding: 16px; margin-bottom: 12px; border: 1px solid #e5e7eb;">
                <div style="font-size: 16px; font-weight: 600; color: #1f2937; margin-bottom: 4px;">{_esc(cluster.get('emoji', '📌'))} {_esc(cluster.get('theme', 'Related items'))}</div>
                <div style="font-size: 12px; color: #6b7280; margin-bottom: 10px;">{count} item{'s' if count != 1 else ''}</div>
                {items_html}
            </div>
            """
        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 16px;">Patterns this week</div>
            {cluster_cards}
        </div>
        <div style="border-top: 1px solid #e5e7eb;"></div>
        """)

    # --- FOOTER ---
    sections.append("""
    <div style="padding: 24px; text-align: center; border-top: 1px solid #e5e7eb;">
        <div style="font-size: 13px; color: #6b7280; line-height: 1.6;">
            Open Dropzone in Telegram to act on these.
            <br>You received this because you use Dropzone. Send /stop to pause.
        </div>
    </div>
    """)

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dropzone Weekly</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
<div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; margin-top: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
{body}
</div>
</body>
</html>"""


def build_followup_html(data: dict) -> str:
    pending = data.get("pending_items", [])
    new_items = data.get("new_items", [])
    stats = data.get("stats", {})

    sections = []

    # --- HEADER ---
    sections.append("""
    <div style="background: #7c3aed; padding: 32px 24px; border-radius: 12px 12px 0 0; text-align: center;">
        <div style="font-size: 28px; font-weight: 700; color: #ffffff;">📬 Dropzone Follow-up</div>
        <div style="font-size: 14px; color: #ddd6fe; margin-top: 8px;">Quick follow-up — these are still waiting</div>
    </div>
    """)

    # --- SECTION 1: PENDING FROM YESTERDAY ---
    if pending:
        items_html = ""
        for item in pending:
            title = _esc(item.get("title", "Untitled"))
            cat = _esc(item.get("category_name", ""))
            url = item.get("url")
            if item.get("content_type") == "url" and url:
                title_display = f'<a href="{_esc(url)}" style="color: #2563eb; text-decoration: none;">{title}</a>'
            else:
                title_display = title
            items_html += f"""
            <div style="padding: 6px 0; font-size: 14px; color: #374151;">
                • {title_display} <span style="color: #9ca3af;">— {cat}</span>
            </div>
            """
        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 4px;">Items from yesterday's digest you haven't acted on</div>
            <div style="font-size: 13px; color: #6b7280; margin-bottom: 16px;">{len(pending)} item{'s' if len(pending) != 1 else ''} still pending</div>
            {items_html}
        </div>
        <div style="border-top: 1px solid #e5e7eb;"></div>
        """)

    # --- SECTION 2: NEW ITEMS ---
    if new_items:
        items_html = ""
        for item in new_items:
            title = _esc(item.get("title", "Untitled"))
            cat = _esc(item.get("category_name", ""))
            items_html += f'<div style="padding: 4px 0; font-size: 14px; color: #374151;">• {title} <span style="color: #9ca3af;">— {cat}</span></div>\n'
        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 16px;">New items saved yesterday</div>
            {items_html}
        </div>
        <div style="border-top: 1px solid #e5e7eb;"></div>
        """)

    # --- SECTION 3: STATS ---
    if stats:
        sections.append(f"""
        <div style="padding: 24px;">
            <div style="font-size: 18px; font-weight: 600; color: #1f2937; margin-bottom: 16px;">📊 Updated stats</div>
            <div style="font-size: 14px; color: #374151; line-height: 1.8;">
                <div style="padding: 4px 0;">Total active: <strong>{stats.get('active', 0)}</strong></div>
                <div style="padding: 4px 0;">Acted on this week: <strong>{stats.get('week_acted', 0)}</strong></div>
                <div style="padding: 4px 0;">Archived this week: <strong>{stats.get('week_archived', 0)}</strong></div>
            </div>
        </div>
        """)

    if not pending and not new_items:
        sections.append("""
        <div style="padding: 24px; text-align: center;">
            <div style="font-size: 16px; color: #1f2937;">You're all caught up! Nothing pending from yesterday. 🎉</div>
        </div>
        """)

    # --- FOOTER ---
    sections.append("""
    <div style="padding: 24px; text-align: center; border-top: 1px solid #e5e7eb;">
        <div style="font-size: 13px; color: #6b7280; line-height: 1.6;">
            Open Dropzone in Telegram to act on these.
            <br>You received this because you use Dropzone. Send /stop to pause.
        </div>
    </div>
    """)

    body = "\n".join(sections)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dropzone Follow-up</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;">
<div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; margin-top: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
{body}
</div>
</body>
</html>"""


def _format_deep_dive(content: str) -> str:
    if not content:
        return ""
    lines = content.strip().split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        line = line.strip()
        if not line:
            if in_list:
                in_list = False
            html_parts.append("<br>")
            continue
        if line.startswith("**") and line.endswith("**"):
            heading = _esc(line.strip("*").strip())
            html_parts.append(f'<div style="font-weight: 600; margin-top: 10px; margin-bottom: 4px;">{heading}</div>')
        elif re.match(r'^\d+\.', line):
            html_parts.append(f'<div style="padding-left: 16px; padding: 2px 0 2px 16px;">{_esc(line)}</div>')
            in_list = True
        elif line.startswith("- ") or line.startswith("• "):
            html_parts.append(f'<div style="padding-left: 16px; padding: 2px 0 2px 16px;">• {_esc(line[2:])}</div>')
            in_list = True
        else:
            html_parts.append(f'<div>{_esc(line)}</div>')
    return "\n".join(html_parts)
