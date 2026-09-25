"""As quatro tarefas que o modelo simulado entende.

Toda saída é determinística para a mesma (tamanho do modelo, conteúdo).
"""

import hashlib
import json
import re
from collections import OrderedDict

TASKS = ("classify", "suggest", "topics", "extract")

PRODUCTS = [
    "fone de ouvido bluetooth", "smartwatch", "cafeteira elétrica", "liquidificador",
    "air fryer", "aspirador robô", "ventilador de mesa", "chaleira elétrica",
    "tênis de corrida", "mochila executiva", "jaqueta corta-vento", "calça jeans",
    "camiseta básica", "vestido midi", "bota de couro", "sandália rasteira",
    "notebook 14 polegadas", "mouse sem fio", "teclado mecânico", "monitor 24 polegadas",
    "webcam full hd", "carregador turbo", "power bank", "caixa de som portátil",
    "panela de pressão", "jogo de facas", "conjunto de potes", "tapete de yoga",
    "halter de 5 kg", "bicicleta ergométrica", "cadeira gamer", "luminária de mesa",
    "jogo de lençol", "travesseiro de espuma", "edredom casal", "cortina blackout",
    "perfume importado", "secador de cabelo", "prancha alisadora", "barbeador elétrico",
]

# A ordem importa: a primeira categoria cujas palavras aparecem no texto vence.
CATEGORIES = [
    ("payment", ["cobrança", "cobrado", "pagamento", "boleto", "pix", "cartão", "estorno", "fatura"]),
    ("exchange_return", ["trocar", "troca", "devolver", "devolução", "arrependi"]),
    ("product_defect", ["defeito", "quebrado", "não liga", "parou de funcionar", "danificado"]),
    ("delivery", ["entrega", "não chegou", "atrasad", "rastreio", "transportadora", "extraviado"]),
]

HIGH_PRIORITY = ["urgente", "cancelar", "procon", "cobrança duplicada", "cobrado duas vezes"]
LOW_PRIORITY = ["dúvida", "gostaria de saber", "informação"]

SUBTOPICS = {
    "delivery": [("extraviado", "Pedido extraviado"), ("rastreio", "Problema no rastreio"),
                 ("atrasad", "Atraso na entrega"), ("não chegou", "Atraso na entrega")],
    "payment": [("duplicada", "Cobrança duplicada"), ("duas vezes", "Cobrança duplicada"),
                ("pix", "Pix não reconhecido"), ("boleto", "Problema com boleto"),
                ("estorno", "Estorno pendente")],
    "exchange_return": [("arrependi", "Arrependimento de compra"), ("tamanho", "Troca por tamanho")],
    "product_defect": [("não liga", "Produto não liga"), ("quebrado", "Produto danificado"),
                       ("danificado", "Produto danificado")],
    "other": [("cupom", "Cupom de desconto"), ("senha", "Acesso à conta"),
              ("cadastro", "Acesso à conta")],
}
DEFAULT_SUBTOPIC = {
    "delivery": "Entrega: outros assuntos",
    "payment": "Pagamento: outros assuntos",
    "exchange_return": "Troca e devolução: outros assuntos",
    "product_defect": "Defeito de fabricação",
    "other": "Outros assuntos",
}

ORDER_RE = re.compile(r"pedido\s*(?:n[º°o]\.?\s*)?#?\s*(\d{6})(?!\d)", re.IGNORECASE)
SIX_DIGITS_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
TOPIC_LINE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.*)$")


def detect(user_text: str) -> tuple[str | None, str]:
    """Separa a linha `TASK: x` do conteúdo."""
    lines = user_text.strip().split("\n", 1)
    first = lines[0].strip()
    content = lines[1] if len(lines) > 1 else ""
    m = re.match(r"^TASK:\s*(\w+)\s*$", first, re.IGNORECASE)
    if m and m.group(1).lower() in TASKS:
        return m.group(1).lower(), content.strip()
    return None, user_text


def category_of(text: str) -> str:
    lower = text.lower()
    for category, words in CATEGORIES:
        if any(w in lower for w in words):
            return category
    return "other"


def priority_of(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in HIGH_PRIORITY):
        return "high"
    if any(w in lower for w in LOW_PRIORITY):
        return "low"
    return "medium"


def topic_of(text: str) -> str:
    category = category_of(text)
    lower = text.lower()
    for word, topic in SUBTOPICS[category]:
        if word in lower:
            return topic
    return DEFAULT_SUBTOPIC[category]


def classify(content: str, size: str) -> str:
    return json.dumps({"category": category_of(content), "priority": priority_of(content)},
                      ensure_ascii=False)


def extract(content: str, size: str) -> str:
    lower = content.lower()
    if size == "large":
        m = ORDER_RE.search(content)
        order_number = f"#{m.group(1)}" if m else None
        product = next((p for p in PRODUCTS if p in lower), None)
    else:
        # Qualidade inferior, de forma determinística: pega o primeiro número de
        # seis dígitos do texto (que pode ser a nota fiscal) e não identifica produto.
        m = SIX_DIGITS_RE.search(content)
        order_number = f"#{m.group(1)}" if m else None
        product = None
    return json.dumps({"order_number": order_number, "product": product}, ensure_ascii=False)


def topics(content: str, size: str) -> str:
    groups: "OrderedDict[str, list[str]]" = OrderedDict()
    for line in content.splitlines():
        m = TOPIC_LINE_RE.match(line)
        if not m:
            continue
        ticket_id, text = m.group(1).strip(), m.group(2)
        groups.setdefault(topic_of(text), []).append(ticket_id)
    items = [{"topic": topic, "count": len(ids), "examples": ids[:3]} for topic, ids in groups.items()]
    items.sort(key=lambda t: (-t["count"], t["topic"]))
    return json.dumps({"topics": items}, ensure_ascii=False)


OPENINGS = {
    "delivery": "Olá! Sinto muito pelo transtorno com a entrega do seu pedido.",
    "payment": "Olá! Entendo a sua preocupação com o pagamento e vou te ajudar a resolver.",
    "exchange_return": "Olá! Claro, vamos cuidar da sua troca ou devolução.",
    "product_defect": "Olá! Lamento muito que o produto tenha apresentado problema.",
    "other": "Olá! Obrigado por entrar em contato com a nossa loja.",
}

STEPS = {
    "delivery": [
        "Já abri uma solicitação de verificação junto à transportadora responsável pelo envio.",
        "O prazo de retorno da transportadora costuma ser de até dois dias úteis.",
        "Assim que tivermos a posição atualizada, você recebe um aviso por e-mail.",
        "Caso o pedido seja considerado extraviado, fazemos o reenvio sem nenhum custo adicional.",
        "Se preferir, também é possível solicitar o cancelamento com reembolso integral.",
    ],
    "payment": [
        "Verifiquei o registro da transação e encaminhei o caso para a equipe financeira.",
        "Cobranças em duplicidade são estornadas automaticamente em até duas faturas.",
        "Pagamentos via pix podem levar alguns minutos para serem reconhecidos pelo sistema.",
        "Se o valor não for regularizado no prazo, basta responder este atendimento.",
        "Guarde o comprovante, ele pode ser solicitado durante a análise.",
    ],
    "exchange_return": [
        "A solicitação pode ser feita em até sete dias corridos após o recebimento.",
        "Vou gerar uma etiqueta de postagem gratuita para você enviar o produto.",
        "O produto deve estar sem sinais de uso e, se possível, na embalagem original.",
        "Assim que o item chegar ao nosso centro, a troca ou o reembolso é processado.",
        "Você pode acompanhar cada etapa pela área Meus Pedidos no site.",
    ],
    "product_defect": [
        "Para agilizar, peço que envie uma foto ou um vídeo curto mostrando o problema.",
        "Com as imagens, a análise técnica é concluída em até três dias úteis.",
        "Confirmado o defeito, você escolhe entre a troca por um novo ou o reembolso.",
        "A coleta do produto é agendada por nossa conta, sem custo para você.",
        "Enquanto isso, evite novas tentativas de uso para não agravar o problema.",
    ],
    "other": [
        "Registrei a sua solicitação e ela já está com a equipe responsável.",
        "Você recebe um retorno por e-mail em até dois dias úteis.",
        "Se precisar complementar alguma informação, basta responder este atendimento.",
        "Nossa central também atende pelo chat, de segunda a sábado.",
        "Agradecemos a paciência e a confiança na nossa loja.",
    ],
}

CLOSING = "Fico à disposição para qualquer outra dúvida. Um abraço, equipe de atendimento."

TARGET_CHARS = {"large": 2400, "mini": 1000}


def suggest(content: str, size: str) -> str:
    category = category_of(content)
    steps = STEPS[category]
    seed = int(hashlib.sha256(f"{size}:{content}".encode()).hexdigest(), 16)
    first = seed % len(steps)
    order = steps[first:] + steps[:first]

    paragraphs = [OPENINGS[category]]
    target = TARGET_CHARS[size]
    i = 0
    while sum(len(p) + 2 for p in paragraphs) + len(CLOSING) < target:
        step = order[i % len(order)]
        if i // len(order) == 0:
            paragraphs.append(step)
        else:
            paragraphs.append(f"Reforçando o ponto {i % len(order) + 1}: {step[0].lower()}{step[1:]}")
        i += 1
    paragraphs.append(CLOSING)
    return "\n\n".join(paragraphs)


def fallback_text(content: str, size: str) -> str:
    return (
        "Tarefa não reconhecida. A primeira linha da mensagem do usuário deve ser "
        "TASK: classify, suggest, topics ou extract."
    )


GENERATORS = {
    "classify": classify,
    "suggest": suggest,
    "topics": topics,
    "extract": extract,
    None: fallback_text,
}


def generate(task: str | None, content: str, size: str) -> str:
    return GENERATORS[task](content, size)
