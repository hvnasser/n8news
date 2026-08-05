# N8News — Resumo diário de notícias por e-mail (n8n)

Workflow para n8n que busca notícias em feeds RSS de grandes jornais do Brasil
e do mundo, organiza por **temas** e envia um e-mail diário com link + resumo
de cada notícia. Cada tema pode ter um **filtro configurável** para incluir ou
excluir notícias por palavra-chave (ex: acompanhar só as ações que você
escolher no tema "Ações e Mercado").

## Como funciona

`workflows/rss-news-email.json` contém o workflow completo:

1. **Schedule Trigger** — dispara todo dia às 7h (`0 7 * * *`, ajuste como quiser).
2. **Config** — lista de feeds RSS + temas + filtros. É o único node que você
   normalmente precisa editar.
3. **RSS Feed Read** — busca cada feed listado no Config.
4. **Classify & Filter** — junta cada notícia ao tema do feed de origem e
   aplica o filtro do tema (include/exclude por palavra-chave).
5. **Dedup & Recency** — evita repetir notícias já enviadas em execuções
   anteriores (usa a memória estática do workflow) e ignora notícias fora da
   janela de tempo (30h por padrão).
6. **Group & Build Email** — agrupa por tema e monta o HTML do e-mail.
7. **Has News?** — só envia e-mail se houver alguma notícia nova.
8. **Send Email** — envia via SMTP.

## Importar no n8n

1. No n8n, vá em **Workflows → Import from File** e selecione
   `workflows/rss-news-email.json`.
2. Abra o node **Send Email** e configure uma credencial SMTP (ou troque pelo
   node **Gmail** se preferir usar OAuth2 com sua conta Google).
   - Ajuste o campo `fromEmail` para o e-mail remetente.
   - O campo `toEmail` já está preenchido com `nasser.hvictor@gmail.com`.
3. Ative o workflow (toggle "Active").

## Temas incluídos por padrão

- 🇧🇷 Brasil (G1, Folha, Estadão)
- 🌍 Mundo (BBC, The Guardian, NYT)
- 💰 Economia (Folha Mercado, G1 Economia)
- 💻 Tecnologia (G1 Tecnologia, The Verge)
- 📈 Ações e Mercado (InfoMoney, Folha Mercado) — **filtrado** por lista de
  empresas/tickers de interesse (Petrobras, Vale, Itaú, etc.)

> As URLs de RSS podem mudar com o tempo — se algum feed parar de retornar
> notícias, verifique se a URL ainda é válida no site do veículo.

## Como adicionar/remover notícias filtradas de um tema

Abra o node **Config** e edite o objeto `topicsMeta`. Exemplo do tema Ações:

```js
acoes: {
  label: '📈 Acoes e Mercado',
  filter: {
    mode: 'include', // só passam notícias que mencionem uma das keywords
    keywords: [
      'Petrobras', 'PETR4',
      'Vale', 'VALE3',
      // adicione aqui a empresa/ticker que te interessa
    ]
  }
}
```

- **Adicionar** uma ação/empresa: acrescente o nome ou ticker no array `keywords`.
- **Remover**: apague o item correspondente do array.
- Isso funciona para qualquer tema, não só Ações. Por exemplo, para excluir
  notícias de celebridades do tema Brasil:

```js
brasil: {
  label: '🇧🇷 Brasil',
  filter: { mode: 'exclude', keywords: ['BBB', 'novela', 'reality show'] }
}
```

## Adicionar ou remover feeds RSS

No mesmo node **Config**, edite o array `feeds`:

```js
{ topic: 'tecnologia', source: 'TechCrunch', url: 'https://techcrunch.com/feed/' }
```

Cada feed precisa apontar para um `topic` que exista em `topicsMeta`.

## Ajustar horário de envio

No node **Schedule Trigger**, altere a expressão cron (`0 7 * * *` = todo dia
às 7h). Ex: `0 8,19 * * *` para enviar às 8h e às 19h.

## Resumo das notícias

Por padrão o "resumo" usado é a descrição/trecho já fornecido pelo próprio
RSS (limpo de HTML e truncado). Se quiser resumos gerados por IA (mais
curtos e consistentes), dá para adicionar um node de LLM (ex: Anthropic/
OpenAI) entre **Classify & Filter** e **Dedup & Recency**, chamando o modelo
por notícia para reescrever `summary` em 1–2 frases.
