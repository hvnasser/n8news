# N8News — notícias por e-mail

Script em Python que busca notícias nos feeds RSS dos principais jornais do
Brasil e do mundo e (nas próximas etapas) envia um e-mail organizado por temas,
com link + resumo e filtros por tema (ex: escolher quais ações acompanhar).

## Etapas

- [x] **1. Busca de notícias**: lê os feeds, limpa o texto, descarta notícias
      antigas e junta notícias repetidas entre jornais.
- [x] **2. Temas e filtros**: `temas.yaml` separa as notícias por tema.
      Primeiro tema: **Crédito** (spreads corporativos e soberanos, ratings,
      default, RJ/RE e renegociação de dívida).
- [x] **3. Resumo das notícias** com IA via OpenRouter (modelo escolhido por
      tarefa) + filtro de países (G10 e principais emergentes).
- [x] **Banco de dados (Supabase)**: guarda cada notícia com data, texto,
      resumo, link e tema, para consultar depois.
- [x] **4. E-mail pelo Gmail**: notícias do dia por tema e filtro, com link,
      fonte, horário (Brasília) e resumo.
- [x] **5. Agendado** todo dia às 06:50 (Brasília) pelo GitHub Actions
      (vale depois que o código estiver no branch principal).

## Rodar

```bash
pip install -r requirements.txt
python -m n8news                     # notícias separadas por tema + status dos feeds
python -m n8news --todas             # todas as notícias, sem filtro de tema
python -m n8news --horas 6           # só as últimas 6 horas
python -m n8news --json noticias.json
python -m n8news --quieto            # só o status dos feeds
```

O GitHub Action **Buscar notícias** roda a busca a cada push (ou manualmente
em *Actions → Buscar notícias → Run workflow*) e salva o `noticias.json` como
artefato.

## Adicionar ou remover jornais

Edite `feeds.yaml`:

```yaml
- { fonte: TechCrunch, categoria: tecnologia, url: "https://techcrunch.com/feed/" }
```

Use `ativo: false` para desligar um feed sem apagar. Para jornais sem RSS
funcionando (caso do WSJ), dá para usar a busca do Google News como feed:
`https://news.google.com/rss/search?q=site:wsj.com+when:1d&hl=en-US&gl=US&ceid=US:en`.
Em `ignorar_links_com` ficam trechos de link a descartar (ex: `/patrocinado/`). O final da saída mostra o
**status de cada feed** (`OK`, `VAZIO` ou `ERRO`), útil para achar URLs que
pararam de funcionar.

## Temas e filtros

Edite `temas.yaml`. Cada tema tem filtros (ex: no tema Crédito: "Spreads
corporativos", "Default e calote", "Recuperação judicial"...). Uma notícia
entra no tema se passar em pelo menos um filtro.

```yaml
- nome: Recuperação judicial e extrajudicial
  ativo: true            # false desliga o filtro
  palavras:              # basta uma aparecer no título ou resumo
    - recuperação judicial
    - Chapter 11
  exige: []              # opcional: além disso, uma destas tem que aparecer
```

- **Adicionar/remover** um assunto: inclua ou apague linhas em `palavras`.
- `*` aceita qualquer final (`renegoci*` pega renegociação, renegociar...).
- Acentos, maiúsculas e hífens não importam.
- `excluir` (no tema) tira notícias com aquelas palavras (ex: Serasa).
- A saída mostra, em cada notícia, qual filtro e palavra a fizeram entrar,
  para facilitar ajustes.
- Notícias sobre o mesmo fato em vários jornais viram uma só, com
  "também em: ..." listando as outras fontes.

As buscas do Google News (categoria `credito` no `feeds.yaml`) só aceitam
notícias dos jornais em `google_news_fontes_permitidas`. Se quiser receber
de um site que está ficando de fora, adicione o nome dele nessa lista.

## Países

`paises.yaml` lista os países em grupos (`g10`, `em`, `outros`). No tema,
`paises_permitidos: [g10, em]` faz sair a notícia que cita **só** países de
fora (ex: Gana, Sri Lanka). Notícia que não cita país nenhum continua. Para
aceitar um país específico, adicione o código (ex: `[g10, em, VEN]`) ou mude
o grupo dele no `paises.yaml`.

## IA: relevância e resumo

Duas tarefas, cada uma com o modelo que você escolher (bloco `ia:` do
`temas.yaml`):

| Tarefa | O que faz | Padrão |
|---|---|---|
| `relevancia` | confirma se a notícia é mesmo do tema; as que não forem saem do e-mail | `anthropic/claude-haiku-5.5` (barato) |
| `resumo` | 1–2 frases em português por notícia | `anthropic/claude-opus-5.5` |

- Notícia **só com título** (sem texto nem trecho, comum no Google News) não
  passa pela IA de resumo: o resumo é o próprio título.
- **Opinião** (colunas, editoriais, análises assinadas) continua no e-mail,
  com o resumo começando por "Opinião — Fulano:". Quem marca é a tarefa de
  relevância.
- `--refazer-resumos` gera de novo os resumos de notícias já gravadas.

O acesso é pelo **OpenRouter** (um só cadastro para Claude, GPT, Gemini,
DeepSeek...). Para trocar o modelo, mude `modelo:` com o nome que aparece em
https://openrouter.ai/models. Um tema pode usar outro modelo só para ele
(`ia:` dentro do tema). Para ir direto na Anthropic, use `provedor: anthropic`
e nomes como `claude-opus-5-5`.

Chave:
- **GitHub Actions:** secret `OPENROUTER_API_KEY` (crie em
  https://openrouter.ai/settings/keys).
- **Local:** `export OPENROUTER_API_KEY=sk-or-...`

Sem a chave tudo funciona, só que com o trecho original do RSS no lugar do
resumo. `--sem-resumo` pula essa etapa; `--sem-texto` não baixa as matérias;
`--sem-banco` não lê nem grava no Supabase.

## E-mail (Gmail)

O e-mail sai pelo Gmail usando uma **senha de app** (não é a sua senha normal):

1. Ative a verificação em duas etapas na conta Google (obrigatório para
   senha de app): https://myaccount.google.com/signinoptions/twosv
2. Crie a senha de app em https://myaccount.google.com/apppasswords (nome:
   `n8news`). O Google mostra 16 letras; copie.
3. No GitHub, crie os secrets:
   - `GMAIL_USER`: seu endereço Gmail (remetente)
   - `GMAIL_APP_PASSWORD`: a senha de app (com ou sem espaços)
   - `EMAIL_PARA` (opcional): destinatários separados por vírgula; sem ele,
     o e-mail vai para o próprio `GMAIL_USER`.

O e-mail é enviado no horário agendado (06:50) ou ao rodar manualmente em
*Actions → Buscar notícias → Run workflow*; não a cada mudança no código.
Localmente: `python -m n8news --enviar-email` (ou `--salvar-email email.html`
para só gerar o arquivo e conferir).

## Banco de dados (Supabase)

Cada execução grava as notícias dos temas em duas tabelas:

- `noticias`: título, link, data de publicação, jornal(is), outros links da
  mesma notícia, países, trecho do RSS, **texto da matéria**, **resumo da IA**,
  data da coleta.
- `noticias_temas`: em qual tema cada notícia entrou e por qual filtro.

Notícia já gravada não é resumida de novo (economiza a API).

O texto da matéria é extraído da própria página. Em sites com paywall (Valor,
FT, WSJ) vem só o começo; links do Google News ficam só com o trecho do RSS.

**Configurar (uma vez):**
1. Crie um projeto em supabase.com.
2. *SQL Editor → New query*: cole o conteúdo de `supabase/schema.sql` e clique
   em *Run*.
3. *Project Settings → API*: copie a **Project URL** e a chave **secret**
   (ou `service_role`). Nunca use a chave pública/anon aqui.
4. No GitHub, crie os secrets `SUPABASE_URL` e `SUPABASE_KEY` (mesmo lugar do
   `ANTHROPIC_API_KEY`).

**Consultar:** no *Table Editor* do Supabase, ou no *SQL Editor*:

```sql
-- últimas notícias de crédito
select publicado_em, titulo, resumo_ia, link from noticias_por_tema
where tema = 'credito' limit 50;

-- busca por palavra (acentos e plural não importam)
select publicado_em, titulo, resumo_ia, link from noticias
where busca @@ websearch_to_tsquery('portuguese', 'Ri Happy')
order by publicado_em desc;
```

## O que cada notícia tem

`titulo`, `link`, `resumo` (trecho do próprio RSS, até 400 caracteres),
`fonte`, `categoria`, `publicado_em`, `imagem`, e `fontes`/`categorias`
quando a mesma notícia aparece em mais de um jornal.

## Testes

```bash
pip install pytest && python -m pytest
```
