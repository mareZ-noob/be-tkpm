import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

JAPANESE_TEXT_BYTE_LIMIT = 70
ENGLISH_TEXT_BYTE_LIMIT = 100
VIETNAMESE_TEXT_BYTE_LIMIT = 100
