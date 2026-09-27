# 0001. Aceitar só OpenAI e Anthropic, e só através do gateway da empresa

- Status: aceita
- Data: 2026-09-27
- Nível: corporativa

## Contexto

O helpdesk nasceu com cada feature escolhendo o provider que "funcionou melhor no teste" e guardando a chave dele na configuração da própria aplicação. O diagnóstico da v1 (README, dor 3) mostrou o custo disso: quando a Anthropic falhou, a sugestão de resposta e o relatório pararam, enquanto a classificação seguia; ninguém tinha decidido que o helpdesk dependeria de dois fornecedores, nem o que fazer quando um deles caísse. A pergunta aqui não é técnica: é com quais empresas a loja aceita mandar texto de cliente, e por onde.

## Opções consideradas

1. Deixar cada time escolher o provider por feature (situação da v1).
2. Padronizar um único provider para a empresa.
3. Homologar um conjunto pequeno de providers e exigir que todo tráfego passe por um ponto único da empresa.

## Decisão

Opção 3. Os providers homologados são OpenAI e Anthropic, os dois que já atendem o helpdesk. Nenhuma aplicação guarda chave de provider nem chama provider diretamente: todo acesso passa pelo AI Gateway da empresa (ADR 0003), que é o único dono das credenciais.

Um único provider (opção 2) foi descartado porque é exatamente o cenário da dor 3: com um só fornecedor, a instabilidade dele para o helpdesk inteiro. Dois providers homologados com modelos equivalentes (os `large` dão a mesma saída) são o que torna o fallback técnico possível (ADR 0005).

## Consequências

- Melhor: a lista de quem recebe dados de cliente é curta e decidida; a troca de um provider por outro homologado é configuração, não projeto.
- Pior: incluir um terceiro provider passa a exigir uma nova decisão neste nível, não só uma linha de código.
- Passa a ser necessário: manter contrato e credencial com os dois fornecedores, mesmo que um deles fique só como fallback.

## Evidência

- `grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY|sk-fake-openai|sk-ant-fake" app/` não retorna nada.
- `docker compose config` mostra as chaves dos providers só nos serviços `provider-fake` e `gateway`; o `app` recebe apenas `GATEWAY_URL` e `GATEWAY_API_KEY`.
