-- Migração 002: controle de envio do e-mail (só notícias novas desde o último e-mail).
-- Rode uma vez no Supabase: SQL Editor → New query → cole e "Run".
-- Pode rodar mais de uma vez sem problema.

alter table public.noticias add column if not exists enviada_em timestamptz;

create table if not exists public.envios (
    id            bigint generated always as identity primary key,
    enviado_em    timestamptz not null default now(),
    assunto       text,
    noticias      int,
    destinatarios text[]
);

alter table public.envios enable row level security;

create index if not exists noticias_enviada_em_idx on public.noticias (enviada_em);
