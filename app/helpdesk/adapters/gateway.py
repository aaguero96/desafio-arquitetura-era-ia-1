from collections.abc import Iterator

from openai import OpenAI, OpenAIError

from ..ports import GenerationInterrupted, LanguageModel, ModelUnavailable


class GatewayLanguageModel(LanguageModel):
    """Fala com o AI Gateway no formato OpenAI, usando a chave virtual da aplicação.

    Retry e fallback moram no gateway; aqui só há o timeout do chamador e a
    tradução dos erros do SDK para os erros da porta.
    """

    def __init__(self, base_url: str, api_key: str, max_output_tokens: int):
        # Retry é responsabilidade do gateway: aqui ele ficaria multiplicado.
        self._client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0)
        self._max_output_tokens = max_output_tokens

    def complete(self, capability: str, prompt: str, *, timeout: float) -> str:
        try:
            response = self._client.with_options(timeout=timeout).chat.completions.create(
                model=capability,
                max_tokens=self._max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except OpenAIError as error:
            raise ModelUnavailable(_reason(capability, error)) from error
        return response.choices[0].message.content

    def stream(self, capability: str, prompt: str, *, timeout: float) -> Iterator[str]:
        # timeout aqui é o tempo máximo sem receber dados, antes e durante o stream.
        started = False
        try:
            response = self._client.with_options(timeout=timeout).chat.completions.create(
                model=capability,
                max_tokens=self._max_output_tokens,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
            )
            for chunk in response:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    started = True
                    yield text
        except OpenAIError as error:
            if started:
                raise GenerationInterrupted(_reason(capability, error)) from error
            raise ModelUnavailable(_reason(capability, error)) from error


def _reason(capability: str, error: OpenAIError) -> str:
    """Motivo curto para quem consome: capacidade, tipo do erro e status HTTP do gateway."""
    status = getattr(error, "status_code", None)
    return f"{capability}: nenhum destino respondeu ({type(error).__name__}{f' {status}' if status else ''})"
