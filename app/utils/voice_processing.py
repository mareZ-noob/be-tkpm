import base64
import os
import threading
from typing import List
from uuid import uuid4

import requests
from moviepy.audio.AudioClip import concatenate_audioclips
from moviepy.editor import AudioFileClip

ENDPOINTS = [
    "https://tiktok-tts.weilnet.workers.dev/api/generation",
    "https://tiktoktts.com/api/tiktok-tts",
]
current_endpoint = 0
TEXT_BYTE_LIMIT = 100


def split_string(string: str, chunk_size: int) -> List[str]:
    if len(string) <= chunk_size:
        return [string]

    # Define priority split points (in order of preference)
    sentence_boundaries = ['. ', '! ', '? ', '; ', '。', '！', '？', '；', '\n']
    clause_boundaries = [', ', ': ', '、', '，', '：', '》', '」', '』', '〉']

    result = []
    remaining_text = string.strip()

    while len(remaining_text) > 0:
        if len(remaining_text) <= chunk_size:
            result.append(remaining_text)
            break

        # Try to find the best split point within the chunk_size limit
        chunk = remaining_text[:chunk_size]

        # First priority: try to split at sentence boundaries
        split_index = -1
        for boundary in sentence_boundaries:
            last_index = chunk.rfind(boundary)
            if last_index != -1:
                split_index = last_index + len(boundary) - 1
                break

        # Second priority: try to split at clause boundaries
        if split_index == -1:
            for boundary in clause_boundaries:
                last_index = chunk.rfind(boundary)
                if last_index != -1:
                    split_index = last_index + len(boundary) - 1
                    break

        # Third priority: if chunk is too small or no good boundary found,
        # try looking a bit further (up to 75% of chunk_size more)
        if split_index < chunk_size // 3 and len(remaining_text) > chunk_size:
            extended_search_size = min(len(remaining_text), int(chunk_size * 1.75))
            extended_chunk = remaining_text[:extended_search_size]

            # Try sentence boundaries in extended chunk
            for boundary in sentence_boundaries:
                next_index = chunk.find(boundary)
                if next_index != -1 and next_index < extended_search_size:
                    split_index = next_index + len(boundary) - 1
                    break

            # Try clause boundaries in extended chunk
            if split_index == -1:
                for boundary in clause_boundaries:
                    next_index = extended_chunk.find(boundary, chunk_size // 2)
                    if next_index != -1:
                        split_index = next_index + len(boundary) - 1
                        break

        # Last resort: split at a space near the chunk_size
        if split_index == -1 or split_index < chunk_size // 3:
            # Find the last space within the chunk size
            last_space = chunk.rfind(' ')
            if last_space != -1:
                split_index = last_space
            else:
                # If no space found, split at chunk_size
                split_index = chunk_size - 1

        # Add the chunk to our results and update the remaining text
        if split_index >= 0:
            result.append(remaining_text[:split_index + 1].strip())
            remaining_text = remaining_text[split_index + 1:].strip()
        else:
            # Fallback if no suitable split point found
            result.append(chunk.strip())
            remaining_text = remaining_text[chunk_size:].strip()

    # for i, r in enumerate(result):
    #     print(r)
    #     print('------------------------------')

    return result


def get_api_response() -> requests.Response:
    url = f'{ENDPOINTS[current_endpoint].split("/a")[0]}'
    response = requests.get(url)
    return response


def save_audio_file(base64_data: str, filename: str):
    audio_bytes = base64.b64decode(base64_data)
    with open(filename, "wb") as file:
        file.write(audio_bytes)


def generate_audio(text: str, voice: str) -> bytes:
    url = f"{ENDPOINTS[current_endpoint]}"
    headers = {"Content-Type": "application/json"}
    data = {"text": text, "voice": voice}
    response = requests.post(url, headers=headers, json=data)
    return response.content


def tts(text: str, voice: str = "none", filename: str = "output.mp3"):
    # checking if the website is available
    global current_endpoint

    if get_api_response().status_code == 200:
        print("[+] TikTok TTS Service available!", "green")
    else:
        current_endpoint = (current_endpoint + 1) % 2
        if get_api_response().status_code == 200:
            print("[+] TTS Service available!", "green")
        else:
            print("[-] TTS Service not available and probably temporarily rate limited, try again later...", "red")
            return

    # checking if arguments are valid
    if voice == "none":
        print("[-] Please specify a voice", "red")
        return

    if not text:
        print("[-] Please specify a text", "red")
        return

    # creating the audio file
    try:
        if len(text) < TEXT_BYTE_LIMIT:
            audio = generate_audio(text, voice)
            if current_endpoint == 0:
                audio_base64_data = str(audio).split('"')[5]
            else:
                audio_base64_data = str(audio).split('"')[3].split(",")[1]

            if audio_base64_data == "error":
                print("[-] This voice is unavailable right now", "red")
                return

        else:
            # Split longer text into smaller parts
            text_parts = split_string(text, TEXT_BYTE_LIMIT)
            audio_base64_data = [None] * len(text_parts)

            # Define a thread function to generate audio for each text part
            def generate_audio_thread(text_part, index):
                audio = generate_audio(text_part, voice)
                if current_endpoint == 0:
                    base64_data = str(audio).split('"')[5]
                else:
                    base64_data = str(audio).split('"')[3].split(",")[1]
                if audio_base64_data == "error":
                    print("[-] This voice is unavailable right now", "red")
                    return "error"

                audio_base64_data[index] = base64_data

            threads = []
            for index, text_part in enumerate(text_parts):
                # Create and start a new thread for each text part
                thread = threading.Thread(
                    target=generate_audio_thread, args=(text_part, index)
                )
                thread.start()
                threads.append(thread)

            # Wait for all threads to complete
            for thread in threads:
                thread.join()

            # Concatenate the base64 data in the correct order
            audio_base64_data = "".join(audio_base64_data)

        save_audio_file(audio_base64_data, filename)
        print(f"[+] Audio file saved successfully as '{filename}'", "green")

    except Exception as e:
        print(f"[-] An error occurred during TTS: {e}", "red")


# sentences = [
#     " Once upon a time, in a faraway land, there was a princess who lived in a castle.",
#     "The princess had a pet dragon that she loved to play with.",
#     "One day, the dragon flew away and the princess had to go on an adventure to find him.",
#     "She traveled through forests, mountains, and rivers until she finally found her dragon.",
#     "The princess and the dragon lived happily ever after in the castle.",
# ]

# sentences = [
#     "【運命の人】と出会い、愛し愛されて幸せになりたい…そう願う人はきっと多いはず。"
#     "しかし【運命の人】という言葉はよく聞きますが、具体的にどんな人のことを指すのか、ご存じでしょうか？"
#     "【運命の人】とは、いわゆる「見えない赤い糸で結ばれている人」や「巡り合えば生涯の伴侶になる人」のことを指します。"
#     "『会った瞬間にビビビッとくる』ともよく言われていますよね。"
#     "これは【運命の人】は生まれる前から宿命として定まっているため、本能が反応していると考えられています。"
#     "このように感覚的な話は耳にしても、実際には誰が自分の【運命の人】なのか、確信するのは難しいですよね。"
#     "もしかすると、すでにそばにいるのに気づいていないのかもしれません。"
#     "そこで今回は【運命の人】の特徴や見分け方、出会いのサインを具体的に紹介していきます。"
#     "【運命の人】を見逃さないよう、ぜひ参考にしてください。"
# ]

sentences = [
    "Sự kiện Y2K, hay còn gọi là Lỗi Thiên Niên Kỷ, là một vấn đề tiềm ẩn nghiêm trọng đối với các hệ thống máy tính trên toàn thế giới vào thời điểm chuyển giao từ năm 1999 sang năm 2000."
    "Vấn đề bắt nguồn từ việc các lập trình viên trước đây thường sử dụng hai chữ số để biểu diễn năm (ví dụ: '99' cho năm 1999) nhằm tiết kiệm bộ nhớ và giảm chi phí lưu trữ, vốn là một vấn đề lớn trong những thập kỷ đầu của kỷ nguyên máy tính. "
    "Khi năm 2000 đến gần, người ta lo ngại rằng các hệ thống này sẽ hiểu nhầm '00' là năm 1900, dẫn đến hàng loạt các lỗi hoạt động, ảnh hưởng nghiêm trọng đến mọi lĩnh vực từ tài chính, giao thông, năng lượng đến các dịch vụ công cộng. "
    "Nỗi lo sợ bao trùm là các hệ thống ngân hàng có thể sụp đổ, máy bay ngừng hoạt động, hoặc lưới điện bị tê liệt. Mặc dù đã có những nỗ lực khắc phục đáng kể và chi phí hàng tỷ đô la để nâng cấp và sửa chữa các hệ thống, tác động thực tế của Y2K sau khi năm 2000 đến lại tương đối hạn chế. "
    "Điều này chủ yếu là do sự chuẩn bị kỹ lưỡng trước đó, nhưng Y2K vẫn là một lời nhắc nhở về tầm quan trọng của việc dự đoán và giải quyết các vấn đề tiềm ẩn trong công nghệ thông tin, và là một ví dụ điển hình về một cuộc khủng hoảng kỹ thuật số được ngăn chặn thành công. "
    "Nỗi ám ảnh Y2K cũng đóng vai trò quan trọng trong việc thúc đẩy sự phát triển của các ngành công nghiệp công nghệ và củng cố nhận thức về an ninh mạng trong nhiều năm sau đó."
]
#
sentences = list(filter(lambda x: x != "", sentences))

voice = [
    "BV075_streaming",
]
#
paths = []
temp_audio_files = []
for v in voice:
    print("[+] Generating audio for voice:", v)
    current_tts_path = f"{uuid4()}.mp3"
    tts(sentences[0], v, filename=current_tts_path, play_sound=False)

    if not os.path.exists(current_tts_path):
        print(f"[-] Missing file: {current_tts_path}, skipping...")
        break

    audio_clip = AudioFileClip(current_tts_path)
    temp_audio_files.append(current_tts_path)
    paths.append(audio_clip)

final_audio = concatenate_audioclips(paths)
tts_path = "output.mp3"
final_audio.write_audiofile(tts_path)

for temp_audio_file in temp_audio_files:
    os.remove(temp_audio_file)

# playsound(tts_path)
