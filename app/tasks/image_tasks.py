import ast
import os
from uuid import uuid4

import pollinations
import requests
from openai import OpenAI

from app.config.extensions import celery
from app.config.logging_config import setup_logging
from app.models import Image, User
from app.utils.ai_agents import PROMPT_IMAGE
from app.utils.constant import IMAGE_FOLDER, OPEN_ROUTER_API_KEY

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
)

logger = setup_logging()


@celery.task(bind=True, max_retries=3)
def process_image_generation(self, user_id, model, paragraph_id, content, num_images=2):
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting image generation for user_id: {user_id} with model: {model}")

    try:
        if not content:
            return {'success': False, 'error': 'No paragraph provided'}

        image_prompts = []
        logger.info(f"[Task ID: {task_id}] Generating image prompt for paragraph {paragraph_id}")

        prompt = PROMPT_IMAGE % (num_images, content, num_images)
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                     "content": "You are an expert assistant skilled at creating descriptive image generation prompts from text. Output *only* the requested Python list of strings."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
        except Exception as e:
            logger.error(
                f"[Task ID: {task_id}] Failed to generate prompt for paragraph {paragraph_id}: {e}", exc_info=True)
            return {'success': False, 'error': f'Failed to generate prompt: {str(e)}'}

        if completion and hasattr(completion, 'choices') and completion.choices:
            raw_response = completion.choices[0].message.content.strip()
            try:
                cleaned_response = raw_response.strip().strip('```python').strip('```').strip()
                parsed_prompts = ast.literal_eval(cleaned_response)

                if isinstance(parsed_prompts, list) and all(isinstance(p, str) for p in parsed_prompts):
                    image_prompts = parsed_prompts
                    logger.info(f"Successfully parsed {len(image_prompts)} prompts from AI response.")
                else:
                    logger.info("AI response format invalid: Expected a list of strings.")
                    image_prompts = [line.strip() for line in cleaned_response.split('\n') if line.strip()]
                    if image_prompts:
                        logger.info(f"Fallback successful (line split): Extracted {len(image_prompts)} prompts.")
                    else:
                        logger.error("Fallback failed: No valid prompts found.")
                        return {'success': False, 'error': 'No image prompts generated'}

            except (SyntaxError, ValueError, TypeError) as parse_error:
                logger.error(f"Error parsing AI response as a Python list: {parse_error}", exc_info=True)
                image_prompts = [line.strip().strip(",").strip("'").strip('"') for line in raw_response.split('\n') if
                                 line.strip() and not line.strip().startswith('[') and not line.strip().endswith(']')]
                image_prompts = [p for p in image_prompts if p]
                if image_prompts:
                    logger.info(f"Fallback successful (robust split): Extracted {len(image_prompts)} prompts.")

        if not image_prompts:
            return {'success': False, 'error': 'No image prompts generated'}

        logger.info(f"[Task ID: {task_id}] Initializing Pollinations model")
        model = pollinations.Image(nologo=True)

        results = []

        for i, img_prompt in enumerate(image_prompts):
            logger.info(f"[Task ID: {task_id}] Generating image {i + 1}/{len(image_prompts)}: {img_prompt}")
            image_filename = os.path.join(os.getcwd(), f"image_{uuid4()}.png")

            try:
                image_url = model(img_prompt)
                if not image_url:
                    logger.error(f"[Task ID: {task_id}] No image URL generated for prompt: {img_prompt}")
                    results.append({
                        'paragraph_id': paragraph_id,
                        'prompt': img_prompt,
                        'success': False,
                        'error': 'Image generation failed or returned no URL'
                    })
                    continue

                if hasattr(image_url, 'save'):
                    logger.info(f"[Task ID: {task_id}] Saving PIL image to {image_filename}")
                    image_url.save(image_filename)
                    with open(image_filename, 'rb') as f:
                        file_data = f.read()
                elif isinstance(image_url, str):
                    logger.info(f"[Task ID: {task_id}] Downloading image from URL: {image_url}")
                    img_response = requests.get(image_url, timeout=10)
                    img_response.raise_for_status()

                    # Verify content type
                    content_type = img_response.headers.get('content-type', '')
                    if not content_type.startswith('image/'):
                        logger.error(f"[Task ID: {task_id}] Invalid content type: {content_type}")
                        results.append({
                            'paragraph_id': paragraph_id,
                            'prompt': img_prompt,
                            'success': False,
                            'error': 'Downloaded content is not an image'
                        })
                        continue

                    file_data = img_response.content
                    # Save temporarily to validate
                    with open(image_filename, 'wb') as f:
                        f.write(file_data)
                else:
                    logger.error(f"[Task ID: {task_id}] Invalid image URL format: {type(image_url)}")
                    results.append({
                        'paragraph_id': paragraph_id,
                        'prompt': img_prompt,
                        'success': False,
                        'error': 'Invalid image URL format'
                    })
                    continue

                # Verify the image data
                if not file_data or len(file_data) < 100:
                    logger.error(f"[Task ID: {task_id}] Image data appears to be empty or too small")
                    results.append({
                        'paragraph_id': paragraph_id,
                        'prompt': img_prompt,
                        'success': False,
                        'error': 'Generated image data is invalid or corrupted'
                    })
                    continue

                # Upload to Cloudinary - Fix: Process upload directly instead of using apply_async
                logger.info(f"[Task ID: {task_id}] Uploading image {i + 1} to Cloudinary")
                try:
                    # Process the upload directly
                    uploaded_result = process_image_upload_directly(user_id, file_data, image_filename)

                    if uploaded_result.get('success'):
                        results.append({
                            'paragraph_id': paragraph_id,
                            'prompt': img_prompt,
                            'success': True,
                            'url': uploaded_result.get('url'),
                            'image_id': uploaded_result.get('id')
                        })
                    else:
                        results.append({
                            'paragraph_id': paragraph_id,
                            'prompt': img_prompt,
                            'success': False,
                            'error': uploaded_result.get('error', 'Unknown upload error')
                        })
                except Exception as upload_error:
                    logger.error(f"[Task ID: {task_id}] Failed to upload image: {upload_error}", exc_info=True)
                    results.append({
                        'paragraph_id': paragraph_id,
                        'prompt': img_prompt,
                        'success': False,
                        'error': f'Failed to upload: {str(upload_error)}'
                    })

            except Exception as e:
                logger.error(f"[Task ID: {task_id}] Error processing image {i + 1}: {e}", exc_info=True)
                results.append({
                    'paragraph_id': paragraph_id,
                    'prompt': img_prompt,
                    'success': False,
                    'error': str(e)
                })
            finally:
                if os.path.exists(image_filename):
                    try:
                        os.remove(image_filename)
                    except Exception as e:
                        logger.warning(f"[Task ID: {task_id}] Failed to remove temporary file {image_filename}: {e}")

        logger.info(f"[Task ID: {task_id}] Image generation completed with {len(results)} results")
        return {
            'success': True if any(r.get('success', False) for r in results) else False,
            'results': results
        }

    except Exception as exc:
        logger.error(f"[Task ID: {task_id}] Error in image generation: {exc}", exc_info=True)
        retry_count = self.request.retries + 1
        if retry_count <= self.max_retries:
            logger.warning(f"[Task ID: {task_id}] Retrying... Attempt {retry_count}/{self.max_retries}")
            self.retry(exc=exc, countdown=5)
        logger.error(f"[Task ID: {task_id}] Failed after {self.max_retries} retries")
        return {'success': False, 'error': str(exc)}

    finally:
        logger.info(f"[Task ID: {task_id}] Task completed")


def process_image_upload_directly(user_id, file_data, filename="uploaded_image"):
    import os
    from uuid import uuid4

    import cloudinary.uploader
    from PIL import Image as PILImage

    from app.config.extensions import db

    logger.info(f"Starting direct image upload for user_id: {user_id}, filename: {filename}")
    public_id = None
    temp_filename = None

    try:
        temp_filename = f"temp_image_{uuid4()}.png"
        with open(temp_filename, 'wb') as f:
            f.write(file_data)

        try:
            with PILImage.open(temp_filename) as img:
                logger.info(f"Image validated: {img.format} {img.size}")
                if img.format not in ('JPEG', 'PNG', 'GIF', 'WEBP'):
                    img.save(temp_filename)
                    with open(temp_filename, 'rb') as f:
                        file_data = f.read()
        except Exception as img_error:
            logger.error(f"Image validation failed: {img_error}", exc_info=True)
            return {'success': False, 'error': f"Invalid image data: {str(img_error)}"}

        unique_id = str(uuid4())
        public_id = f"{IMAGE_FOLDER}/{user_id}/{unique_id}"

        logger.info(
            f"Attempting to upload image '{filename}' for user {user_id} to Cloudinary (public_id: {public_id}).")
        upload_result = cloudinary.uploader.upload(
            file_data,
            resource_type="image",
            public_id=public_id,
            overwrite=True,
            format="png"
        )
        secure_url = upload_result['secure_url']
        logger.info(f"Successfully uploaded image '{filename}' for user {user_id}. Cloudinary URL: {secure_url}")

        logger.info(f"Attempting to save image record for user {user_id} to the database.")
        user = User.query.get(user_id)
        if not user:
            logger.error(f"User not found in database for user_id: {user_id} while saving image record.")
            return {'success': False, 'error': f"User not found for user_id: {user_id}"}

        new_image = Image(
            user_id=user_id,
            url=secure_url
        )
        db.session.add(new_image)
        db.session.commit()

        logger.info(f"Successfully saved image record for user {user_id} to the database.")
        logger.info(f"Image upload completed successfully for user_id: {user_id}.")
        return {'success': True, 'url': secure_url, 'public_id': public_id, 'id': new_image.id}

    except Exception as exc:
        logger.error(
            f"Exception occurred during direct image upload for user {user_id}, filename: {filename}. Error: {exc}",
            exc_info=True)
        return {'success': False, 'error': str(exc)}

    finally:
        if temp_filename and os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
                logger.debug(f"Removed temporary file: {temp_filename}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file: {temp_filename}. Error: {e}")
