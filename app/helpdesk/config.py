import os

OPENAI_API_KEY = os.environ["FAKE_OPENAI_KEY"]
ANTHROPIC_API_KEY = os.environ["FAKE_ANTHROPIC_KEY"]

OPENAI_BASE_URL = "http://provider-fake:8090/openai/v1"
ANTHROPIC_BASE_URL = "http://provider-fake:8090/anthropic"

# A classificação e a extração rodam na OpenAI; a sugestão e o relatório, na Anthropic.
CLASSIFICATION_MODEL = "gpt-fake-large"
EXTRACTION_MODEL = "gpt-fake-large"
SUGGESTION_MODEL = "claude-fake-large"
REPORT_MODEL = "claude-fake-large"

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = "/data/tickets.jsonl"
TICKETS_PER_CALL = 150
