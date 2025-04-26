import logging
import math
import os
import subprocess
import threading
from uuid import uuid4

import cloudinary
import cloudinary.uploader
from flask import after_this_request, g, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.config.logging_config import setup_logging
from app.models import User
from app.utils.constant import ALL, AUDIO_FOLDER, EDGE_ENGINE, FEMALE, MALE, TIKTOK_ENGINE
from app.utils.exceptions import (
    BadRequestException,
    InternalServerException,
    InvalidCredentialsException,
    MissingParameterException,
    ResourceNotFoundException,
    ServiceUnavailableException,
)
from app.utils.voice.edge_voices import EDGE_FORMATTED_VOICES
from app.utils.voice.tiktok_tts import TikTokTTS
from app.utils.voice.tiktok_voices import TIKTOK_FORMATTED_VOICES

logger = setup_logging()

try:
    tts_service = TikTokTTS()
except Exception as e:
    logger.error(f"Error initializing TikTokTTS: {e}", exc_info=True)
    tts_service = None


def _generate_display_name(voice_id):
    parts = voice_id.split('-')
    if len(parts) >= 3:
        name = parts[-1].replace("Neural", "")
        region_code = f"{parts[0]}-{parts[1]}"
        return f"{name} ({region_code})"
    logger.info(f"Generating display name for voice_id: {voice_id}")
    return voice_id


def _get_flat_voices(formatted_voices):
    flat_list = []
    for lang, genders in formatted_voices.items():
        for gender, voices in genders.items():
            for voice_entry in voices:
                if isinstance(voice_entry, str):
                    voice_id = voice_entry
                    display_name = _generate_display_name(voice_id)
                elif isinstance(voice_entry, dict):
                    voice_id = voice_entry.get("voice_id")
                    display_name = voice_entry.get("display_name")
                    if not voice_id: continue
                    if not display_name: display_name = _generate_display_name(voice_id)
                else:
                    continue

                flat_list.append({
                    "language": lang,
                    "gender": gender,
                    "display_name": display_name,
                    "voice_id": voice_id
                })
    return flat_list


try:
    logger.info("Pre-processing Edge voice list for faster access.")
    ALL_EDGE_VOICES_FLAT = _get_flat_voices(EDGE_FORMATTED_VOICES)
except Exception as e:
    logger.error(f"Error pre-processing Edge voice list: {e}", exc_info=True)
    ALL_EDGE_VOICES_FLAT = []


def get_list_engines():
    logger.info(f"Getting list of available Edge voice engines: {EDGE_ENGINE}")
    return jsonify({"engines": [TIKTOK_ENGINE, EDGE_ENGINE]}), 200


def get_list_languages():
    data = request.get_json()
    if not data:
        logger.error("Get list languages failed: No data provided.")
        raise MissingParameterException("Missing request body")

    engine = data.get("engine", TIKTOK_ENGINE)
    engine = engine.lower() if engine else TIKTOK_ENGINE

    languages = []
    if engine == EDGE_ENGINE:
        languages = list(EDGE_FORMATTED_VOICES.keys())
    elif engine == TIKTOK_ENGINE and tts_service:
        languages = list(TIKTOK_FORMATTED_VOICES.keys())
    elif engine == TIKTOK_ENGINE and not tts_service:
        logger.error("Get list languages failed: TikTok TTS service unavailable during initialization.")
        raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")
    else:
        logger.error("Get list languages failed: Engine not supported.")
        raise ServiceUnavailableException("Engine not supported")

    return jsonify({"languages": sorted(list(set(languages)))}), 200


def filter_voices():
    data = request.get_json()
    if not data:
        logger.error("Filer voices failed: No data provided.")
        raise MissingParameterException("Missing request body")

    engine = data.get("engine")
    language = data.get("language")
    gender_filter = data.get("gender", ALL).lower()

    if not engine:
        logger.error("Filer voices failed: Engine not provided.")
        raise MissingParameterException("Missing required fields: engine")
    engine = engine.lower()

    if not language:
        logger.error("Filer voices failed: Language not provided.")
        raise MissingParameterException("Missing required fields: language")

    if engine == EDGE_ENGINE:
        source_voices = ALL_EDGE_VOICES_FLAT
        voices = [v for v in source_voices if v["language"].lower() == language.lower()]

        if gender_filter == FEMALE:
            voices = [v for v in voices if v["gender"].lower() == FEMALE]
        elif gender_filter == MALE:
            voices = [v for v in voices if v["gender"].lower() == MALE]
        elif gender_filter != ALL:
            logger.error(f"Filer voices failed: Unknown gender: {gender_filter}")
            raise BadRequestException(f"Invalid gender: {gender_filter}")

        logger.info(f"Filer voices returned {len(voices)} voices.")
        return jsonify({"voices": voices}), 200

    elif engine == TIKTOK_ENGINE:
        if not tts_service:
            logger.error("Get list languages failed: TikTok TTS service unavailable during initialization.")
            raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")
        if language not in TIKTOK_FORMATTED_VOICES:
            return jsonify({"voices": []}), 200

        lang_voices = TIKTOK_FORMATTED_VOICES[language]
        result_voices = []

        genders_to_include = []
        if gender_filter == FEMALE:
            genders_to_include = [FEMALE.title()]
        elif gender_filter == MALE:
            genders_to_include = [MALE.title()]
        elif gender_filter == ALL:
            genders_to_include = list(lang_voices.keys())
        else:
            logger.error(f"Filer voices failed: Unknown gender: {gender_filter}")
            raise BadRequestException(f"Invalid gender: {gender_filter}")

        for gender in genders_to_include:
            gender_key = gender
            if gender_key in lang_voices:
                for voice_entry in lang_voices[gender_key]:
                    voice_id = voice_entry
                    display_name = voice_id
                    result_voices.append({
                        "language": language,
                        "gender": gender_key,
                        "display_name": display_name,
                        "voice_id": voice_id
                    })

        logger.info(f"Filer voices returned {len(result_voices)} voices.")
        return jsonify({"voices": result_voices}), 200

    else:
        logger.error("Filer voices failed: Unknown engine.")
        raise BadRequestException("Engine not supported")


def process_text_part(text_part: str, idx: int, voice: str, results_list: list):
    try:
        if not tts_service:
            logger.error("Process_text_part failed: TikTok TTS service unavailable during initialization.")
            results_list[idx] = "error_service_unavailable"
            return

        audio = tts_service.generate_audio(text_part, voice)
        base64_data = tts_service.extract_base64_data(audio)

        if base64_data == "error":
            logger.error(f"TTS generation failed for voice {voice} (part {idx + 1}) - Voice unavailable?")
            results_list[idx] = "error_voice_unavailable"
        else:
            results_list[idx] = base64_data
    except Exception as e:
        logger.error(f"Exception in thread for part {idx}: {e}", exc_info=True)
        results_list[idx] = "error_exception"


def change_audio_speed(input_path: str, output_path: str, speed: float, ffmpeg_timeout: int = 30):
    if not (0.25 <= speed <= 2.0):
        logger.error(f"Speed {speed} out of supported range (0.25-2.0). Skipping speed change.")
        return False

    if math.isclose(speed, 1.0, rel_tol=1e-09, abs_tol=1e-09):
        return False

    try:
        subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
    except FileNotFoundError:
        logger.error("ffmpeg command not found. Cannot change audio speed. Is ffmpeg installed and in PATH?")
        raise ResourceNotFoundException("ffmpeg command not found. Cannot change audio speed.")
    except subprocess.CalledProcessError:
        logger.error("Error checking ffmpeg version.")
        raise ResourceNotFoundException("ffmpeg command not found. Cannot change audio speed.")
    except Exception as e:
        logger.error(f"Unexpected error during change audio speed: {e}", exc_info=True)
        raise InternalServerException("Unexpected error during change audio speed")

    tempo_filters = []
    current_speed = speed
    while current_speed < 0.5:
        tempo_filters.append("atempo=0.5")
        current_speed /= 0.5
    tempo_filters.append(f"atempo={current_speed}")

    filter_complex = ",".join(tempo_filters)

    command = [
        'ffmpeg',
        '-i', input_path,
        '-filter:a', filter_complex,
        '-vn',
        '-y',
        output_path
    ]

    try:
        logger.info(f"Applying speed {speed}x using ffmpeg: {' '.join(command)}")
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=ffmpeg_timeout)
        logger.info(f"ffmpeg speed change successful for {input_path}.")
        logger.debug(f"ffmpeg stdout: {result.stdout}")
        logger.debug(f"ffmpeg stderr: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg speed change failed with code {e.returncode}")
        logger.error(f"ffmpeg stderr: {e.stderr}")
        raise InternalServerException(f"ffmpeg failed: {e.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg speed change process timed out.")
        raise InternalServerException("ffmpeg timed out")
    except Exception as e:
        logger.error(f"Unexpected error during ffmpeg processing: {e}", exc_info=True)
        raise InternalServerException("ffmpeg unexpected error")


def generate_tts():
    filename = None
    temp_speed_file = None  # Keep track of the temporary speed file

    def cleanup_files(response):
        file_to_delete = g.pop('tts_filename', None)
        temp_file_to_delete = g.pop('tts_temp_speed_filename', None)

        if temp_file_to_delete and os.path.exists(temp_file_to_delete):
            try:
                os.remove(temp_file_to_delete)
                logger.info(f"Deleted temporary speed file: {temp_file_to_delete}")
            except OSError as e:
                logger.error(f"Error deleting temp speed file {temp_file_to_delete}: {e}")

        if file_to_delete and os.path.exists(file_to_delete):
            try:
                os.remove(file_to_delete)
                logger.info(f"Deleted final TTS file: {file_to_delete}")
            except OSError as e:
                logger.error(f"Error deleting file {file_to_delete}: {e}")

        return response

    after_this_request(cleanup_files)

    try:
        data = request.get_json()
        if not data:
            logger.error("Generate TTS failed: No input data provided.")
            raise InvalidCredentialsException("No input data provided.")

        engine = data.get("engine", TIKTOK_ENGINE).lower()
        text = data.get("text")
        voice = data.get("voice_id")
        try:
            speed = float(data.get("speed", 1.0))
            if not (0.25 <= speed <= 2.0):
                logger.error(f"Received invalid speed {speed}. Defaulting to 1.0.")
                speed = 1.0
        except (ValueError, TypeError):
            logger.error(f"Received non-numeric speed '{data.get('speed')}''. Defaulting to 1.0.")
            speed = 1.0

        base_filename = f"tts_{uuid4()}"
        filename = os.path.join(os.getcwd(), f"{base_filename}.mp3")
        g.tts_filename = filename  # Store final filename for cleanup

        if not text:
            logger.error("Generate TTS failed: text is required.")
            raise MissingParameterException("Missing required fields: text")
        if not voice:
            logger.error("Generate TTS failed: voice is required.")
            raise MissingParameterException("Missing required fields: voice")
        if engine not in [TIKTOK_ENGINE, EDGE_ENGINE]:
            logger.error(f"Generate TTS failed: Engine '{engine}' not supported.")
            raise BadRequestException(f"Engine '{engine}' not supported.")

        # --- Edge TTS ---
        if engine == EDGE_ENGINE:
            if math.isclose(speed, 1.0, rel_tol=1e-09, abs_tol=1e-09):
                rate = "+0%"
            else:
                percentage = int((speed - 1.0) * 100)
                rate = f"{'+' if percentage >= 0 else ''}{percentage}%"
            logger.info(f"Setting Edge TTS rate to {rate} for speed {speed}x")

            command = [
                'edge-tts',
                f'--rate={rate}',
                '--voice', voice,
                '--text', text,
                '--write-media', filename
            ]
            try:
                result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
                logger.info("Edge TTS process completed successfully.")
                logger.debug(f"Edge TTS stdout: {result.stdout}")
                logger.debug(f"Edge TTS stderr: {result.stderr}")
            except FileNotFoundError:
                logger.error("edge-tts command not found. Is it installed and in PATH?")
                raise InternalServerException("TTS engine tool not found on server")
            except subprocess.CalledProcessError as e:
                logger.error(f"Edge TTS process failed with code {e.returncode}")
                logger.error(f"Edge TTS stderr: {e.stderr}")
                raise InternalServerException(f"Edge TTS generation failed: {e.stderr[:200]}")
            except subprocess.TimeoutExpired:
                logger.error("Edge TTS process timed out.")
                raise InternalServerException("TTS generation timed out")

            if not os.path.exists(filename):
                logger.error(f"Edge TTS command ran but output file not found: {filename}")
                raise InternalServerException("Failed to generate audio file (post-process check)")

            # Edge TTS handles speed directly, so file is ready
            return send_file(
                filename,
                mimetype="audio/mp3",
                as_attachment=False,
            )

        # --- TikTok TTS ---
        elif engine == TIKTOK_ENGINE:
            if not tts_service:
                logger.error("Generate TTS failed: TikTok TTS service unavailable during initialization.")
                raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")

            try:
                is_available = tts_service.check_api_availability()
                if not is_available:
                    logger.error("Generate TTS failed: TikTok TTS service unavailable during initialization.")
                    raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")
            except AttributeError:
                logger.debug("TikTokTTS class does not have 'check_api_availability'. Skipping check.")
            except Exception as api_check_err:
                logger.error(f"Error checking TikTok API status: {api_check_err}", exc_info=True)
                raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")

            limit = 70

            # Generate Audio
            generated_base64_data = None
            if len(text) < limit:
                audio = tts_service.generate_audio(text, voice)
                generated_base64_data = tts_service.extract_base64_data(audio)
                if generated_base64_data == "error":
                    logger.error(f"TikTok TTS failed for voice {voice} (short text) - unavailable?")
                    raise ServiceUnavailableException("TikTok TTS service unavailable during initialization.")
            else:
                text_parts = tts_service.split_string(text, limit)
                part_results = [None] * len(text_parts)
                threads = []

                for i, part in enumerate(text_parts):
                    thread = threading.Thread(target=process_text_part, args=(part, i, voice, part_results))
                    thread.start()
                    threads.append(thread)

                for thread in threads:
                    thread.join()

                final_base64_parts = []
                for i, result in enumerate(part_results):
                    if result is None:
                        logger.error(f"TTS Error: Thread for part {i + 1} did not produce a result.")
                        raise InternalServerException(f"Internal error processing part {i + 1}")
                    elif result.startswith("error_"):
                        logger.error(f"TTS Error in part {i + 1}: {result}")
                        error_msg = "An error occurred during TTS generation."
                        if result == "error_voice_unavailable":
                            error_msg = "Selected voice is unavailable for a part of the text."
                        elif result == "error_service_unavailable":
                            error_msg = "TTS service became unavailable during processing."
                        raise InternalServerException(error_msg)
                    else:
                        final_base64_parts.append(result)

                if not final_base64_parts:
                    logger.error("TTS Error: No successful parts generated.")
                    raise InternalServerException("Failed to generate any audio parts")

                generated_base64_data = "".join(final_base64_parts)

            # Save the initially generated (normal speed) audio
            tts_service.save_audio_file(generated_base64_data, filename)

            if not os.path.exists(filename):
                logger.error(f"Audio file expected but not found after TikTok processing: {filename}")
                raise InternalServerException("Failed to generate or save initial audio file")

            if not math.isclose(speed, 1.0, rel_tol=1e-09, abs_tol=1e-09):
                temp_speed_file = os.path.join(os.getcwd(), f"{base_filename}_speed_{speed}x.mp3")
                g.tts_temp_speed_filename = temp_speed_file  # Store for cleanup

                try:
                    logger.info(f"Attempting to change speed to {speed}x for TikTok audio: {filename}")
                    changed_successfully = change_audio_speed(filename, temp_speed_file, speed)

                    if changed_successfully:
                        # Replace original with speed-changed file
                        logger.info(f"Replacing original file {filename} with speed-adjusted file {temp_speed_file}")
                        os.replace(temp_speed_file, filename)  # Atomically replace if possible
                        # No need to delete temp_speed_file explicitly if os.replace succeeds
                        g.pop('tts_temp_speed_filename', None)  # Remove from cleanup list as it's now the main file
                    else:
                        # Speed was 1.0 or out of range, use original file
                        logger.info(f"Speed change not applied (speed={speed}). Using original file.")
                        # Clean up the potentially created (but unused) temp file if it exists
                        if os.path.exists(temp_speed_file):
                            try:
                                os.remove(temp_speed_file)
                            except OSError:
                                pass

                except RuntimeError as ffmpeg_err:
                    logger.error(f"ffmpeg processing failed: {ffmpeg_err}. Sending original speed audio.")
                    if temp_speed_file and os.path.exists(temp_speed_file):
                        try:
                            os.remove(temp_speed_file)
                        except OSError:
                            pass
                    # Send the original file as a fallback
                    return send_file(filename, mimetype="audio/mp3", as_attachment=False)
                except Exception as e:
                    logger.error(f"Unexpected error during speed adjustment post-processing: {e}", exc_info=True)
                    if temp_speed_file and os.path.exists(temp_speed_file):
                        try:
                            os.remove(temp_speed_file)
                        except OSError:
                            pass
                    raise InternalServerException("Error during audio speed adjustment")

            if not os.path.exists(filename):
                logger.error(f"Final audio file not found before sending: {filename}")
                raise InternalServerException("Failed to process audio file")

            return send_file(
                filename,
                mimetype="audio/mp3",
                as_attachment=False,
            )
        raise ValueError(f"Unsupported engine: {engine}")

    except Exception as e:
        logger.error(f"Unhandled error in generate_tts: {str(e)}", exc_info=True)
        if filename and os.path.exists(filename) and 'tts_filename' not in g:
            try:
                os.remove(filename)
            except OSError:
                pass
        if temp_speed_file and os.path.exists(temp_speed_file) and 'tts_temp_speed_filename' not in g:
            try:
                os.remove(temp_speed_file)
            except OSError:
                pass

        raise InternalServerException("An unexpected server error occurred during TTS generation.")


def cleanup_files(files_to_delete):
    for f_path in files_to_delete:
        try:
            if os.path.exists(f_path):
                os.remove(f_path)
                logger.info(f"Cleaned up temp file: {f_path}")
        except OSError as e:
            logger.error(f"Error cleaning up file {f_path}: {e}")


@jwt_required()
def concatenate_and_upload():
    temp_files = []
    output_filename = None
    try:
        files = request.files
        if not files:
            logger.error("Concatenate and upload failed: No files provided.")
            raise MissingParameterException("No audio files provided")

        file_paths_ordered = {}
        for key in files:
            if key.startswith("audio_part_"):
                try:
                    index = int(key.split("_")[-1])
                    file = files[key]
                    if file and file.filename:
                        temp_filename = os.path.join(os.getcwd(), f"{uuid4()}.mp3")
                        file.save(temp_filename)
                        file_paths_ordered[index] = temp_filename
                        temp_files.append(temp_filename)  # Add to list for cleanup
                        logger.info(f"Saved part {index} to {temp_filename}")
                    else:
                        logger.error(f"Skipping invalid file part: {key}")
                except (ValueError, IndexError) as e:
                    logger.error(f"Could not parse index from key {key}: {e}")
                    continue

        if not file_paths_ordered:
            logger.error("Concatenate and upload failed: No valid audio parts received.")
            raise ResourceNotFoundException("No valid audio parts received.")

        # Sort paths by index
        sorted_paths = [path for idx, path in sorted(file_paths_ordered.items())]

        if not sorted_paths:
            logger.error("Concatenate and upload failed: No audio files to process after sorting.")
            raise ResourceNotFoundException("No audio files to process after sorting")

        output_filename = os.path.join(os.getcwd(), f"final_{uuid4()}.mp3")
        temp_files.append(output_filename)

        # Create the concat file list for ffmpeg
        concat_list_path = os.path.join(os.getcwd(), f"concat_list_{uuid4()}.txt")
        temp_files.append(concat_list_path)
        try:
            with open(concat_list_path, 'w') as f:
                for path in sorted_paths:
                    # Need to escape special characters if paths might contain them
                    # For simplicity here, assuming basic paths
                    f.write(f"file '{os.path.abspath(path)}'\n")  # Use absolute paths

            # Using the concat demuxer is safer than direct concat protocol
            command = [
                'ffmpeg',
                '-f', 'concat',  # Use the concat demuxer
                '-safe', '0',  # Allow relative paths in list if needed (though abspath is better)
                '-i', concat_list_path,  # Input is the list file
                '-c', 'copy',  # Copy codec, faster if formats match
                '-y',  # Overwrite output if exists
                output_filename
            ]

            logger.info(f"Running ffmpeg command: {' '.join(command)}")
            result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
            logger.info("ffmpeg concatenation successful.")
            logger.debug(f"ffmpeg stdout: {result.stdout}")
            logger.debug(f"ffmpeg stderr: {result.stderr}")

        except FileNotFoundError:
            logger.error("ffmpeg command not found. Is it installed and in PATH?")
            raise InternalServerException("Audio processing tool (ffmpeg) not found on server")
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg concatenation failed with code {e.returncode}")
            logger.error(f"ffmpeg stderr: {e.stderr}")
            raise InternalServerException(f"Audio concatenation failed: {e.stderr[:200]}")
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg concatenation timed out.")
            raise InternalServerException("Audio concatenation timed out")
        except Exception as e:
            logger.error(f"Error during ffmpeg list creation or execution: {e}", exc_info=True)
            raise InternalServerException("An unexpected error occurred during audio concatenation")

        if not os.path.exists(output_filename) or os.path.getsize(output_filename) == 0:
            logger.error(f"Concatenated file not found or empty: {output_filename}")
            raise InternalServerException("Failed to create final audio file")

        logger.info(f"Uploading {output_filename} to Cloudinary...")
        try:
            unique_id = str(uuid4())
            current_user = get_jwt_identity()
            user = User.query.get(current_user)
            public_id = f"{AUDIO_FOLDER}/{user.id}/{unique_id}"
            upload_options = {
                "resource_type": "video",
                "public_id": public_id,
                "overwrite": True,
            }
            upload_result = cloudinary.uploader.upload(output_filename, **upload_options)
            logger.info("Upload to Cloudinary successful.")
            logger.debug("Cloudinary upload result: %s", upload_result)

            final_url = upload_result.get('secure_url')
            if not final_url:
                logger.error("Cloudinary upload result missing secure_url")
                raise InternalServerException("Upload succeeded but failed to get URL")

            return jsonify({"cloudinary_url": final_url}), 200

        except Exception as e:
            logger.error(f"Cloudinary upload failed: {e}", exc_info=True)
            raise InternalServerException("Failed to upload final audio to storage")

    finally:
        cleanup_files(temp_files)
