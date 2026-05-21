import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

GROQ_API_KEYS: list[str] = [
    k for k in [
        os.getenv("GROQ_API_KEY_1", ""),
        os.getenv("GROQ_API_KEY_2", ""),
        os.getenv("GROQ_API_KEY_3", ""),
    ] if k
]

SITE_URL = "https://centr-krasok.kz"
SITE_NAME = "Центр Красок #1"
GROQ_MODEL = "llama-3.3-70b-versatile"
PRODUCTS_PER_PAGE = 8
AI_MAX_HISTORY = 10
