from datetime import datetime

from pipeline.extractors import text
from pipeline.extractors import url as url_extractor
from pipeline.extractors import whisper
from pipeline.extractors import vision
from pipeline.classifier import classify
from db.queries import insert_item

_URL_PATTERN = __import__("re").compile(r"https?://[^\s<>\"']+")


def _process_single(extracted_data: dict, user_id: str = None) -> dict:
    if extracted_data.get("needs_screenshot"):
        return {
            "status": "needs_screenshot",
            "message": "This link doesn't give me much to work with. Send a screenshot of the post instead — I'll read it much better!",
        }

    classification = classify(extracted_data["extracted_text"])

    item = {
        "content_type": extracted_data["content_type"],
        "raw_content": extracted_data["raw_content"],
        "extracted_text": extracted_data["extracted_text"],
        "category_id": classification["category_id"],
        "title": classification["title"],
        "summary": classification["summary"],
        "tags": classification["tags"],
        "status": "fresh",
        "processed_at": datetime.utcnow().isoformat(),
    }
    if user_id:
        item["user_id"] = user_id

    inserted = insert_item(item)

    return {
        "item_id": inserted["id"],
        "category_name": classification["category_name"],
        "title": classification["title"],
        "summary": classification["summary"],
        "tags": classification["tags"],
    }


def process_message(raw_content: str, content_type: str = "text", file_path: str = None, user_id: str = None):
    if content_type == "text":
        urls = url_extractor.find_urls(raw_content)

        if len(urls) > 1:
            remaining = raw_content
            for u in urls:
                remaining = remaining.replace(u, "")
            user_note = remaining.strip() or None

            results = []
            for u in urls:
                extracted_data = url_extractor.extract_single(u, user_note)
                results.append(_process_single(extracted_data, user_id))
            return results

        if len(urls) == 1:
            extracted_data = url_extractor.extract(raw_content)
        else:
            extracted_data = text.extract(raw_content)

    elif content_type == "voice":
        extracted_data = whisper.extract(file_path, raw_content)
    elif content_type == "image":
        extracted_data = vision.extract(file_path, raw_content)
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

    return _process_single(extracted_data, user_id)
