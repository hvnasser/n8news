-- N8News: tabelas para guardar as notícias e os resumos.
-- Rode uma vez no Supabase: Dashboard → SQL Editor → New query → cole e "Run".

-- Uma linha por notícia (a mesma notícia em vários jornais vira uma linha só,
-- com os outros links em `outros_links`).
create table if not exists public.noticias (
    id            text primary key,          -- hash do link normalizado
    titulo        text not null,
    link          text not null,
    fonte         text,                      -- jornal principal
    fontes        text[] not null default '{}',
    outros_links  jsonb not null default '[]',  -- [{"fonte": ..., "link": ..., "titulo": ...}]
    categorias    text[] not null default '{}',
    paises        text[] not null default '{}',
    publicado_em  timestamptz,               -- data da notícia (do jornal)
    trecho_rss    text,                      -- trecho que veio no RSS
    texto         text,                      -- texto extraído da página (parcial em sites com paywall)
    resumo_ia     text,                      -- resumo gerado pelo Claude
    imagem        text,
    enviada_em    timestamptz,               -- quando foi enviada por e-mail (vazio = ainda não)
    coletado_em   timestamptz not null default now(),  -- primeira vez que o robô viu a notícia
    atualizado_em timestamptz not null default now(),
    busca         tsvector generated always as (
        to_tsvector('portuguese',
            coalesce(titulo, '') || ' ' || coalesce(resumo_ia, '') || ' ' || coalesce(texto, ''))
    ) stored
);

-- Em quais temas cada notícia entrou e por qual filtro.
create table if not exists public.noticias_temas (
    noticia_id  text not null references public.noticias(id) on delete cascade,
    tema        text not null,               -- id do tema (ex: credito)
    filtros     text[] not null default '{}',
    palavras    text[] not null default '{}',
    criado_em   timestamptz not null default now(),
    primary key (noticia_id, tema)
);

-- Cada e-mail enviado (o próximo e-mail só traz notícias publicadas depois deste).
create table if not exists public.envios (
    id            bigint generated always as identity primary key,
    enviado_em    timestamptz not null default now(),
    assunto       text,
    noticias      int,
    destinatarios text[]
);

create index if not exists noticias_enviada_em_idx on public.noticias (enviada_em);
create index if not exists noticias_publicado_em_idx on public.noticias (publicado_em desc);
create index if not exists noticias_busca_idx on public.noticias using gin (busca);
create index if not exists noticias_paises_idx on public.noticias using gin (paises);
create index if not exists noticias_temas_tema_idx on public.noticias_temas (tema, criado_em desc);

-- Segurança: com RLS ligado e sem políticas, só a chave secreta (service role)
-- usada pelo robô consegue ler e gravar. A chave pública não vê nada.
alter table public.noticias enable row level security;
alter table public.noticias_temas enable row level security;
alter table public.envios enable row level security;

-- Visão prática para consultar: notícia + tema, mais recentes primeiro.
create or replace view public.noticias_por_tema
with (security_invoker = true) as
select t.tema, t.filtros, n.publicado_em, n.titulo, n.resumo_ia, n.link,
       n.fontes, n.paises, n.texto, n.id
from public.noticias_temas t
join public.noticias n on n.id = t.noticia_id
order by n.publicado_em desc nulls last;

-- Exemplos de consulta (SQL Editor):
--   Últimas notícias de crédito:
--     select publicado_em, titulo, resumo_ia, link from noticias_por_tema
--     where tema = 'credito' limit 50;
--   Busca por palavra (ex: Ri Happy):
--     select publicado_em, titulo, resumo_ia, link from noticias
--     where busca @@ websearch_to_tsquery('portuguese', 'Ri Happy')
--     order by publicado_em desc;
