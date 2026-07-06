import base64
import os
import uuid

from config import openai_client, supabase, OPENAI_API_KEY

if not openai_client:
    from openai import OpenAI
    _client = OpenAI(api_key=OPENAI_API_KEY)
else:
    _client = openai_client

_SYSTEM_PROMPT = """You are an expert at reading screenshots and extracting meaningful content.

IGNORE all UI noise:
- Phone status bars (battery, time, signal, wifi icons)
- Navigation bars (back buttons, home indicators)
- App chrome (like, comment, share, save buttons)
- Story/reel progress bars
- Usernames, profile pictures, follower counts
- App watermarks (Instagram, LinkedIn logos)

FOCUS ON the actual post content:
- Text written ON or IN the image (infographics, cards, overlaid text, quotes, lists, tips)
- Any readable text that is the main content of the post
- Captions or descriptions if they contain useful info

Return your response in this exact format:

EXTRACTED TEXT:
[All meaningful text from the post, cleaned and readable]

VISUAL DESCRIPTION:
[One line describing what the image shows — e.g. "recipe card for butter chicken", "job posting graphic", "motivational quote on sunset background"]"""


def extract(image_file_path: str, raw_content: str = "") -> dict:
    try:
        with open(image_file_path, "rb") as f:
            file_data = f.read()
    except Exception as e:
        if os.path.exists(image_file_path):
            os.remove(image_file_path)
        return {
            "content_type": "image",
            "raw_content": raw_content or "screenshot",
            "extracted_text": f"Could not read image file: {e}",
            "source_platform": "telegram",
            "image_path": None,
        }

    image_path = None
    try:
        filename = f"screenshots/{uuid.uuid4()}.jpg"
        supabase.storage.from_("images").upload(filename, file_data)
        image_path = filename
    except Exception:
        pass

    try:
        base64_image = base64.b64encode(file_data).decode("utf-8")

        response = _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the main content from this screenshot. Ignore all phone UI and app interface elements.",
                        },
                    ],
                },
            ],
            max_tokens=1000,
        )
        extracted_text = response.choices[0].message.content
    except Exception as e:
        extracted_text = f"Could not extract content from image: {e}"
    finally:
        if os.path.exists(image_file_path):
            os.remove(image_file_path)

    if raw_content and raw_content != "screenshot":
        extracted_text = f"User note: {raw_content}\n\n{extracted_text}"

    return {
        "content_type": "image",
        "raw_content": raw_content or "screenshot",
        "extracted_text": extracted_text,
        "source_platform": "telegram",
        "image_path": image_path,
    }
