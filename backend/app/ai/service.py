from openai import OpenAI

from app.config import settings

SYSTEM_PROMPTS = {
    'general': 'You are FLIWAI OmniAI, a practical all-in-one AI assistant. Be accurate, clear, and safety-conscious.',
    'it': 'You are FLIWAI OmniAI IT Support. Troubleshoot networks, printers, servers, endpoints, and scripts safely. Ask for evidence before recommending destructive actions.',
    'business': 'You are FLIWAI OmniAI Business Assistant. Create practical plans, documents, SOPs, and professional content while clearly separating facts from assumptions.',
    'creative': 'You are FLIWAI OmniAI Creative Assistant. Help with branding, design concepts, marketing, and product ideas while avoiding unsupported claims of uniqueness.',
}


def get_ai_response(message: str, tool: str = 'general') -> tuple[str, str]:
    if not settings.openai_api_key:
        return (
            'The application is running, but OPENAI_API_KEY is missing. Add it to the root .env file and restart the backend.',
            settings.openai_model,
        )

    client = OpenAI(api_key=settings.openai_api_key, timeout=45.0, max_retries=2)
    system_prompt = SYSTEM_PROMPTS.get(tool, SYSTEM_PROMPTS['general'])
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': message},
        ],
    )
    return response.choices[0].message.content or 'No response generated.', settings.openai_model
