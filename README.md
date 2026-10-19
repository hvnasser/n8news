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
- [x] **3. Resumo das notícias** com o Claude (1–2 frases em português por
      notícia) + filtro de países (G10 e principais emergentes).
- [ ] 4. Montar e enviar o e-mail
- [ ] 5. Agendar (GitHub Actions)

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

## Resumo com IA

Cada tema vai numa chamada ao Claude, que devolve um resumo de 1–2 frases em
português por notícia e marca as que não são do tema (que saem do e-mail).
Configuração no bloco `resumo:` do `temas.yaml`.

Precisa da chave da API da Anthropic:
- **Local:** `export ANTHROPIC_API_KEY=sk-ant-...`
- **GitHub Actions:** *Settings → Secrets and variables → Actions → New
  repository secret*, nome `ANTHROPIC_API_KEY`.

Sem a chave tudo funciona, só que com o trecho original do RSS no lugar do
resumo. `--sem-resumo` pula essa etapa.

## O que cada notícia tem

`titulo`, `link`, `resumo` (trecho do próprio RSS, até 400 caracteres),
`fonte`, `categoria`, `publicado_em`, `imagem`, e `fontes`/`categorias`
quando a mesma notícia aparece em mais de um jornal.

## Testes

```bash
pip install pytest && python -m pytest
```
