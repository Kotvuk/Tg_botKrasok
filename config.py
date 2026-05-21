import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

SITE_URL = "https://centr-krasok.kz"
SITE_NAME = "Центр Красок #1"
GROQ_MODEL = "llama-3.3-70b-versatile"
PRODUCTS_PER_PAGE = 8
AI_MAX_HISTORY = 10
