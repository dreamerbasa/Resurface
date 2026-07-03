import os

from openai import OpenAI
from config import OPENAI_API_KEY

_client = OpenAI(api_key=OPENAI_API_KEY)


def extract(voice_file_path: str, raw_content: str = "") -> dict:
    try:
        with open(voice_file_path, "rb") as audio_file:
            transcript = _client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        extracted_text = transcript.text
    except Exception as e:
        extracted_text = f"Could not transcribe voice note: {e}"
    finally:
        if os.path.exists(voice_file_path):
            os.remove(voice_file_path)

    return {
        "content_type": "voice",
        "raw_content": raw_content or extracted_text,
        "extracted_text": extracted_text,
        "source_platform": "telegram",
    }
