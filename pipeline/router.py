from datetime import datetime

from pipeline.extractors import text
from pipeline.extractors import url as url_extractor
from pipeline.extractors import whisper
from pipeline.classifier import classify
from db.queries import insert_item

_URL_PATTERN = __import__("re").compile(r"https?://[^\s<>\"']+")


def process_message(raw_content: str, content_type: str = "text", file_path: str = None) -> dict:
    if content_type == "text":
        if _URL_PATTERN.search(raw_content):
            extracted_data = url_extractor.extract(raw_content)
        else:
            extracted_data = text.extract(raw_content)
    elif content_type == "voice":
        extracted_data = whisper.extract(file_path, raw_content)
    else:
        raise ValueError(f"Unsupported content type: {content_type}")

    if extracted_data.get("needs_screenshot"):
        return {
            "status": "needs_screenshot",
            "message": "Instagram links don't give me much to work with. Send a screenshot of the post instead — I'll read it much better!",
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

    insert_item(item)

    return {
        "category_name": classification["category_name"],
        "title": classification["title"],
        "summary": classification["summary"],
        "tags": classification["tags"],
    }
