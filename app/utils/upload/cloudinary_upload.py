import cloudinary
import cloudinary.api
import cloudinary.uploader
from cloudinary import CloudinaryImage, CloudinaryVideo

from app.utils.constant import CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, CLOUDINARY_CLOUD_NAME, CLOUDINARY_URL

config = cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

filename = "output.mp3"

# Upload a file to Cloudinary
response = cloudinary.uploader.upload_large(filename, resource_type="video", chunk_size=6000000)

print(response['secure_url'])
