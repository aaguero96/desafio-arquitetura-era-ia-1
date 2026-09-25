import json
from datetime import date, datetime

from . import config


def in_period(start: date, end: date) -> list[dict]:
    selected = []
    with open(config.TICKETS_FILE, encoding="utf-8") as file:
        for line in file:
            ticket = json.loads(line)
            day = datetime.fromisoformat(ticket["created_at"]).date()
            if start <= day <= end:
                selected.append(ticket)
    return selected
