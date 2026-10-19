"""Etapa 3: resume as notícias de cada tema com o Claude.

Uma chamada por tema (até `max_por_chamada` notícias por vez). O Claude devolve,
para cada notícia, um resumo curto em português e se ela é mesmo do tema.
Sem chave de API, ou se a chamada falhar, as notícias seguem com o trecho
original do RSS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .temas import ResultadoTema

SISTEMA = """Você resume notícias para um e-mail diário lido por um profissional de \
mercado de crédito (crédito corporativo e soberano, Brasil e principais economias).

Você recebe o nome de um tema e uma lista de notícias (título, fontes e, quando \
existe, um trecho do texto). Para cada notícia:

- resumo: 1 a 2 frases em português do Brasil, no máximo 280 caracteres. Diga o \
fato principal com os detalhes relevantes para crédito que estiverem no texto \
(quem, valor, instrumento, prazo, credores, rating, país). Use só a informação \
recebida: não invente números, datas nem desdobramentos. Se só houver o título, \
escreva uma frase clara a partir dele, sem acrescentar fatos. Notícias em inglês \
também são resumidas em português. Não comece com "A notícia" ou "O artigo".
- relevante: true se a notícia é de fato sobre o tema; false se a palavra-chave \
apareceu por acaso (sentido figurado, finanças pessoais, recomendação de ação, \
assunto sem relação com dívida de empresas ou governos).

Devolva um item para cada notícia recebida, com o mesmo id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "itens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "resumo": {"type": "string"},
                    "relevante": {"type": "boolean"},
                },
                "required": ["id", "resumo", "relevante"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["itens"],
    "additionalProperties": False,
}


@dataclass
class ConfigResumo:
    ativo: bool = True
    modelo: str = "claude-opus-5-5"
    esforco: str = "medium"
    remover_irrelevantes: bool = True
    max_por_chamada: int = 40


def carregar_config_resumo(caminho: str | Path = "temas.yaml") -> ConfigResumo:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    return ConfigResumo(**(dados.get("resumo") or {}))


def _entrada(tema: str, lote) -> str:
    noticias = []
    for i, m in enumerate(lote):
        n = m.noticia
        fontes = list(dict.fromkeys(n.fontes + [f for r in m.relacionadas for f in r.fontes]))
        trecho = n.resumo or next((r.resumo for r in m.relacionadas if r.resumo), "")
        noticias.append({"id": i, "titulo": n.titulo, "fontes": fontes, "trecho": trecho})
    return json.dumps({"tema": tema, "noticias": noticias}, ensure_ascii=False)


def resumir_temas(resultados: list[ResultadoTema], cfg: ConfigResumo, client=None) -> list[str]:
    """Preenche `resumo_ia` de cada notícia. Devolve avisos (vazio = tudo ok)."""
    if not cfg.ativo:
        return ["resumo com IA desligado (temas.yaml → resumo.ativo)"]

    import anthropic

    if client is None:
        try:
            client = anthropic.Anthropic()
        except anthropic.AnthropicError as e:
            return [f"resumo com IA não rodou: {e}"]

    avisos: list[str] = []
    for res in resultados:
        noticias = res.noticias
        for inicio in range(0, len(noticias), cfg.max_por_chamada):
            lote = noticias[inicio : inicio + cfg.max_por_chamada]
            try:
                resp = client.beta.messages.create(
                    model=cfg.modelo,
                    max_tokens=16000,
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    output_config={
                        "effort": cfg.esforco,
                        "format": {"type": "json_schema", "schema": SCHEMA},
                    },
                    system=SISTEMA,
                    messages=[{"role": "user", "content": _entrada(res.tema.nome, lote)}],
                )
            except (anthropic.AuthenticationError, TypeError):
                # TypeError: o SDK não achou nenhuma credencial configurada
                return avisos + ["resumo com IA não rodou: chave ANTHROPIC_API_KEY ausente ou inválida"]
            except anthropic.APIError as e:
                avisos.append(f"{res.tema.nome}: erro na API ({type(e).__name__}: {e})")
                continue

            if resp.stop_reason == "refusal":
                avisos.append(f"{res.tema.nome}: o modelo recusou o pedido")
                continue
            texto = next((b.text for b in resp.content if b.type == "text"), "")
            try:
                itens = json.loads(texto)["itens"]
            except (json.JSONDecodeError, KeyError, TypeError):
                avisos.append(f"{res.tema.nome}: resposta inválida (stop_reason={resp.stop_reason})")
                continue

            for item in itens:
                i = item.get("id")
                if isinstance(i, int) and 0 <= i < len(lote):
                    lote[i].resumo_ia = item.get("resumo", "").strip()
                    lote[i].relevante = bool(item.get("relevante", True))

        if cfg.remover_irrelevantes:
            fora = [m for m in res.noticias if not m.relevante]
            res.noticias = [m for m in res.noticias if m.relevante]
            res.excluidas += [(m.noticia, "IA: fora do tema") for m in fora]
    return avisos
