import os
import shutil
import tempfile
from uuid import uuid4

import cloudinary.uploader
import numpy as np
from moviepy.editor import ImageClip
from moviepy.video.fx import all as vfx
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename

from app.config.extensions import celery, db
from app.config.logging_config import setup_logging
from app.models import Video
from app.utils.constant import EFFECT_TRANSITION_DURATION, EFFECTS_TO_APPLY, TARGET_FPS, VIDEO_FOLDER, ZOOM_FACTOR
from app.utils.function_helpers import create_video

logger = setup_logging()


def cleanup_resources(*args):
    for resource in args:
        if resource:
            try:
                if hasattr(resource, 'close') and callable(resource.close):
                    resource.close()
            except Exception:
                pass


def apply_zoom(clip, zoom_factor=1.15):
    if not clip.duration or clip.duration <= 0:
        return clip
    original_w, original_h = clip.size

    def zoom_frame_transform(get_frame, t):
        frame = get_frame(t)
        if len(frame.shape) < 2:
            return frame
        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return frame
        current_duration = clip.duration if clip.duration > 0 else 1
        scale = 1 + (zoom_factor - 1) * (t / current_duration)
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w <= 0 or new_h <= 0:
            return frame
        try:
            pil_image = Image.fromarray(frame)
            resized_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            resized_frame = np.array(resized_image)
            start_x = max(0, (new_w - w) // 2)
            start_y = max(0, (new_h - h) // 2)
            end_x = min(new_w, start_x + w)
            end_y = min(new_h, start_y + h)
            cropped_frame = resized_frame[start_y:end_y, start_x:end_x]
            if cropped_frame.shape[0] != original_h or cropped_frame.shape[1] != original_w:
                final_pil = Image.fromarray(cropped_frame)
                final_frame = np.array(final_pil.resize((original_w, original_h), Image.Resampling.LANCZOS))
                return final_frame
            else:
                return cropped_frame
        except Exception as e:
            logger.error(f"Error resizing frame: {e}", exc_info=True)
            if frame.shape[0] == original_h and frame.shape[1] == original_w:
                return frame
            else:
                num_channels = frame.shape[2] if len(frame.shape) > 2 else 3
                return np.zeros((original_h, original_w, num_channels), dtype=frame.dtype)

    return clip.fl(zoom_frame_transform, apply_to=['mask'] if clip.mask else [])


def process_image_effects(img_file, duration_per_part, target_size, effects_list, zoom_factor, fps, transition_duration,
                          task_id, user_id):
    logger.info(f"[Task ID: {task_id}] Processing image: {os.path.basename(img_file)} for user {user_id}")
    base_clip = None
    zoomed_clip_base = None
    generated_videos = []

    try:
        # Load and prepare base clip
        base_clip = ImageClip(img_file).set_duration(duration_per_part).set_fps(fps)
        if base_clip.size != target_size:
            base_clip = base_clip.resize(width=target_size[0], height=target_size[1])

        # Apply base zoom effect
        zoomed_clip_base = apply_zoom(base_clip.copy(), zoom_factor=zoom_factor)
        zoomed_clip_base = zoomed_clip_base.set_duration(duration_per_part)

        # Process each effect
        for effect_type in effects_list:
            # Generate unique filename in current working directory
            output_filename = os.path.join(os.getcwd(), f"{effect_type}_{uuid4()}.mp4")
            final_effect_clip = None

            try:
                clip_to_modify = zoomed_clip_base.copy()
                transition = min(transition_duration, duration_per_part / 2)
                slide_transition = min(transition_duration, duration_per_part)

                if effect_type == 'zoom_only':
                    final_effect_clip = clip_to_modify
                elif effect_type == 'fade_in':
                    final_effect_clip = vfx.fadein(clip_to_modify, duration=transition)
                elif effect_type == 'fade_out':
                    final_effect_clip = vfx.fadeout(clip_to_modify, duration=transition)
                elif effect_type == 'slide_in_left':
                    w, h = clip_to_modify.size

                    def slide_position(t):
                        if t < slide_transition:
                            x_pos = -w + (w * (t / slide_transition))
                            return (x_pos, 'center')
                        else:
                            return ('center', 'center')

                    final_effect_clip = clip_to_modify.set_position(slide_position)
                else:
                    logger.warning(f"[Task ID: {task_id}] Effect type '{effect_type}' not implemented. Skipping.")
                    cleanup_resources(clip_to_modify)
                    continue

                # Write the video clip
                if final_effect_clip:
                    final_effect_clip = final_effect_clip.set_duration(duration_per_part)
                    final_effect_clip.write_videofile(
                        output_filename, fps=fps, codec='libx264', audio=False, threads=1,
                        logger=None, preset='medium'
                    )

                    # Upload to Cloudinary
                    public_id = f"{VIDEO_FOLDER}/{user_id}/{uuid4()}"
                    logger.info(
                        f"[Task ID: {task_id}] Uploading video {output_filename} to Cloudinary (public_id: {public_id})")
                    with open(output_filename, 'rb') as video_file:
                        upload_result = cloudinary.uploader.upload(
                            video_file,
                            resource_type="video",
                            public_id=public_id,
                            overwrite=True,
                            chunk_size=6000000
                        )
                    secure_url = upload_result['secure_url']
                    logger.info(f"[Task ID: {task_id}] Uploaded video to Cloudinary: {secure_url}")

                    # Save to database
                    video = Video(
                        user_id=user_id,
                        url=secure_url,
                        title=f"Effect_{effect_type}_{os.path.basename(img_file)}"
                    )
                    db.session.add(video)
                    db.session.commit()

                    generated_videos.append({
                        'success': True,
                        'effect': effect_type,
                        'url': secure_url,
                        'video_id': video.id
                    })

            except Exception as e:
                logger.error(f"[Task ID: {task_id}] Error applying effect '{effect_type}' to image {img_file}: {e}",
                             exc_info=True)
                generated_videos.append({
                    'success': False,
                    'effect': effect_type,
                    'error': str(e)
                })
            finally:
                cleanup_resources(final_effect_clip)
                # Clean up the video file
                if os.path.exists(output_filename):
                    try:
                        os.remove(output_filename)
                        logger.debug(f"[Task ID: {task_id}] Removed video file: {output_filename}")
                    except OSError as e:
                        logger.warning(f"[Task ID: {task_id}] Could not remove video file {output_filename}: {e}")

    except (IOError, SyntaxError, UnidentifiedImageError) as img_err:
        logger.error(f"[Task ID: {task_id}] Failed to load/process image {img_file}: {img_err}", exc_info=True)
        return {'success': False, 'error': str(img_err), 'results': []}
    except Exception as e:
        logger.error(f"[Task ID: {task_id}] Critical error processing image {img_file}: {e}", exc_info=True)
        return {'success': False, 'error': str(e), 'results': []}
    finally:
        cleanup_resources(zoomed_clip_base, base_clip)

    return {'success': len(generated_videos) > 0, 'results': generated_videos}


@celery.task(bind=True, max_retries=3)
def process_image_to_video_effects(self, user_id, file_data, filename, duration_per_part):
    task_id = self.request.id
    logger.info(
        f"[Task ID: {task_id}] Starting video effects task for user {user_id}, filename: {filename}, duration_per_part: {duration_per_part}s")

    temp_dir = None
    temp_image_path = None
    try:
        # Save image to temporary file
        temp_dir = tempfile.mkdtemp()
        temp_image_path = os.path.join(temp_dir, secure_filename(filename))
        with open(temp_image_path, 'wb') as f:
            f.write(file_data)

        # Validate image
        try:
            with Image.open(temp_image_path) as img:
                img.verify()
        except (IOError, UnidentifiedImageError) as img_err:
            logger.error(f"[Task ID: {task_id}] Invalid image file {filename}: {img_err}", exc_info=True)
            return {'success': False, 'error': f"Invalid image file: {str(img_err)}", 'results': []}

        # Determine target size
        with ImageClip(temp_image_path) as temp_clip:
            target_size = temp_clip.size
        logger.info(f"[Task ID: {task_id}] Target video size set to: {target_size} (WxH)")

        # Process effects
        result = process_image_effects(
            img_file=temp_image_path,
            duration_per_part=duration_per_part,
            target_size=target_size,
            effects_list=EFFECTS_TO_APPLY,
            zoom_factor=ZOOM_FACTOR,
            fps=TARGET_FPS,
            transition_duration=EFFECT_TRANSITION_DURATION,
            task_id=task_id,
            user_id=user_id
        )

        logger.info(f"[Task ID: {task_id}] Video effects task completed for user {user_id}, filename: {filename}")
        return result

    except Exception as exc:
        logger.error(
            f"[Task ID: {task_id}] Exception in video effects task for user {user_id}, filename: {filename}: {exc}",
            exc_info=True)
        try:
            retry_count = self.request.retries + 1
            logger.warning(
                f"[Task ID: {task_id}] Retrying task for {filename}. Attempt {retry_count}/{self.max_retries}. Countdown: 5s.")
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            logger.error(
                f"[Task ID: {task_id}] Task failed permanently for {filename} after {self.max_retries} retries: {e}")
            return {'success': False, 'error': f"Max retries exceeded: {str(e)}", 'results': []}
    finally:
        # Clean up temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"[Task ID: {task_id}] Removed temporary directory: {temp_dir}")
            except OSError as e:
                logger.warning(f"[Task ID: {task_id}] Could not remove temporary directory {temp_dir}: {e}")


@celery.task(bind=True, max_retries=3)
def concat_video(self, user_id, data_dict):
    task_id = self.request.id
    logger.info(f"[Task ID: {task_id}] Starting video generation task for user {user_id}")

    try:
        # Process the image to video effects
        result = create_video(data_dict)

        if result is None:
            logger.error(f"[Task ID: {task_id}] Failed to create video for user {user_id}")
            return {'success': False, 'error': "Failed to create video"}

        # Upload the video to Cloudinary
        public_id = f"{VIDEO_FOLDER}/{user_id}/{uuid4()}"
        logger.info(f"[Task ID: {task_id}] Uploading video to Cloudinary (public_id: {public_id})")
        with open(result, 'rb') as video_file:
            upload_result = cloudinary.uploader.upload(
                video_file,
                resource_type="video",
                public_id=public_id,
                overwrite=True,
                chunk_size=6000000
            )
        secure_url = upload_result['secure_url']
        logger.info(f"[Task ID: {task_id}] Uploaded video to Cloudinary: {secure_url}")

        # Save the video URL to the database
        video = Video(
            user_id=user_id,
            url=secure_url,
            title=f"Generated_Video_{uuid4()}"
        )
        db.session.add(video)
        db.session.commit()
        logger.info(f"[Task ID: {task_id}] Video saved to database with ID: {video.id}")
        logger.info(f"[Task ID: {task_id}] Video generation task completed for user {user_id}")
        return {'success': True, 'url': secure_url, 'video_id': video.id}

    except Exception as exc:
        logger.error(f"[Task ID: {task_id}] Exception in video generation task for user {user_id}: {exc}",
                     exc_info=True)
        try:
            retry_count = self.request.retries + 1
            logger.warning(
                f"[Task ID: {task_id}] Retrying task for user {user_id}. Attempt {retry_count}/{self.max_retries}. Countdown: 5s.")
            self.retry(exc=exc, countdown=5)
        except self.MaxRetriesExceededError as e:
            logger.error(
                f"[Task ID: {task_id}] Task failed permanently for user {user_id} after {self.max_retries} retries: {e}")
            return {'success': False, 'error': f"Max retries exceeded: {str(e)}"}
    finally:
        if os.path.exists(result):
            try:
                os.remove(result)
                logger.debug(f"[Task ID: {task_id}] Removed temporary video file: {result}")
            except OSError as e:
                logger.warning(f"[Task ID: {task_id}] Could not remove temporary video file {result}: {e}")
