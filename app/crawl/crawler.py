import wikipedia
import urllib.parse
import google.generativeai as genai
from googletrans import Translator
import langdetect
import requests
import wikipedia
import wikipediaapi

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
            return f"Article not found.\n Did you mean:\n- " + "\n- ".join(suggestions)
        else:
            return "Article not found and no suggestions available."

    return page.text  # Trả về nội dung bài viết nếu tìm thấy

def summarize_text(text):
    model = genai.GenerativeModel("gemini-1.5-pro-latest")
    response = model.generate_content(f"Tóm tắt nội dung sau thành đoạn văn 300 từ:\n{text}")
    return response.text


def get_wikipedia_summary(keyword):
    url = "https://vi.wikipedia.org/wiki/" + urllib.parse.quote(keyword)  # Encode URL chính xác
    content = get_wikipedia_content(url)
    result = summarize_text(content)
    return result

def translate_text_sync(text, source_lang=None):
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
            print(f"Translation request failed with status code {response.status_code}")
            return text
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def detect_language_sync(text):
    try:
        return langdetect.detect(text)
    except Exception as e:
        print(f"Language detection error: {e}")
        return 'en'


def get_wikipedia_content_sync(keyword):
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
            print(f"Wikipedia search error: {e}")
            return None
    else:
        return page.text


def generate_youtube_content(text, is_wikipedia_query=True, output_language="English",
                             age_range="13-25", style="casual", word_count=1000,
                             tone="engaging"):
    try:
        model = genai.GenerativeModel("gemini-1.5-pro-latest")

        if style.lower() == "casual":
            style_instructions = "Write in a casual, conversational style that's relatable to YouTube viewers."
        elif style.lower() == "educational":
            style_instructions = "Write in an educational style that explains concepts clearly for a YouTube audience."
        elif style.lower() == "storytelling":
            style_instructions = "Write in an engaging, narrative style that hooks YouTube viewers."
        elif style.lower() == "enthusiastic":
            style_instructions = "Write with high energy and enthusiasm to engage YouTube viewers."
        else:
            style_instructions = f"Write in a {style} style that feels natural and engaging for YouTube viewers."

        if tone.lower() == "engaging":
            tone_instructions = "Use an engaging tone that keeps viewers interested throughout."
        elif tone.lower() == "informative":
            tone_instructions = "Use an informative tone while maintaining viewer interest."
        elif tone.lower() == "enthusiastic":
            tone_instructions = "Use an enthusiastic, energetic tone that's perfect for YouTube."
        elif tone.lower() == "friendly":
            tone_instructions = "Use a friendly, approachable tone that builds connection with viewers."
        else:
            tone_instructions = f"Use a {tone} tone that resonates with viewers and keeps them hooked."

        if age_range.lower() == "5-12":
            age_instructions = "Use simple language and basic explanations suitable for younger YouTube viewers."
        elif age_range.lower() == "13-17":
            age_instructions = "Use moderately complex language suitable for teenage YouTube viewers."
        elif age_range.lower() == "18-25":
            age_instructions = "Use language suitable for young adult YouTube viewers with some background knowledge."
        elif age_range.lower() == "26+":
            age_instructions = "Use language suitable for adult YouTube viewers with general knowledge."
        else:
            age_instructions = f"Use language tailored to a {age_range} age range, making it accessible and engaging."

        if is_wikipedia_query:
            prompt = f"""
                I have the content: {text}.

                Create engaging YouTube script content in paragraph format about this topic with approximately {word_count} words. 
                This content will be used for a YouTube video, so make it highly engaging and optimized for social media audience retention.

                Language:
                    - {output_language}

                Audience:
                    - Age range: {age_range}
                    - {age_instructions}

                Style and tone:
                    - {style_instructions}
                    - {tone_instructions}
                    - Start with a friendly, masterpiece greeting like a famous YouTuber to hook viewers right away
                    - Write in clearly defined paragraphs with natural transitions
                    - Make the content highly shareable for social media
                    - Use a conversational, YouTuber-style voice throughout
                    - Include a strong call-to-action toward the end

                Content structure:
                    - Begin with an attention-grabbing introduction featuring the friendly, masterpiece greeting
                    - Develop the main points in well-structured paragraphs
                    - Use natural language transitions between paragraphs
                    - End with a conclusion that summarizes key points
                    - Add a call-to-action for engagement (like, subscribe, comment)

                Rules:
                    - Only use paragraph format (no bullet points or numbered lists)
                    - Not use Markdown formatting
                    - Not use HTML formatting
                    - Not use special characters, symbols, or emojis
                    - Never use a title or headings
                    - Only return the script content ready for voiceover
                    - Optimize for YouTube audience retention
            """
        else:
            prompt = f"""
                The user has asked about: "{text}"

                Create engaging YouTube script content in paragraph format about this topic with approximately {word_count} words.
                This content will be used for a YouTube video, so make it highly engaging and optimized for social media audience retention.

                Language:
                    - {output_language}

                Audience:
                    - Age range: {age_range}
                    - {age_instructions}

                Style and tone:
                    - {style_instructions}
                    - {tone_instructions}
                    - Start with a friendly, masterpiece greeting like a famous YouTuber to hook viewers right away
                    - Write in clearly defined paragraphs with natural transitions
                    - Make the content highly shareable for social media
                    - Use a conversational, YouTuber-style voice throughout
                    - Include a strong call-to-action toward the end

                Content structure:
                    - Begin with an attention-grabbing introduction featuring the friendly, masterpiece greeting
                    - Develop the main points in well-structured paragraphs
                    - Use natural language transitions between paragraphs
                    - End with a conclusion that summarizes key points
                    - Add a call-to-action for engagement (like, subscribe, comment)

                Rules:
                    - Only use paragraph format (no bullet points or numbered lists)
                    - Not use Markdown formatting
                    - Not use HTML formatting
                    - Not use special characters, symbols, or emojis
                    - Never use a title or headings
                    - Only return the script content ready for voiceover
                    - Optimize for YouTube audience retention
            """

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI response error: {e}")
        return f"Error generating YouTube content: {e}"


def process_user_input_sync(user_text, **kwargs):
    """
    Process user input with parameters optimized for YouTube content

    Parameters:
    - user_text: User input text (already translated to English)
    - output_language: Target language for output (already translated to English)
    - age_range: Target audience age range (already translated to English)
    - style: Writing style (already translated to English)
    - word_count: Approximate word count for output
    - tone: Tone of writing (already translated to English)
    """
    try:
        # Set default values for parameters
        output_language = kwargs.get("output_language", "English")
        age_range = kwargs.get("age_range", "13-25")
        style = kwargs.get("style", "casual")
        word_count = kwargs.get("word_count", 1000)
        tone = kwargs.get("tone", "engaging")

        # Step 1: Detect language (already handled before this function)
        # Step 2: Translate to English (already handled before this function)

        # Step 3: Try to find Wikipedia article
        wiki_content = get_wikipedia_content_sync(user_text)

        # Step 4: Generate YouTube-optimized content
        if wiki_content and not wiki_content.startswith("Article not found"):
            print("📚 Wikipedia content found. Generating YouTube script...")
            result = generate_youtube_content(
                wiki_content,
                is_wikipedia_query=True,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone
            )
            return result
        elif wiki_content and wiki_content.startswith("Article not found"):
            print("❌ Wikipedia article not found. Generating direct YouTube script...")
            result = generate_youtube_content(
                user_text,
                is_wikipedia_query=False,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone
            )
            return result
        else:
            print("🤖 No Wikipedia content. Generating direct YouTube script...")
            result = generate_youtube_content(
                user_text,
                is_wikipedia_query=False,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone
            )
            return result
    except Exception as e:
        print(f"Error in processing: {e}")
        return f"An error occurred while processing your request: {e}"


if __name__ == "__main__":
    # Example usage with user input, translating all inputs to English
    user_input = input("Enter a topic or question in any language: ")
    source_lang = detect_language_sync(user_input)
    if source_lang != 'en':
        user_input_translated = translate_text_sync(user_input, source_lang)
        print(f"🔄 Topic translated: '{user_input}' → '{user_input_translated}'")
    else:
        user_input_translated = user_input
        print(f"✓ Topic already in English: '{user_input_translated}'")

    output_language = input("Enter the output language (default is 'English'): ") or "English"
    source_lang = detect_language_sync(output_language)
    if source_lang != 'en':
        output_language_translated = translate_text_sync(output_language, source_lang)
        print(f"🔄 Output language translated: '{output_language}' → '{output_language_translated}'")
    else:
        output_language_translated = output_language
        print(f"✓ Output language already in English: '{output_language_translated}'")

    age_range = input("Enter the target age range (e.g., '5-12', '13-25', or custom like 'teens'): ") or "13-25"
    source_lang = detect_language_sync(age_range)
    if source_lang != 'en':
        age_range_translated = translate_text_sync(age_range, source_lang)
        print(f"🔄 Age range translated: '{age_range}' → '{age_range_translated}'")
    else:
        age_range_translated = age_range
        print(f"✓ Age range already in English: '{age_range_translated}'")

    style = input("Enter the writing style (e.g., 'casual', 'educational', or custom like 'dramatic'): ") or "casual"
    source_lang = detect_language_sync(style)
    if source_lang != 'en':
        style_translated = translate_text_sync(style, source_lang)
        print(f"🔄 Style translated: '{style}' → '{style_translated}'")
    else:
        style_translated = style
        print(f"✓ Style already in English: '{style_translated}'")

    word_count_input = input("Enter the approximate word count (default is 1000): ") or "1000"
    try:
        word_count = int(word_count_input)
    except ValueError:
        print(f"Invalid word count input '{word_count_input}', using default 1000")
        word_count = 1000

    tone = input("Enter the tone (e.g., 'engaging', 'friendly', or custom like 'chill'): ") or "engaging"
    source_lang = detect_language_sync(tone)
    if source_lang != 'en':
        tone_translated = translate_text_sync(tone, source_lang)
        print(f"🔄 Tone translated: '{tone}' → '{tone_translated}'")
    else:
        tone_translated = tone
        print(f"✓ Tone already in English: '{tone_translated}'")

    parameters = {
        "output_language": output_language_translated,
        "age_range": age_range_translated,
        "style": style_translated,
        "word_count": word_count,
        "tone": tone_translated
    }

    youtube_script = process_user_input_sync(user_input_translated, **parameters)
    print("\nYOUTUBE SCRIPT:\n")
    print(youtube_script)
