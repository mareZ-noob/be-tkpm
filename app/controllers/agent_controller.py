import re

import langdetect
import requests
import wikipedia
import wikipediaapi
from flask import jsonify, request
from flask_jwt_extended import jwt_required
from openai import OpenAI

from app.config.logging_config import setup_logging
from app.utils.ai_agents import FLAT_OPEN_ROUTER_MODELS, OPEN_ROUTER_MODELS, PROMPT_TEXT, WIKIPEDIA_PROMPT_TEXT
from app.utils.constant import OPEN_ROUTER_API_KEY
from app.utils.exceptions import (
    InternalServerException,
    MissingParameterException,
    ResourceNotFoundException,
    ServiceUnavailableException,
)

logger = setup_logging()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPEN_ROUTER_API_KEY,
)


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


def generate_youtube_content(text, is_wikipedia_query=True, output_language="English",
                             age_range="13-25", style="casual", word_count=1000,
                             tone="engaging", model=None):
    try:
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
            prompt = WIKIPEDIA_PROMPT_TEXT % (text, word_count, output_language, age_range, age_instructions,
                                              style_instructions, tone_instructions)
        else:
            prompt = PROMPT_TEXT % (text, word_count, output_language, age_range, age_instructions, style_instructions,
                                    tone_instructions)

        completion = client.chat.completions.create(
            extra_body={},
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
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
        else:
            logger.error("No choices returned. Full response:", completion)
            return None
    except Exception as e:
        logger.error(f"An error occurred while generating content: {e}", exc_info=True)
        return None


def process_user_input_sync(user_text, **kwargs):
    try:
        # Set default values for parameters
        output_language = kwargs.get("output_language", "English")
        age_range = kwargs.get("age_range", "13-25")
        style = kwargs.get("style", "casual")
        word_count = kwargs.get("word_count", 1000)
        tone = kwargs.get("tone", "engaging")
        model = kwargs.get("model")

        wiki_content = get_wikipedia_content(user_text)

        if wiki_content and not wiki_content.startswith("Article not found"):
            logger.info("Wikipedia content found. Generating YouTube script")
            result = generate_youtube_content(
                wiki_content,
                is_wikipedia_query=True,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone,
                model=model,
            )
            return result
        elif wiki_content and wiki_content.startswith("Article not found"):
            logger.info("Wikipedia article not found. Generating direct YouTube script")
            result = generate_youtube_content(
                user_text,
                is_wikipedia_query=False,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone,
                model=model,
            )
            return result
        else:
            logger.info("No Wikipedia content. Generating direct YouTube script")
            result = generate_youtube_content(
                user_text,
                is_wikipedia_query=False,
                output_language=output_language,
                age_range=age_range,
                style=style,
                word_count=word_count,
                tone=tone,
                model=model,
            )
            return result
    except Exception as e:
        logger.error(f"Error in processing: {e}", exc_info=True)
        return f"An error occurred while processing your request: {e}"


@jwt_required()
def get_provider():
    try:
        providers = list(OPEN_ROUTER_MODELS.keys())
        return jsonify(providers)
    except Exception as e:
        logger.error(f"Error in getting providers: {e}", exc_info=True)
        raise ServiceUnavailableException("Error in getting providers")


@jwt_required()
def get_all_models():
    return jsonify(OPEN_ROUTER_MODELS)


@jwt_required()
def get_models_by_provider(provider):
    provider_key = provider.lower()

    if provider_key in OPEN_ROUTER_MODELS:
        return jsonify(OPEN_ROUTER_MODELS[provider_key])
    else:
        logger.error(f"Provider '{provider_key}' not found.")
        raise ResourceNotFoundException(f"Provider '{provider_key}' not found.")


def generate_script(data):
    try:
        user_text = data.get("keyword")
        output_language = data.get("language")
        age_range = data.get("age")
        style = data.get("style")
        word_count = 1000
        tone = data.get("tone")
        model = data.get("model")

        if model not in FLAT_OPEN_ROUTER_MODELS:
            logger.error(f"Model '{model}' not found.")
            raise ResourceNotFoundException(f"Model '{model}' not found.")

        source_lang = detect_language(user_text)
        logger.info(f"Detected source language: {source_lang}")
        user_input_translated = translate_text(user_text, source_lang)

        # Process the user input and generate the YouTube script
        script = process_user_input_sync(
            user_input_translated,
            output_language=output_language,
            age_range=age_range,
            style=style,
            word_count=word_count,
            tone=tone,
            model=model,
        )
        return script
    except Exception as e:
        logger.error(f"Error in generating YouTube script: {e}", exc_info=True)
        raise ServiceUnavailableException(f"Error in generating YouTube script: {e}")


@jwt_required()
def get_script():
    try:
        data = request.get_json()

        required_fields = ['keyword', 'style', 'age', 'language', 'tone', 'model']
        missing_fields = [field for field in required_fields if not data.get(field)]

        if missing_fields:
            logger.error("Get script failed: Missing required fields")
            raise MissingParameterException("Missing required fields: keyword, style, age, language, tone, model")

        script = generate_script(data)
        logger.info(f"Generated script: {script}")
        return jsonify({"summary": script}), 200

    except Exception as e:
        logger.error(f"Error in generating YouTube script: {e}", exc_info=True)
        raise InternalServerException(f"Internal server error: {e}")
