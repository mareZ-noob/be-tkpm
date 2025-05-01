import ast
import base64
import io
import os
from uuid import uuid4

import pollinations
import requests
from openai import OpenAI

from app.config.extensions import celery
from app.config.logging_config import setup_logging
from app.tasks.upload_tasks import process_image_upload
from app.utils.ai_agents import PROMPT_IMAGE
from app.utils.constant import OPEN_ROUTER_API_KEY

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
                if image_url:
                    if hasattr(image_url, 'save'):
                        logger.info(f"[Task ID: {task_id}] Saving PIL image to {image_filename}")
                        image_url.save(image_filename)

                        with open(image_filename, 'rb') as f:
                            file_data = f.read()

                    elif isinstance(image_url, str):
                        logger.info(f"[Task ID: {task_id}] Downloading image from URL to {image_filename}")
                        img_response = requests.get(image_url, stream=True)
                        img_response.raise_for_status()

                        # Save the image to validate it's a proper image file
                        with open(image_filename, 'wb') as f:
                            for chunk in img_response.iter_content(chunk_size=8192):
                                f.write(chunk)

                        # Read the validated image back for uploading
                        with open(image_filename, 'rb') as f:
                            file_data = f.read()
                    else:
                        logger.error(f"[Task ID: {task_id}] Invalid image URL format")
                        results.append({
                            'paragraph_id': paragraph_id,
                            'response': img_prompt,
                            'success': False,
                            'error': 'Image generation failed or returned invalid URL'
                        })
                        continue
                else:
                    logger.error(f"[Task ID: {task_id}] No image URL generated")
                    results.append({
                        'paragraph_id': paragraph_id,
                        'prompt': img_prompt,
                        'success': False,
                        'error': 'Image generation failed or returned invalid URL'
                    })
                    continue

                # Verify the image data
                if not file_data or len(file_data) < 100:
                    logger.error(f"[Task ID: {task_id}] Image data appears to be empty or too small")
                    results.append({
                        'paragraph_id': paragraph_id,
                        'response': img_prompt,
                        'success': False,
                        'error': 'Generated image data is invalid or corrupted'
                    })
                    continue

                # Upload to Cloudinary
                logger.info(f"[Task ID: {task_id}] Uploading image {i + 1} to Cloudinary")
                try:
                    # Use file data directly
                    upload_task = process_image_upload.apply_async(
                        args=[user_id, file_data, os.path.basename(image_filename)]
                    )

                    # Store task ID in results
                    results.append({
                        'paragraph_id': paragraph_id,
                        'response': img_prompt,
                        'success': True,
                        'upload_task_id': upload_task.id
                    })

                except Exception as upload_error:
                    logger.error(f"[Task ID: {task_id}] Failed to initiate upload task: {upload_error}", exc_info=True)
                    results.append({
                        'paragraph_id': paragraph_id,
                        'response': img_prompt,
                        'success': False,
                        'error': f'Failed to initiate upload: {str(upload_error)}'
                    })

            except Exception as e:
                logger.error(f"[Task ID: {task_id}] Error processing image {i + 1}: {e}", exc_info=True)
                results.append({
                    'paragraph_id': paragraph_id,
                    'response': img_prompt,
                    'success': False,
                    'error': str(e)
                })
            finally:
                if os.path.exists(image_filename):
                    os.remove(image_filename)

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