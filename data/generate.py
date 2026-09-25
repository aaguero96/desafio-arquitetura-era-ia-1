"""Gera data/tickets.jsonl de forma determinística (seed fixa).

Uso: python3 data/generate.py
O arquivo gerado é o que vale; este script existe para rastreabilidade.
"""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
TOTAL_TICKETS = 5000
TIMEZONE = timezone(timedelta(hours=-3))

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

# Cada categoria tem subtemas; cada subtema tem frases-núcleo com as palavras-chave
# que o provider-fake usa para classificar e agrupar.
TEMPLATES = {
    "delivery": {
        "delay": [
            "Meu {ped} ainda não chegou e o prazo de entrega já passou.",
            "A entrega do {ped} está atrasada há vários dias.",
            "Comprei {prod_art} e a entrega está atrasada, o {ped} continua parado.",
        ],
        "lost": [
            "A transportadora informou que o {ped} foi extraviado.",
            "O rastreio diz que o {ped} foi extraviado no centro de distribuição.",
        ],
        "tracking": [
            "O código de rastreio do {ped} não mostra nenhuma atualização.",
            "Não consigo acompanhar o rastreio da entrega de {prod_art}.",
        ],
    },
    "payment": {
        "duplicate_charge": [
            "Fui cobrado duas vezes no cartão pelo {ped}, é uma cobrança duplicada.",
            "Apareceu cobrança duplicada na fatura referente a {prod_art}.",
        ],
        "pix": [
            "Paguei o {ped} via pix e o pagamento não foi reconhecido.",
            "Fiz o pix de {prod_art} e o pagamento consta como pendente.",
        ],
        "bank_slip": [
            "O boleto do {ped} venceu e não consigo gerar outro para pagamento.",
            "Paguei o boleto de {prod_art} e o pagamento não foi confirmado.",
        ],
        "refund": [
            "Estou esperando o estorno do {ped} no cartão há semanas.",
            "O estorno do pagamento de {prod_art} ainda não caiu.",
        ],
    },
    "exchange_return": {
        "regret": [
            "Quero devolver {prod_art} por arrependimento, o {ped} chegou ontem.",
            "Me arrependi da compra e quero fazer a devolução do {ped}.",
        ],
        "size": [
            "Quero trocar {prod_art} por outro tamanho, o {ped} veio pequeno.",
            "Preciso fazer a troca do {ped} porque o tamanho não serviu.",
        ],
    },
    "product_defect": {
        "wont_turn_on": [
            "Recebi {prod_art} e o aparelho não liga, {ped}.",
            "O produto do {ped} não liga de jeito nenhum.",
        ],
        "damaged": [
            "{prod_Art} veio quebrado na caixa, {ped}.",
            "O produto do {ped} chegou danificado e com a embalagem aberta.",
        ],
        "general": [
            "{prod_Art} parou de funcionar depois de dois dias de uso, {ped}.",
            "O item do {ped} veio com defeito de fabricação.",
        ],
    },
    "other": {
        "coupon": [
            "O cupom de desconto não foi aplicado na minha compra.",
            "Recebi um cupom por e-mail e o site diz que ele é inválido.",
        ],
        "account": [
            "Não consigo acessar minha conta, a senha não funciona.",
            "Quero atualizar o cadastro com meu novo endereço de e-mail.",
        ],
        "general": [
            "Vocês têm loja física na minha cidade?",
            "Queria elogiar o atendimento que recebi semana passada.",
        ],
    },
}

CATEGORY_WEIGHTS = {
    "delivery": 30, "payment": 22, "exchange_return": 18, "product_defect": 18, "other": 12,
}

HIGH_PRIORITY_PHRASES = [
    "É urgente.",
    "Se não resolverem hoje vou cancelar a compra.",
    "Vou abrir uma reclamação no Procon.",
]
LOW_PRIORITY_PHRASES = [
    "É só uma dúvida.",
    "Gostaria de saber como funciona o processo.",
]
NEUTRAL_PHRASES = [
    "Aguardo retorno.",
    "Obrigado desde já.",
    "Sou cliente da loja há bastante tempo.",
    "Já tentei resolver pelo chat, sem sucesso.",
    "Fico no aguardo de uma solução.",
    "Podem me ajudar, por favor?",
    "Moro em Campinas, caso ajude.",
    "Prefiro contato por e-mail.",
]



def with_article(product: str, capitalize: bool = False) -> str:
    feminine = ("cafeteira", "chaleira", "mochila", "jaqueta", "calça", "camiseta",
                "bota", "sandália", "webcam", "caixa", "panela", "bicicleta", "cadeira",
                "luminária", "cortina", "prancha", "air fryer")
    article = "a" if product.startswith(feminine) else "o"
    if capitalize:
        article = article.upper()
    return f"{article} {product}"


def random_number(rng: random.Random) -> str:
    return f"{rng.randint(100000, 999999)}"


def order_reference(rng: random.Random, number: str) -> str:
    return rng.choice([f"pedido #{number}", f"pedido {number}", f"pedido nº {number}"])


def generate_text(rng: random.Random, category: str) -> str:
    subtopic = rng.choice(list(TEMPLATES[category]))
    core = rng.choice(TEMPLATES[category][subtopic])

    product = rng.choice(PRODUCTS)
    mentions_order = rng.random() < 0.6
    mentions_product = rng.random() < 0.5

    parts = []
    if mentions_order:
        number = random_number(rng)
        ped = order_reference(rng, number)
        if rng.random() < 0.25:
            # Dois números no mesmo texto: torna a extração não trivial.
            parts.append(f"Tenho aqui a nota fiscal {random_number(rng)}.")
    else:
        ped = "pedido"

    prod_art = with_article(product) if mentions_product else "o produto"
    prod_Art = with_article(product, capitalize=True) if mentions_product else "O produto"

    if "{ped}" not in core and mentions_order:
        core = core + f" Referente ao {ped}."
    parts.append(core.format(ped=ped, prod_art=prod_art, prod_Art=prod_Art))

    draw = rng.random()
    if draw < 0.15:
        parts.append(rng.choice(HIGH_PRIORITY_PHRASES))
    elif draw < 0.30:
        parts.append(rng.choice(LOW_PRIORITY_PHRASES))

    neutral = NEUTRAL_PHRASES[:]
    rng.shuffle(neutral)
    text = " ".join(parts)
    while len(text) < 150 and neutral:
        text = f"{text} {neutral.pop()}"
    if len(text) > 300:
        text = text[:300].rsplit(" ", 1)[0].rstrip(",") + "."
    return text


def main() -> None:
    rng = random.Random(SEED)
    start = datetime(2026, 8, 1, 0, 0, tzinfo=TIMEZONE)
    seconds_in_month = 31 * 24 * 3600

    # Garante pelo menos um ticket por dia e distribui o resto ao acaso.
    instants = [start + timedelta(days=d, seconds=rng.randint(8 * 3600, 20 * 3600)) for d in range(31)]
    instants += [start + timedelta(seconds=rng.randint(0, seconds_in_month - 1)) for _ in range(TOTAL_TICKETS - 31)]
    instants.sort()

    categories = list(CATEGORY_WEIGHTS)
    weights = list(CATEGORY_WEIGHTS.values())

    target = Path(__file__).with_name("tickets.jsonl")
    with target.open("w", encoding="utf-8") as out:
        for i, instant in enumerate(instants, start=1):
            category = rng.choices(categories, weights=weights)[0]
            ticket = {
                "id": f"TK-{i:05d}",
                "created_at": instant.isoformat(),
                "customer_id": f"CL-{rng.randint(10000, 99999)}",
                "text": generate_text(rng, category),
            }
            out.write(json.dumps(ticket, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
