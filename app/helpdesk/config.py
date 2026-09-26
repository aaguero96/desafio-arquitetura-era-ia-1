import os

GATEWAY_URL = os.environ["GATEWAY_URL"]
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]

# Capacidades lógicas do gateway; o modelo físico de cada uma fica em gateway/config.yaml.
CLASSIFICATION_MODEL = "ticket-classifier"
EXTRACTION_MODEL = "order-extractor"
SUGGESTION_MODEL = "reply-writer"
REPORT_MODEL = "topic-analyzer"

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = "/data/tickets.jsonl"
TICKETS_PER_CALL = 150
