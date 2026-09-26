from openai import OpenAI

from ..ports import LanguageModel


class GatewayLanguageModel(LanguageModel):
    """Fala com o AI Gateway no formato OpenAI, usando a chave virtual da aplicação."""

    def __init__(self, base_url: str, api_key: str, max_output_tokens: int):
        # Retry é responsabilidade do gateway: aqui ele ficaria multiplicado.
        self._client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
        self._max_output_tokens = max_output_tokens

    def complete(self, capability: str, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
