import os

from dotenv import load_dotenv
from edge_tts.constants import DEFAULT_VOICE

load_dotenv()

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPEN_ROUTER_API_KEY = os.getenv('OPEN_ROUTER_API_KEY')
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
CLOUDINARY_URL = os.getenv('CLOUDINARY_URL')
AVATAR_FOLDER = os.getenv('AVATAR_FOLDER')
VIDEO_FOLDER = os.getenv('VIDEO_FOLDER')
AUDIO_FOLDER = os.getenv('AUDIO_FOLDER')
IMAGE_FOLDER = os.getenv('IMAGE_FOLDER')
SRT_FOLDER = os.getenv('SRT_FOLDER')
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg'}

ENDPOINTS = [
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://tiktoktts.com/api/tiktok-tts",
]
EDGE_ENGINE = "edge"
TIKTOK_ENGINE = "tiktok"
FEMALE = "female"
MALE = "male"
ALL = "all"
DEFAULT_EDGE_VOICE = DEFAULT_VOICE
DEFAULT_TIKTOK_VOICE = "en_us_001"

JAPANESE_TEXT_BYTE_LIMIT = 70
ENGLISH_TEXT_BYTE_LIMIT = 100
VIETNAMESE_TEXT_BYTE_LIMIT = 100

API_SERVICE_NAME = "youtube"
API_VERSION = "v3"
CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/userinfo.profile",
          "https://www.googleapis.com/auth/userinfo.email",
          "openid"]

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

CHUNK_SIZE = 3 * 1024 * 1024
DOWNLOAD_RETRIES = 3
DOWNLOAD_BACKOFF_FACTOR = 1
DOWNLOAD_TIMEOUT = (10, 60)

CASCADE_RULES = "all, delete-orphan"

EFFECT_TRANSITION_DURATION = 1.0  # Duration of fade/slide effects in seconds
ZOOM_FACTOR = 1.15  # How much to zoom in (e.g., 1.15 = 15% zoom)
TARGET_FPS = 24  # Frames per second for output video clips
EFFECTS_TO_APPLY = ['zoom_only', 'slide_in_left', 'fade_in', 'fade_out']
FFMPEG_PATH = "ffmpeg"
FPS = 25
VIDEO_FORMAT = "yuv420p"
TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
