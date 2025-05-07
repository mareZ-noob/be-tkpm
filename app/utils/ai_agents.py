OPEN_ROUTER_MODELS = {
    "deepseek": [
        "deepseek/deepseek-chat-v3-0324:free",
        "deepseek/deepseek-r1:free",
        "deepseek/deepseek-r1-zero:free",
        "deepseek/deepseek-chat:free",
        "microsoft/mai-ds-r1:free",
        "deepseek/deepseek-v3-base:free",
        "deepseek/deepseek-r1-distill-qwen-32b:free",
        "deepseek/deepseek-r1-distill-qwen-14b:free",
        "deepseek/deepseek-r1-distill-llama-70b:free",
    ],
    "gemini": [
        "google/gemini-2.0-flash-exp:free",
        "google/gemini-2.5-pro-exp-03-25",
        "gemini/gemini-13b:free",
        "google/gemini-flash-1.5-8b-exp",
    ],
    "gemma": [
        "google/gemma-3-1b-it:free",
        "google/gemma-3-4b-it:free",
        "google/gemma-2-9b-it:free",
        "google/gemma-3-12b-it:free",
        "google/gemma-3-27b-it:free",
    ],
    "meta": [
        "meta-llama/llama-3.1-8b-instruct:free",
        "meta-llama/llama-3.1-405b:free",
        "meta-llama/llama-3.2-1b-instruct:free",
        "meta-llama/llama-3.2-3b-instruct:free",
        "meta-llama/llama-3.2-11b-vision-instruct:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "meta-llama/llama-4-scout:free",
        "meta-llama/llama-4-maverick:free",
    ],
    "microsoft": [
        "microsoft/mai-ds-r1:free",
    ],
    "mistral": [
        "mistralai/mistral-nemo:free",
        "mistralai/mistral-7b-instruct:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
    ],
    "nvidia": [
        "nvidia/llama-3.1-nemotron-nano-8b-v1:free",
        "nvidia/llama-3.3-nemotron-super-49b-v1:free",
        "nvidia/llama-3.1-nemotron-ultra-253b-v1:free",
    ],
    "qwen": [
        "qwen/qwen2.5-vl-3b-instruct:free",
        "qwen/qwen-2.5-7b-instruct:free",
        "qwen/qwen-2.5-vl-7b-instruct:free",
        "qwen/qwq-32b-preview:free",
        "qwen/qwq-32b:free",
        "qwen/qwen2.5-vl-32b-instruct:free",
        "qwen/qwen-2.5-coder-32b-instruct:free",
        "qwen/qwen-2.5-72b-instruct:free",
        "qwen/qwen2.5-vl-72b-instruct:free",
    ],
}

FLAT_OPEN_ROUTER_MODELS = [model for sublist in OPEN_ROUTER_MODELS.values() for model in sublist]

# (topic, word count, language, age range, audience description, style, tone)
WIKIPEDIA_PROMPT_TEXT = """
    I have the content: %s.
    
    Create engaging YouTube script content in paragraph format about this topic with approximately %s words.
    This content will be used for a YouTube video, so make it highly engaging and optimized for social media audience retention.
    
    Language:
        - %s
        
    Number of paragraphs:
        - Must less than 4 paragraphs!
    
    Audience:
        - Age range: %s
        - %s
    
    Style and tone:
        - %s
        - %s
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

# (prompt, word count, language, age range, audience description, style, tone)
PROMPT_TEXT = """
    The user has asked about: "%s"

    Create engaging YouTube script content in paragraph format about this topic with approximately %s words.
    This content will be used for a YouTube video, so make it highly engaging and optimized for social media audience retention.

    Language:
        - %s

    Number of paragraphs:
        - Must less than 4 paragraphs!

    Audience:
        - Age range: %s
        - %s

    Style and tone:
        - %s
        - %s
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

# (number of images, prompt, number of images)
PROMPT_IMAGE = """
    Analyze the following scientific text. Based on its content, key concepts, and narrative flow, generate a list of exactly %s distinct and visually descriptive prompts suitable for an image generation AI (like Stable Diffusion, Midjourney, or Pollinations). The prompts should cover different aspects mentioned in the text, from introduction to conclusion.
    
    Prioritize visual elements mentioned or implied in the text, such as key phenomena, objects, structures, processes, historical concepts/figures, or abstract ideas related to the scientific topic. Use styles like 'cinematic', 'hyperrealistic', 'abstract visualization', 'scientific illustration', 'dramatic lighting', 'microscopic view', 'astronomical illustration', 'conceptual art'.
    
    Format the output ONLY as a Python list of strings, like this:
    ['prompt 1 description', 'prompt 2 description', ..., 'prompt N description']
    
    Text:
    -------
    %s
    -------
    
    Generate the Python list of %s prompts now:
"""

# (text)
PROMPT_CORRECT_TEXT = """Correct spelling errors in the text below. Return *only* the corrected text and absolutely nothing else, not even quotation marks around the text unless they were in the original: %s.
Return only the corrected text, no explanations or additional information. If the text has period at the end of the sentence, please keep it. Otherwise, do not add period at the end of the sentence.
"""
