import base64
from typing import List

import requests

from app.utils.constant import ENDPOINTS


class TikTokTTS:
    def __init__(self):
        self.current_endpoint = 0

    def split_string(self, string: str, chunk_size: int) -> List[str]:
        if len(string) <= chunk_size:
            return [string]

        sentence_boundaries = ['. ', '! ', '? ', '; ', '。', '！', '？', '；', '\n']
        clause_boundaries = [', ', ': ', '、', '，', '：', '》', '」', '』', '〉']

        result = []
        remaining_text = string.strip()

        while len(remaining_text) > 0:
            if len(remaining_text) <= chunk_size:
                result.append(remaining_text)
                break

            chunk = remaining_text[:chunk_size]
            split_index = -1

            for boundary in sentence_boundaries:
                last_index = chunk.rfind(boundary)
                if last_index != -1:
                    split_index = last_index + len(boundary) - 1
                    break

            if split_index == -1:
                for boundary in clause_boundaries:
                    last_index = chunk.rfind(boundary)
                    if last_index != -1:
                        split_index = last_index + len(boundary) - 1
                        break

            if split_index < chunk_size // 3 and len(remaining_text) > chunk_size:
                extended_search_size = min(len(remaining_text), int(chunk_size * 1.75))
                extended_chunk = remaining_text[:extended_search_size]

                for boundary in sentence_boundaries:
                    next_index = chunk.find(boundary)
                    if next_index != -1 and next_index < extended_search_size:
                        split_index = next_index + len(boundary) - 1
                        break

                if split_index == -1:
                    for boundary in clause_boundaries:
                        next_index = extended_chunk.find(boundary, chunk_size // 2)
                        if next_index != -1:
                            split_index = next_index + len(boundary) - 1
                            break

            if split_index == -1 or split_index < chunk_size // 3:
                last_space = chunk.rfind(' ')
                if last_space != -1:
                    split_index = last_space
                else:
                    split_index = chunk_size - 1

            if split_index >= 0:
                result.append(remaining_text[:split_index + 1].strip())
                remaining_text = remaining_text[split_index + 1:].strip()
            else:
                result.append(chunk.strip())
                remaining_text = remaining_text[chunk_size:].strip()

        return result

    def get_api_response(self) -> requests.Response:
        url = f'{ENDPOINTS[self.current_endpoint].split("/a")[0]}'
        return requests.get(url)

    @staticmethod
    def save_audio_file(base64_data: str, filename: str):
        audio_bytes = base64.b64decode(base64_data)
        with open(filename, "wb") as file:
            file.write(audio_bytes)

    def generate_audio(self, text: str, voice: str) -> bytes:
        url = f"{ENDPOINTS[self.current_endpoint]}"
        headers = {"Content-Type": "application/json"}
        data = {"text": text, "voice": voice}
        response = requests.post(url, headers=headers, json=data)
        return response.content

    def extract_base64_data(self, audio_response: bytes) -> str:
        if self.current_endpoint == 0:
            return str(audio_response).split('"')[5]
        return str(audio_response).split('"')[3].split(",")[1]
