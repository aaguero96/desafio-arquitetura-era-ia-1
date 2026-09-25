import json

from anthropic import Anthropic
from openai import OpenAI

from . import config

openai_client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL)
anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY, base_url=config.ANTHROPIC_BASE_URL)


def call_openai(model: str, task: str, content: str) -> str:
    response = openai_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
    )
    return response.choices[0].message.content


def call_anthropic(model: str, task: str, content: str) -> str:
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=config.MAX_OUTPUT_TOKENS,
        messages=[{"role": "user", "content": f"TASK: {task}\n{content}"}],
    )
    return response.content[0].text


def parse_json(text: str) -> dict:
    return json.loads(text)
