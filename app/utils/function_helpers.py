import datetime
import math
import os
import re
import subprocess
import tempfile
from uuid import uuid4

import langdetect
import requests
import whisper
import wikipedia
import wikipediaapi
from openai import OpenAI
from pydub import AudioSegment

from app.config.logging_config import setup_logging
from app.utils.ai_agents import PROMPT_CORRECT_TEXT
from app.utils.constant import FFMPEG_PATH, FPS, OPEN_ROUTER_API_KEY, TARGET_HEIGHT, TARGET_WIDTH, VIDEO_FORMAT
from app.utils.whisper_support_language import whisper_support_language

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
)

logger = setup_logging()


def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions


def standardize_text(text):
    text = text.replace("*", " ")
    text = text.replace("#", " ")
    text = re.sub(r"\[.*\]", "", text)
    text = re.sub(r"\(.*\)", "", text)
    return text


def detect_language(text):
    try:
        return langdetect.detect(text)
    except Exception as e:
        logger.error(f"Language detection error: {e}", exc_info=True)
        return 'en'


def translate_text(text, source_lang=None):
    try:
        # Use the Google Translate API
        url = "https://translate.googleapis.com/translate_a/single"

        params = {
            "client": "gtx",
            "sl": source_lang if source_lang else "auto",
            "tl": "en",
            "dt": "t",
            "q": text
        }

        response = requests.get(url, params=params)
        if response.status_code == 200:
            result = response.json()
            translated_text = ''.join([sentence[0] for sentence in result[0] if sentence[0]])
            return translated_text
        else:
            logger.error(f"Translation request failed with status code {response.status_code}")
            return text
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        return text


def get_wikipedia_content(keyword):
    wiki_en = wikipediaapi.Wikipedia(
        user_agent="MyWikipediaCrawler/1.0 (contact@example.com)",
        language="en"
    )

    page = wiki_en.page(keyword)

    if not page.exists():
        try:
            suggestions = wikipedia.search(keyword, results=5)
            if suggestions:
                return "Article not found.\n Did you mean:\n- " + "\n- ".join(suggestions)
            else:
                return None
        except Exception as e:
            logger.error(f"Wikipedia search error: {e}", exc_info=True)
            return None
    else:
        return page.text


def correct_text(text, model):
    prompt = PROMPT_CORRECT_TEXT % text

    completion = client.chat.completions.create(
        extra_body={},
        model=model,
        messages=[
            {"role": "system", "content": "You are a master of language."},
            {
                "role": "user",
                "content": prompt,
            },
        ],
    )

    if completion and hasattr(completion, 'choices') and completion.choices:
        msg = completion.choices[0].message.content
        msg = standardize_text(msg)
        return msg

    return text


def format_srt_timestamp(seconds):
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = delta.microseconds // 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def convert_audio_to_text(file_path, language, model_name):
    temp_wav_file = None
    srt_file_path = None
    segments_json = None

    try:
        if not os.path.exists(file_path):
            logger.error(f"Input audio file not found: {file_path}")
            return None
        if not model_name:
            logger.error("Model name is required for audio transcription.")
            return None
        if language not in whisper_support_language:
            logger.warning(f"Language '{language}' might not be optimally supported by Whisper.")

        # model = whisper.load_model("turbo")
        model = whisper.load_model("base")

        logger.info(f"Loading audio file: {file_path}")
        audio = AudioSegment.from_file(file_path)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav_file = temp_wav.name
            logger.info(f"Exporting audio to temporary WAV file: {temp_wav_file}")
            audio.export(temp_wav_file, format="wav")

        logger.info(f"Starting transcription for language: {language}")
        result = model.transcribe(temp_wav_file, language=language, verbose=True)
        logger.info("Transcription complete.")

        if not result or "segments" not in result or not result["segments"]:
            logger.warning("Whisper transcription returned no segments.")
            return None

        srt_content = []
        segments_json = []
        for i, segment in enumerate(result["segments"]):
            text = segment["text"].strip()
            if not text:
                continue

            # corrected_text_segment = correct_text(text, model_name).strip()
            corrected_text_segment = text

            start_time_sec = segment["start"]
            end_time_sec = segment["end"]

            segments_json.append({
                "start": math.floor(start_time_sec),
                "end": math.floor(end_time_sec),
                "text": corrected_text_segment
            })

            # Format for SRT file
            start_time_srt = format_srt_timestamp(start_time_sec)
            end_time_srt = format_srt_timestamp(end_time_sec)

            srt_content.append(f"{i + 1}")
            srt_content.append(f"{start_time_srt} --> {end_time_srt}")
            srt_content.append(corrected_text_segment)
            srt_content.append("")

        if not srt_content:
            logger.warning("No valid text segments found after processing.")
            return None, None

        srt_file_path = os.path.join(os.getcwd(), f"srt_{uuid4()}.srt")

        logger.info(f"Saving SRT file to: {srt_file_path}")
        with open(srt_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_content))

        return srt_file_path, segments_json
    except FileNotFoundError as fnf:
        logger.error(f"File not found error: {fnf}", exc_info=True)
        return None, None
    except Exception as e:
        logger.error(f"An unexpected error occurred during audio processing: {e}", exc_info=True)
        return None, None

    finally:
        if temp_wav_file and os.path.exists(temp_wav_file):
            try:
                os.remove(temp_wav_file)
                logger.info(f"Removed temporary WAV file: {temp_wav_file}")
            except OSError as oe:
                logger.error(f"Error removing temporary WAV file {temp_wav_file}: {oe}")


def run_ffmpeg_command(command_list):
    try:
        logger.info(f"Executing FFmpeg command: {' '.join(map(str, command_list))}")
        process = subprocess.run(command_list, check=True, capture_output=True, text=True, encoding='utf-8',
                                 errors='replace')
        if process.stderr and "Error" not in process.stderr and "failed" not in process.stderr.lower():
            logger.error("FFmpeg Info/Warnings (stderr):\n", process.stderr[-1000:])
        elif process.stderr:
            logger.error("FFmpeg Error (stderr):\n", process.stderr)

        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error executing FFmpeg command: {' '.join(map(str, command_list))}")
        logger.error("FFmpeg STDERR:", e.stderr)
        logger.error("FFmpeg STDOUT:", e.stdout)
        return False
    except FileNotFoundError:
        logger.error("Error: ffmpeg executable not found. Please ensure FFmpeg is installed and in your PATH.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred while running FFmpeg: {e}", exc_info=True)
        return False


def download_file(url, local_filename):
    logger.info(f"Downloading {url} to {local_filename}...")
    try:
        os.makedirs(os.path.dirname(local_filename), exist_ok=True)
        with requests.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Downloaded {local_filename} successfully.")
        return local_filename
    except requests.exceptions.Timeout:
        logger.error(f"Error downloading {url}: Timeout")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading {url}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred during download of {url}: {e}", exc_info=True)
        return None


def create_video(data_dict):
    # Keep track of all created files for cleanup
    temp_files = []

    logger.info("Downloading Media")
    downloaded_files = {}
    main_audio_url = data_dict.get("audioUrl")
    if main_audio_url:
        main_audio_filename_ext = main_audio_url.split('.')[-1].split('?')[0] if '.' in main_audio_url else "mp3"
        main_audio_filename = os.path.join(os.getcwd(), f"main_audio_{uuid4()}.{main_audio_filename_ext}")
        temp_files.append(main_audio_filename)  # Add to cleanup list

        if not download_file(main_audio_url, main_audio_filename):
            logger.error(
                "Failed to download main audio. Video will be created without main audio if possible, or abort if critical.")
            downloaded_files["main_audio"] = None
        else:
            downloaded_files["main_audio"] = main_audio_filename
    else:
        logger.error("No main audioUrl provided.")
        downloaded_files["main_audio"] = None

    processed_segment_files = []

    logger.info("Processing Clips")
    sorted_clips = sorted(data_dict["clips"], key=lambda c: c["startTime"])

    vf_common_options = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={FPS},format={VIDEO_FORMAT}"
    )

    for i, clip in enumerate(sorted_clips):
        clip_id = clip["id"]
        clip_type = clip["type"]
        source_url = clip["sourceUrl"]
        duration = clip["duration"]

        original_filename_ext = "tmp"
        if '.' in source_url.split('/')[-1]:
            original_filename_ext = source_url.split('.')[-1].split('?')[0]

        local_clip_path = os.path.join(os.getcwd(), f"clip_{i}_{clip_id}_{uuid4()}.{original_filename_ext}")
        temp_files.append(local_clip_path)  # Add to cleanup list

        output_segment_path = os.path.join(os.getcwd(), f"segment_{i}_{clip_id}_{uuid4()}.mp4")
        temp_files.append(output_segment_path)  # Add to cleanup list

        if not download_file(source_url, local_clip_path):
            logger.error(f"Failed to download clip {clip_id} ({source_url}). Skipping.")
            continue

        ffmpeg_cmd_segment = [FFMPEG_PATH]

        if clip_type == "image":
            logger.info(f"Processing image: {clip_id}")
            ffmpeg_cmd_segment.extend([
                "-loop", "1",  # Loop input image
                "-i", local_clip_path,
                "-t", str(duration),
                "-vf", vf_common_options,
                "-an",  # No audio for image segments
                "-y",  # Overwrite output file if it exists
                output_segment_path
            ])
        elif clip_type == "video":
            logger.info(f"Processing video: {clip_id}")
            ffmpeg_cmd_segment.extend([
                "-i", local_clip_path,
                "-t", str(duration),  # Trim/extend video to its specified duration
                "-vf", vf_common_options,
                "-c:v", "libx264",  # Re-encode for compatibility and uniform parameters
                "-preset", "medium",  # A balance between speed and quality
                "-an",  # Remove existing audio from segment
                "-y",  # Overwrite output file if it exists
                output_segment_path
            ])
        else:
            logger.warning(f"Unsupported clip type: {clip_type} for clip {clip_id}. Skipping.")
            continue

        if not run_ffmpeg_command(ffmpeg_cmd_segment):
            logger.error(f"Failed to process {clip_type} {clip_id}. Skipping.")
            continue

        # Add to processed segments only if ffmpeg was successful
        processed_segment_files.append(output_segment_path)

        # Original clip can be removed immediately after processing
        try:
            if os.path.exists(local_clip_path):
                os.remove(local_clip_path)
                temp_files.remove(local_clip_path)  # Remove from cleanup list once deleted
                logger.debug(f"Removed temporary file: {local_clip_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {local_clip_path}: {e}")

    if not processed_segment_files:
        logger.error("No video segments were processed successfully. Aborting.")
        # Clean up any files created before failure
        cleanup_temp_files(temp_files)
        return None

    # Concatenate Video Segments using the concat filter
    logger.info("Concatenating Video Segments")
    intermediate_video_no_audio = os.path.join(os.getcwd(), f"intermediate_no_audio_{uuid4()}.mp4")
    temp_files.append(intermediate_video_no_audio)  # Add to cleanup list

    if len(processed_segment_files) == 1:
        logger.info("Only one segment processed, copying it directly.")
        try:
            if os.path.exists(intermediate_video_no_audio):
                os.remove(intermediate_video_no_audio)
            os.rename(processed_segment_files[0], intermediate_video_no_audio)
        except OSError:
            import shutil
            shutil.copyfile(processed_segment_files[0], intermediate_video_no_audio)
        logger.info(f"Copied {processed_segment_files[0]} to {intermediate_video_no_audio}")

        # Remove the original processed segment since we've renamed/copied it
        try:
            if os.path.exists(processed_segment_files[0]) and processed_segment_files[0] != intermediate_video_no_audio:
                os.remove(processed_segment_files[0])
                temp_files.remove(processed_segment_files[0])  # Remove from cleanup list
                logger.debug(f"Removed temporary file: {processed_segment_files[0]}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {processed_segment_files[0]}: {e}")

    else:
        inputs_for_concat_filter = []
        filter_complex_str_parts = []
        for i, segment_path in enumerate(processed_segment_files):
            inputs_for_concat_filter.extend(["-i", segment_path])
            filter_complex_str_parts.append(
                f"[{i}:v:0]")  # Assumes video stream is the first stream (0) in each segment

        filter_complex_str = "".join(filter_complex_str_parts) + \
                             f"concat=n={len(processed_segment_files)}:v=1:a=0[v]"
        # v=1 means 1 video stream output, a=0 means 0 audio stream output

        concat_command = [FFMPEG_PATH] + \
                         inputs_for_concat_filter + \
                         ["-filter_complex", filter_complex_str,
                          "-map", "[v]",  # Map the output of concat filter
                          "-c:v", "libx264",  # Re-encode during concat for maximum stability
                          "-preset", "medium",
                          "-pix_fmt", VIDEO_FORMAT,
                          "-r", str(FPS),  # Ensure consistent frame rate
                          "-y",  # Overwrite output
                          intermediate_video_no_audio]

        if not run_ffmpeg_command(concat_command):
            logger.error("Failed to concatenate video segments. Aborting.")
            # Clean up any files created before failure
            cleanup_temp_files(temp_files)
            return None

        # Clean up segment files after concatenation
        for segment_path in processed_segment_files:
            try:
                if os.path.exists(segment_path):
                    os.remove(segment_path)
                    temp_files.remove(segment_path)  # Remove from cleanup list
                    logger.debug(f"Removed temporary file: {segment_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {segment_path}: {e}")

    # Add main audio and set final duration
    logger.info("Adding Audio and Finalizing Video")
    total_duration_spec = data_dict.get("totalDuration")

    # Check if intermediate video was created
    if not os.path.exists(intermediate_video_no_audio):
        logger.error(f"Intermediate video {intermediate_video_no_audio} not found. Aborting finalization.")
        # Clean up any files created before failure
        cleanup_temp_files(temp_files)
        return None

    final_command = [
        FFMPEG_PATH,
        "-i", intermediate_video_no_audio
    ]

    audio_mapping_done = False
    if downloaded_files.get("main_audio") and os.path.exists(downloaded_files["main_audio"]):
        final_command.extend(["-i", downloaded_files["main_audio"]])
        final_command.extend(["-c:v", "copy"])  # Video is already processed
        final_command.extend(["-c:a", "aac"])  # Re-encode audio to AAC
        final_command.extend(["-map", "0:v:0"])  # Map video from first input (intermediate_video_no_audio)
        final_command.extend(["-map", "1:a:0"])  # Map audio from second input (main_audio_filename)
        final_command.extend(["-shortest"])  # End when the shorter of video/audio ends
        audio_mapping_done = True
    else:  # No main audio, or main audio download failed
        final_command.extend(["-c:v", "copy"])  # Copy video stream
        if not audio_mapping_done:  # Ensure video is mapped if no audio added
            final_command.extend(["-map", "0:v:0"])
        final_command.extend(["-an"])  # Explicitly no audio if none was provided/added

    if total_duration_spec is not None:
        final_command.extend(["-t", str(total_duration_spec)])  # Trim/extend to total_duration_spec

    output_filename = f"output_video_{uuid4()}.mp4"

    final_command.extend(["-y", output_filename])

    success = run_ffmpeg_command(final_command)

    cleanup_temp_files(temp_files)

    if not success:
        logger.info("Failed to add audio and finalize video. Check logs.")
        return None
    else:
        logger.info(f"Successfully created video: {output_filename}")
        return output_filename


def cleanup_temp_files(file_list):
    logger.info(f"Cleaning up {len(file_list)} temporary files")
    for file_path in file_list:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Removed temporary file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to remove temporary file {file_path}: {e}")
