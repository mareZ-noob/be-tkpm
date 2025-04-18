import math
import os
import shutil
import threading
from uuid import uuid4
import subprocess
import logging

from flask import g, jsonify, request, send_file, current_app, after_this_request
from app.utils.constant import ALL, EDGE_ENGINE, FEMALE, MALE, TIKTOK_ENGINE
from app.utils.voice.edge_voices import EDGE_FORMATTED_VOICES
from app.utils.voice.tiktok_tts import TikTokTTS
from app.utils.voice.tiktok_voices import TIKTOK_FORMATTED_VOICES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    tts_service = TikTokTTS()
except Exception as e:
    logger.error(f"Error initializing TikTokTTS: {e}", exc_info=True)
    tts_service = None


def _generate_display_name(voice_id: str) -> str:
    parts = voice_id.split('-')
    if len(parts) >= 3:
        name = parts[-1].replace("Neural", "")
        region_code = f"{parts[0]}-{parts[1]}"
        return f"{name} ({region_code})"
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
    ALL_EDGE_VOICES_FLAT = _get_flat_voices(EDGE_FORMATTED_VOICES)
except Exception as e:
    logger.error(f"Error pre-processing Edge voice list: {e}", exc_info=True)
    ALL_EDGE_VOICES_FLAT = []


def get_list_engines():
    return jsonify({"engines": [TIKTOK_ENGINE, EDGE_ENGINE]}), 200


def get_list_languages():
    data = request.get_json()
    if not data:
        return jsonify({"msg": "Missing request body"}), 400

    engine = data.get("engine", TIKTOK_ENGINE)
    engine = engine.lower() if engine else TIKTOK_ENGINE

    languages = []
    if engine == EDGE_ENGINE:
        languages = list(EDGE_FORMATTED_VOICES.keys())
    elif engine == TIKTOK_ENGINE and tts_service:
        languages = list(TIKTOK_FORMATTED_VOICES.keys())
    elif engine == TIKTOK_ENGINE and not tts_service:
        return jsonify({"msg": "TikTok TTS service not available"}), 503
    else:
        return jsonify({"msg": f"Engine '{engine}' not supported"}), 404

    return jsonify({"languages": sorted(list(set(languages)))}), 200


def filter_voices():
    data = request.get_json()
    if not data:
        return jsonify({"msg": "Missing request body"}), 400

    engine = data.get("engine")
    language = data.get("language")
    gender_filter = data.get("gender", ALL).lower()

    if not engine:
        return jsonify({"msg": "Engine is required"}), 400
    engine = engine.lower()

    if not language:
        return jsonify({"msg": "Language is required"}), 400

    if engine == EDGE_ENGINE:
        source_voices = ALL_EDGE_VOICES_FLAT
        voices = [v for v in source_voices if v["language"].lower() == language.lower()]

        if gender_filter == FEMALE:
            voices = [v for v in voices if v["gender"].lower() == FEMALE]
        elif gender_filter == MALE:
            voices = [v for v in voices if v["gender"].lower() == MALE]
        elif gender_filter != ALL:
            return jsonify({"msg": f"Invalid gender filter: '{gender_filter}'"}), 400

        return jsonify({"voices": voices}), 200

    elif engine == TIKTOK_ENGINE:
        if not tts_service:
            return jsonify({"msg": "TikTok TTS service not available"}), 503
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
            return jsonify({"msg": f"Invalid gender filter: '{gender_filter}'"}), 400

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

        return jsonify({"voices": result_voices}), 200

    else:
        return jsonify({"msg": f"Engine '{engine}' not supported"}), 404


def process_text_part(text_part: str, idx: int, voice: str, results_list: list):
    try:
        if not tts_service:
            results_list[idx] = "error_service_unavailable"
            return

        audio = tts_service.generate_audio(text_part, voice)
        base64_data = tts_service.extract_base64_data(audio)

        if base64_data == "error":
            logger.warning(f"TTS generation failed for voice {voice} (part {idx + 1}) - Voice unavailable?")
            results_list[idx] = "error_voice_unavailable"
        else:
            results_list[idx] = base64_data
    except Exception as e:
        logger.error(f"Exception in thread for part {idx}: {e}", exc_info=True)
        results_list[idx] = "error_exception"


def change_audio_speed(input_path: str, output_path: str, speed: float, ffmpeg_timeout: int = 30):
    """Changes the speed of an audio file using ffmpeg."""
    if not (0.25 <= speed <= 2.0):
        logger.warning(f"Speed {speed} out of supported range (0.25-2.0). Skipping speed change.")
        return False

    if speed == 1.0:
        return False

    try:
        subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True)
    except FileNotFoundError:
        logger.error("ffmpeg command not found. Cannot change audio speed. Is ffmpeg installed and in PATH?")
        raise RuntimeError("ffmpeg not found")
    except subprocess.CalledProcessError:
        logger.error("Error checking ffmpeg version.")
        raise RuntimeError("ffmpeg error")

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
        raise RuntimeError(f"ffmpeg failed: {e.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg speed change process timed out.")
        raise RuntimeError("ffmpeg timed out")
    except Exception as e:
        logger.error(f"Unexpected error during ffmpeg processing: {e}", exc_info=True)
        raise RuntimeError("ffmpeg unexpected error")


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
            return jsonify({"msg": "No data provided"}), 400

        engine = data.get("engine", TIKTOK_ENGINE).lower()
        text = data.get("text")
        voice = data.get("voice_id")
        try:
            speed = float(data.get("speed", 1.0))
            if not (0.25 <= speed <= 2.0):
                logger.warning(f"Received invalid speed {speed}. Defaulting to 1.0.")
                speed = 1.0
        except (ValueError, TypeError):
            logger.warning(f"Received non-numeric speed '{data.get('speed')}''. Defaulting to 1.0.")
            speed = 1.0

        base_filename = f"tts_{uuid4()}"
        filename = os.path.join(os.getcwd(), f"{base_filename}.mp3")
        g.tts_filename = filename  # Store final filename for cleanup

        if not text:
            return jsonify({"msg": "Text is required"}), 400
        if not voice:
            return jsonify({"msg": "Voice is required"}), 400
        if engine not in [TIKTOK_ENGINE, EDGE_ENGINE]:
            return jsonify({"msg": f"Engine '{engine}' not supported"}), 404

        # --- Edge TTS ---
        if engine == EDGE_ENGINE:
            if speed == 1.0:
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
                return jsonify({"msg": "TTS engine tool not found on server"}), 500
            except subprocess.CalledProcessError as e:
                logger.error(f"Edge TTS process failed with code {e.returncode}")
                logger.error(f"Edge TTS stderr: {e.stderr}")
                return jsonify(
                    {"msg": f"Edge TTS generation failed: {e.stderr[:200]}"}), 500
            except subprocess.TimeoutExpired:
                logger.error("Edge TTS process timed out.")
                return jsonify({"msg": "TTS generation timed out"}), 500

            if not os.path.exists(filename):
                logger.error(f"Edge TTS command ran but output file not found: {filename}")
                return jsonify({"msg": "Failed to generate audio file (post-process check)"}), 500

            # Edge TTS handles speed directly, so file is ready
            return send_file(
                filename,
                mimetype="audio/mp3",
                as_attachment=False,
            )

        # --- TikTok TTS ---
        elif engine == TIKTOK_ENGINE:
            if not tts_service:
                logger.error("TikTok TTS service requested but not initialized.")
                return jsonify({"msg": "TikTok TTS service is unavailable"}), 503

            try:
                is_available = tts_service.check_api_availability()
                if not is_available:
                    logger.warning("TikTok TTS API check failed.")
                    return jsonify({"msg": "TTS service unavailable or rate limited"}), 503
            except AttributeError:
                logger.debug("TikTokTTS class does not have 'check_api_availability'. Skipping check.")
            except Exception as api_check_err:
                logger.error(f"Error checking TikTok API status: {api_check_err}", exc_info=True)
                return jsonify({"msg": "Error contacting TTS service"}), 503

            limit = 70

            # Generate Audio
            generated_base64_data = None
            if len(text) < limit:
                audio = tts_service.generate_audio(text, voice)
                generated_base64_data = tts_service.extract_base64_data(audio)
                if generated_base64_data == "error":
                    logger.warning(f"TikTok TTS failed for voice {voice} (short text) - unavailable?")
                    return jsonify({"msg": "This voice might be unavailable or an error occurred"}), 400  # Or 500
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
                        return jsonify({"msg": f"Internal error processing part {i + 1}"}), 500
                    elif result.startswith("error_"):
                        logger.error(f"TTS Error in part {i + 1}: {result}")
                        error_msg = "An error occurred during TTS generation."
                        if result == "error_voice_unavailable":
                            error_msg = "Selected voice is unavailable for a part of the text."
                        elif result == "error_service_unavailable":
                            error_msg = "TTS service became unavailable during processing."
                        return jsonify({"msg": error_msg}), 500
                    else:
                        final_base64_parts.append(result)

                if not final_base64_parts:
                    logger.error("TTS Error: No successful parts generated.")
                    return jsonify({"msg": "Failed to generate any audio parts"}), 500

                generated_base64_data = "".join(final_base64_parts)

            # Save the initially generated (normal speed) audio
            tts_service.save_audio_file(generated_base64_data, filename)

            if not os.path.exists(filename):
                logger.error(f"Audio file expected but not found after TikTok processing: {filename}")
                return jsonify({"msg": "Failed to generate or save initial audio file"}), 500

            # --- NEW: Apply speed change using ffmpeg if speed is not 1.0 ---
            if speed != 1.0:
                # Create a temporary filename for the speed-adjusted audio
                temp_speed_file = os.path.join(current_app.config.get('TEMP_FOLDER', os.getcwd()),
                                               f"{base_filename}_speed_{speed}x.mp3")
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
                                pass  # Ignore error if it was already gone

                except RuntimeError as ffmpeg_err:
                    # ffmpeg failed (not found, error, timeout)
                    logger.error(f"ffmpeg processing failed: {ffmpeg_err}. Sending original speed audio.")
                    # Clean up the failed temp file if it exists
                    if temp_speed_file and os.path.exists(temp_speed_file):
                        try:
                            os.remove(temp_speed_file)
                        except OSError:
                            pass
                    # Send the original file as a fallback
                    return send_file(filename, mimetype="audio/mp3", as_attachment=False)
                except Exception as e:
                    logger.error(f"Unexpected error during speed adjustment post-processing: {e}", exc_info=True)
                    # Clean up potential temp file
                    if temp_speed_file and os.path.exists(temp_speed_file):
                        try:
                            os.remove(temp_speed_file)
                        except OSError:
                            pass
                    # Fallback to original file might be okay, or return server error
                    return jsonify({"msg": "Error during audio speed adjustment"}), 500


            if not os.path.exists(filename):
                logger.error(f"Final audio file not found before sending: {filename}")
                return jsonify({"msg": "Failed to process audio file"}), 500

            return send_file(
                filename,
                mimetype="audio/mp3",
                as_attachment=False,
            )

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

        return jsonify({
            "msg": "An unexpected server error occurred during TTS generation.",
        }), 500

