import os
import threading
from uuid import uuid4

from flask import g, jsonify, request, send_file

from app.utils.constant import ALL, EDGE_ENGINE, FEMALE, MALE, TIKTOK_ENGINE
from app.utils.voice.edge_voices import EDGE_FORMATTED_VOICES
from app.utils.voice.tiktok_tts import TikTokTTS
from app.utils.voice.tiktok_voices import TIKTOK_FORMATTED_VOICES

tts_service = TikTokTTS()


# @jwt_required()
def get_list_languages():
    data = request.get_json()
    engine = data.get("engine", TIKTOK_ENGINE)
    engine = engine.lower()

    if engine == EDGE_ENGINE:
        return list(EDGE_FORMATTED_VOICES.keys())
    elif engine == TIKTOK_ENGINE:
        return list(TIKTOK_FORMATTED_VOICES.keys())
    else:
        return []


# @jwt_required()
def filter_voices():
    data = request.get_json()
    engine = data.get("engine", TIKTOK_ENGINE).lower()
    language = data.get("language", "English")
    gender = data.get("gender", ALL).lower()

    if engine == EDGE_ENGINE:
        voices_dict = EDGE_FORMATTED_VOICES
    elif engine == TIKTOK_ENGINE:
        voices_dict = TIKTOK_FORMATTED_VOICES
    else:
        return jsonify({"msg": "Engine not found"}), 404

    if language not in voices_dict:
        return jsonify({"msg": "Language not found"}), 404

    voices = voices_dict[language]

    if gender == FEMALE:
        voices = voices.get("Female", [])
    elif gender == MALE:
        voices = voices.get("Male", [])
    elif gender == ALL:
        female_voices = voices.get("Female", [])
        male_voices = voices.get("Male", [])
        voices = female_voices + male_voices
    else:
        return jsonify({"msg": "Gender not found"}), 404

    if voices:
        return jsonify({"voices": voices}), 200
    else:
        return jsonify({"msg": "No voices found"}), 404


def generate_tts():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"msg": "No data provided"}), 400

        engine = data.get("engine", TIKTOK_ENGINE)
        text = data.get("text")
        language = data.get("language", "English")
        voice = data.get("voice")
        filename = os.path.join(os.getcwd(), f"tts_{uuid4()}.mp3")

        g.tts_filename = filename

        limit = 100
        if language == "Japanese":
            limit = 70

        if not text:
            return jsonify({"msg": "Text is required"}), 400
        if not voice:
            return jsonify({"msg": "Voice is required"}), 400
        if engine != TIKTOK_ENGINE and engine != EDGE_ENGINE:
            return jsonify({"msg": "Engine not found"}), 404

        if engine == EDGE_ENGINE:
            rate = "+0%"
            payload = f"edge-tts --rate={rate} --voice {voice} --text '{text}' --write-media {filename}"
            os.popen(payload).read()

            response = send_file(
                filename,
                mimetype="audio/mp3",
                as_attachment=False,
            )

            return response

        response = tts_service.get_api_response()
        if response.status_code != 200:
            tts_service.current_endpoint = (tts_service.current_endpoint + 1) % 2
            if tts_service.get_api_response().status_code != 200:
                return jsonify({
                    "msg": "TTS service unavailable or rate limited",
                }), 503

        if len(text) < limit:
            audio = tts_service.generate_audio(text, voice)
            audio_base64_data = tts_service.extract_base64_data(audio)

            if audio_base64_data == "error":
                return jsonify({"msg": "This voice is unavailable"}), 400

            tts_service.save_audio_file(audio_base64_data, filename)
        else:
            text_parts = tts_service.split_string(text, limit)
            audio_base64_data = [""] * len(text_parts)

            def process_text_part(text_part, idx: int):
                audio = tts_service.generate_audio(text_part, voice)
                base64_data = tts_service.extract_base64_data(audio)
                if base64_data == "error":
                    return jsonify({"msg": "This voice is unavailable"}), 400

                audio_base64_data[idx] = base64_data

            threads = []
            for i, part in enumerate(text_parts):
                thread = threading.Thread(
                    target=process_text_part,
                    args=(i, part)
                )
                thread.start()
                threads.append(thread)

            for thread in threads:
                thread.join()

                audio_base64_data = "".join(audio_base64_data)
            tts_service.save_audio_file(audio_base64_data, filename)

        if not os.path.exists(filename):
            return jsonify({"msg": "Failed to generate audio file"}), 500

        response = send_file(
            filename,
            mimetype="audio/mp3",
            as_attachment=False,
        )

        return response

    except Exception as e:
        print(f"Error in generate_tts: {str(e)}")
        return jsonify({
            "msg": "An error occurred during TTS generation",
        }), 500
