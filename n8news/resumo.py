"""Etapa 3: IA sobre as notícias de cada tema, em duas tarefas.

1. relevancia: confirma se a notícia é mesmo do tema (a palavra-chave pode ter
   aparecido por acaso). Tarefa simples: dá para usar um modelo barato.
2. resumo: 1-2 frases em português para cada notícia que ficou.

Cada tarefa tem seu modelo (temas.yaml → ia.tarefas). Um tema pode trocar o
modelo de uma tarefa só para ele (temas.yaml → tema.ia). Notícias que já
têm resumo gravado no banco não passam pela IA de novo.

Sem chave, ou se a chamada falhar, tudo segue com o trecho original do RSS.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .ia import ErroCredencial, ErroIA, criar_cliente
from .temas import ResultadoTema

CONTEXTO = """Você ajuda a montar um e-mail diário de notícias lido por um \
profissional de mercado de crédito (crédito corporativo e soberano, Brasil e \
principais economias). Você recebe o nome de um tema e uma lista de notícias \
(id, título, fontes e, quando existe, um trecho do texto)."""

SISTEMA_RELEVANCIA = CONTEXTO + """

Para cada notícia, diga se ela é de fato sobre o tema:
- relevante: true se trata do tema; false se a palavra-chave apareceu por acaso \
(sentido figurado, finanças pessoais, recomendação de investimento, política sem \
efeito concreto sobre dívida de empresas ou governos, assunto sem relação).

Devolva um item para cada notícia recebida, com o mesmo id."""

SISTEMA_RESUMO = CONTEXTO + """

Para cada notícia, escreva o campo resumo: 1 a 2 frases em português do Brasil, \
no máximo 280 caracteres. Diga o fato principal com os detalhes relevantes para \
crédito que estiverem no texto (quem, valor, instrumento, prazo, credores, rating, \
país). Use só a informação recebida: não invente números, datas nem \
desdobramentos. Se só houver o título, escreva uma frase clara a partir dele, sem \
acrescentar fatos. Notícias em inglês também são resumidas em português. Não \
comece com "A notícia" ou "O artigo".

Devolva um item para cada notícia recebida, com o mesmo id."""


def _schema(campo: str, tipo: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "itens": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "integer"}, campo: {"type": tipo}},
                    "required": ["id", campo],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["itens"],
        "additionalProperties": False,
    }


SCHEMA_RELEVANCIA = _schema("relevante", "boolean")
SCHEMA_RESUMO = _schema("resumo", "string")

TRECHO_MAX = 3000  # caracteres do texto da matéria enviados por notícia


@dataclass
class Tarefa:
    modelo: str
    ativo: bool = True
    esforco: str | None = None  # low | medium | high (modelos com raciocínio)


TAREFAS_PADRAO = {
    "relevancia": Tarefa("anthropic/claude-haiku-5.5", esforco="low"),
    "resumo": Tarefa("anthropic/claude-opus-5.5", esforco="medium"),
}


@dataclass
class ConfigIA:
    provedor: str = "openrouter"
    tarefas: dict[str, Tarefa] = field(default_factory=lambda: dict(TAREFAS_PADRAO))
    remover_irrelevantes: bool = True
    max_por_chamada: int = 40

    def tarefa(self, nome: str, tema=None) -> Tarefa:
        """Configuração da tarefa, com a troca de modelo do tema, se houver."""
        base = self.tarefas.get(nome) or TAREFAS_PADRAO[nome]
        troca = ((getattr(tema, "ia", None) or {}).get(nome)) or {}
        return Tarefa(**{**base.__dict__, **troca})


def carregar_config_ia(caminho: str | Path = "temas.yaml") -> ConfigIA:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    bruto = dict(dados.get("ia") or {})
    tarefas = dict(TAREFAS_PADRAO)
    for nome, valores in (bruto.pop("tarefas", None) or {}).items():
        tarefas[nome] = Tarefa(**{**TAREFAS_PADRAO.get(nome, Tarefa("")).__dict__, **(valores or {})})
    return ConfigIA(tarefas=tarefas, **bruto)


def _entrada(tema: str, lote) -> str:
    noticias = []
    for i, m in enumerate(lote):
        n = m.noticia
        fontes = list(dict.fromkeys(n.fontes + [f for r in m.relacionadas for f in r.fontes]))
        trecho = n.texto[:TRECHO_MAX] or n.resumo or next((r.resumo for r in m.relacionadas if r.resumo), "")
        noticias.append({"id": i, "titulo": n.titulo, "fontes": fontes, "trecho": trecho})
    return json.dumps({"tema": tema, "noticias": noticias}, ensure_ascii=False)


def _rodar(cliente, tarefa: Tarefa, sistema: str, schema: dict, campo: str, tema_nome: str,
           noticias: list, tamanho: int, avisos: list[str], nome_tarefa: str):
    """Chama o modelo em lotes e devolve {match: valor}."""
    valores = {}
    for inicio in range(0, len(noticias), tamanho):
        lote = noticias[inicio : inicio + tamanho]
        try:
            dados = cliente.json(modelo=tarefa.modelo, sistema=sistema, usuario=_entrada(tema_nome, lote),
                                 schema=schema, esforco=tarefa.esforco)
            itens = dados["itens"]
        except ErroCredencial:
            raise
        except (ErroIA, KeyError, TypeError) as e:
            avisos.append(f"{tema_nome} / {nome_tarefa} ({tarefa.modelo}): {e}")
            continue
        for item in itens:
            i = item.get("id") if isinstance(item, dict) else None
            if isinstance(i, int) and 0 <= i < len(lote) and campo in item:
                valores[id(lote[i])] = item[campo]
    return valores


def resumir_temas(resultados: list[ResultadoTema], cfg: ConfigIA, cliente=None) -> list[str]:
    """Aplica relevância e resumo. Devolve avisos (vazio = tudo ok)."""
    pendentes_total = sum(1 for r in resultados for m in r.noticias if not m.resumo_ia)
    if not pendentes_total:
        return []
    if not any(cfg.tarefa(n).ativo for n in ("relevancia", "resumo")):
        return ["IA desligada (temas.yaml → ia.tarefas)"]

    if cliente is None:
        try:
            cliente = criar_cliente(cfg.provedor)
        except (ErroCredencial, ErroIA) as e:
            return [f"IA não rodou: {e}"]

    avisos: list[str] = []
    try:
        for res in resultados:
            nome = res.tema.nome
            pendentes = [m for m in res.noticias if not m.resumo_ia]  # já resumidas: reaproveita

            relev = cfg.tarefa("relevancia", res.tema)
            if relev.ativo and pendentes:
                vals = _rodar(cliente, relev, SISTEMA_RELEVANCIA, SCHEMA_RELEVANCIA, "relevante",
                              nome, pendentes, cfg.max_por_chamada, avisos, "relevância")
                for m in pendentes:
                    if id(m) in vals:
                        m.relevante = bool(vals[id(m)])
                if cfg.remover_irrelevantes:
                    fora = [m for m in res.noticias if not m.relevante]
                    res.noticias = [m for m in res.noticias if m.relevante]
                    res.excluidas += [(m.noticia, "IA: fora do tema") for m in fora]
                    pendentes = [m for m in pendentes if m.relevante]

            resumo = cfg.tarefa("resumo", res.tema)
            if resumo.ativo and pendentes:
                vals = _rodar(cliente, resumo, SISTEMA_RESUMO, SCHEMA_RESUMO, "resumo",
                              nome, pendentes, cfg.max_por_chamada, avisos, "resumo")
                for m in pendentes:
                    if id(m) in vals:
                        m.resumo_ia = str(vals[id(m)]).strip()
    except ErroCredencial as e:
        avisos.append(f"IA não rodou: {e}")
    return avisos
