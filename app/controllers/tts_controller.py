import os
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


def generate_tts():
    filename = None

    def cleanup_file(response):
        file_to_delete = g.pop('tts_filename', None)
        if file_to_delete and os.path.exists(file_to_delete):
            try:
                os.remove(file_to_delete)
                logger.info(f"Deleted temporary file: {file_to_delete}")
            except OSError as e:
                logger.error(f"Error deleting file {file_to_delete}: {e}")
        return response

    after_this_request(cleanup_file)

    try:
        data = request.get_json()
        if not data:
            return jsonify({"msg": "No data provided"}), 400

        engine = data.get("engine", TIKTOK_ENGINE).lower()
        text = data.get("text")
        voice = data.get("voice_id")

        filename = os.path.join(current_app.config.get('TEMP_FOLDER', os.getcwd()), f"tts_{uuid4()}.mp3")
        g.tts_filename = filename

        if not text:
            return jsonify({"msg": "Text is required"}), 400
        if not voice:
            return jsonify({"msg": "Voice is required"}), 400
        if engine not in [TIKTOK_ENGINE, EDGE_ENGINE]:
            return jsonify({"msg": f"Engine '{engine}' not supported"}), 404

        # --- Edge TTS ---
        if engine == EDGE_ENGINE:
            rate = "+0%"
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
                    {"msg": f"Edge TTS generation failed: {e.stderr[:200]}"}), 500  # Return part of the error
            except subprocess.TimeoutExpired:
                logger.error("Edge TTS process timed out.")
                return jsonify({"msg": "TTS generation timed out"}), 500

            if not os.path.exists(filename):
                logger.error(f"Edge TTS command ran but output file not found: {filename}")
                return jsonify({"msg": "Failed to generate audio file (post-process check)"}), 500

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

            # Check API availability (assuming tts_service handles this logic now)
            # Maybe add a specific check method to tts_service?
            try:
                # Example check: (replace with actual check if available in TikTokTTS class)
                is_available = tts_service.check_api_availability()
                if not is_available:
                    logger.warning("TikTok TTS API check failed.")
                    return jsonify({"msg": "TTS service unavailable or rate limited"}), 503
            except AttributeError:
                logger.warning("TikTokTTS class does not have 'check_api_availability'. Skipping check.")
            except Exception as api_check_err:
                logger.error(f"Error checking TikTok API status: {api_check_err}", exc_info=True)
                return jsonify({"msg": "Error contacting TTS service"}), 503

            limit = 70

            # Generate Audio
            if len(text) < limit:
                audio = tts_service.generate_audio(text, voice)
                audio_base64_data = tts_service.extract_base64_data(audio)

                if audio_base64_data == "error":
                    logger.warning(f"TikTok TTS failed for voice {voice} (short text) - unavailable?")
                    return jsonify(
                        {"msg": "This voice might be unavailable or an error occurred"}), 400  # Use 400 or 500

                tts_service.save_audio_file(audio_base64_data, filename)
            else:
                text_parts = tts_service.split_string(text, limit)
                # Use a list pre-filled with None to store results/errors
                part_results = [None] * len(text_parts)
                threads = []

                for i, part in enumerate(text_parts):
                    thread = threading.Thread(
                        target=process_text_part,
                        args=(part, i, voice, part_results)
                    )
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
                        # Handle specific errors reported by the thread
                        logger.error(f"TTS Error in part {i + 1}: {result}")
                        error_msg = "An error occurred during TTS generation."
                        if result == "error_voice_unavailable":
                            error_msg = "Selected voice is unavailable for a part of the text."
                        elif result == "error_service_unavailable":
                            error_msg = "TTS service became unavailable during processing."
                        return jsonify({"msg": error_msg}), 500  # Or specific code
                    else:
                        # Append successful base64 data
                        final_base64_parts.append(result)

                # Combine successful parts
                if not final_base64_parts:
                    logger.error("TTS Error: No successful parts generated.")
                    return jsonify({"msg": "Failed to generate any audio parts"}), 500

                combined_audio_base64_data = "".join(final_base64_parts)
                tts_service.save_audio_file(combined_audio_base64_data, filename)

            if not os.path.exists(filename):
                logger.error(f"Audio file expected but not found after processing: {filename}")
                return jsonify({"msg": "Failed to generate or save audio file"}), 500

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
                logger.info(f"Cleaned up file manually after error: {filename}")
            except OSError as clean_err:
                logger.error(f"Manual cleanup failed for {filename}: {clean_err}")

        return jsonify({
            "msg": "An unexpected server error occurred during TTS generation.",
        }), 500
