import json
import re

from config import claude, gemini, openai_client, LLM_PROVIDER
from db.queries import get_categories

SYSTEM_PROMPT = (
    "You are a content classifier. Given a list of categories and a piece "
    "of content, classify the content into the best fitting category. "
    "Return ONLY valid JSON with no markdown formatting, no backticks. "
    "JSON schema: {category_name: str, title: str, summary: str, tags: [str]}. "
    "- category_name must exactly match one of the provided category names. "
    "- title: a short descriptive title (5-10 words). "
    "- summary: 2-3 sentence summary of the content. "
    "- tags: 3-5 relevant tags. "
    "If nothing fits well, use 'random_thought' as the category."
)


def _call_claude(user_message: str) -> str:
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _call_gemini(user_message: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\n{user_message}"
    response = gemini.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text


def _call_openai(user_message: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


def classify(extracted_text: str) -> dict:
    categories = get_categories()

    formatted = "\n".join(
        f"- {c['name']}: {c['description']}" for c in categories
    )
    user_message = (
        f"Categories:\n{formatted}\n\n"
        f"Content to classify:\n{extracted_text}"
    )

    if LLM_PROVIDER == "claude":
        raw = _call_claude(user_message)
    elif LLM_PROVIDER == "gemini":
        raw = _call_gemini(user_message)
    elif LLM_PROVIDER == "openai":
        raw = _call_openai(user_message)

    result = _parse_json(raw)

    category_id = None
    for c in categories:
        if c["name"] == result["category_name"]:
            category_id = c["id"]
            break

    return {
        "category_id": category_id,
        "category_name": result["category_name"],
        "title": result["title"],
        "summary": result["summary"],
        "tags": result["tags"],
    }


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
        return json.loads(cleaned)
