import os
from dotenv import load_dotenv
import anthropic
import google.genai
from openai import OpenAI
from supabase import create_client

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_IDS = [int(id) for id in os.getenv("AUTHORIZED_USER_IDS", "").split(",") if id]

_required = {"SUPABASE_URL": SUPABASE_URL, "SUPABASE_KEY": SUPABASE_KEY, "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN}
if LLM_PROVIDER == "claude":
    _required["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
elif LLM_PROVIDER == "gemini":
    _required["GEMINI_API_KEY"] = GEMINI_API_KEY
elif LLM_PROVIDER == "openai":
    _required["OPENAI_API_KEY"] = OPENAI_API_KEY

_missing = [name for name, value in _required.items() if not value]
if _missing:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(_missing)}")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
try:
    supabase.table("categories").select("id").limit(1).execute()
except Exception as e:
    raise ConnectionError(f"Failed to connect to Supabase: {e}")

claude = None
gemini = None
openai_client = None

if LLM_PROVIDER == "claude":
    claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
elif LLM_PROVIDER == "gemini":
    gemini = google.genai.Client(api_key=GEMINI_API_KEY)
elif LLM_PROVIDER == "openai":
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
