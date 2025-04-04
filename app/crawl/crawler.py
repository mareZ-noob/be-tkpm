import urllib.parse

import google.generativeai as genai
import wikipedia
import wikipediaapi
from googletrans import Translator

genai.configure(api_key="AIzaSyASeaYG6TS-aq64c-DCXD0_Aqg9D6sUU4o")


def translate_to_english(text):
    translator = Translator()
    translated_text = translator.translate(text, src="vi", dest="en")
    return translated_text.text


def get_wikipedia_content(url):
    # Trích xuất tiêu đề bài viết từ URL và giải mã nếu cần
    title = url.split("/")[-1]
    title = urllib.parse.unquote(title).replace("_", " ")  # Giải mã URL

    # Dịch tiêu đề sang tiếng Anh nếu cần
    translated_title = translate_to_english(title)
    print(f"🔄 Translated '{title}' ➝ '{translated_title}'")

    # Khởi tạo API Wikipedia (tiếng Anh)
    wiki = wikipediaapi.Wikipedia(user_agent="MyWikipediaCrawler/1.0 (contact@example.com)", language="en")

    # Lấy nội dung bài viết
    page = wiki.page(translated_title)

    if not page.exists():
        # Nếu bài viết không tồn tại, tìm kiếm các bài liên quan
        try:
            suggestions = wikipedia.search(translated_title, results=5)
        except wikipedia.exceptions.WikipediaException:
            suggestions = []

        if suggestions:
            return "Article not found.\n Did you mean:\n- " + "\n- ".join(suggestions)
        else:
            return "Article not found and no suggestions available."

    return page.text


def summarize_text(text):
    model = genai.GenerativeModel("gemini-1.5-pro-latest")
    response = model.generate_content(f"Tóm tắt nội dung sau thành đoạn văn 300 từ:\n{text}")
    return response.text


def get_wikipedia_summary(keyword):
    url = "https://vi.wikipedia.org/wiki/" + urllib.parse.quote(keyword)  # Encode URL chính xác
    content = get_wikipedia_content(url)
    result = summarize_text(content)
    return result
