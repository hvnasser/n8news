"""Etapa 2: separa as notícias por tema usando filtros de palavras-chave.

Cada tema (ex: Crédito) tem vários filtros (ex: "Spreads", "Default"). Uma
notícia entra no tema se passar em pelo menos um filtro ativo e não tiver
nenhuma palavra da lista `excluir` do tema.

Regras das palavras-chave (ver temas.yaml):
- maiúsculas, acentos, hífens e apóstrofos são ignorados
  ("risco-país" casa com "Risco Pais"; "high yield" casa com "high-yield")
- a palavra precisa aparecer inteira: "default" não casa com "defaulted"
- `*` aceita qualquer final: "renegoci*" casa com renegociação, renegociar...
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .busca import Noticia


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"['’`´]", "", texto)
    texto = re.sub(r"[^a-z0-9*]+", " ", texto)
    return f" {texto.strip()} "


def compilar(palavras: list[str]) -> list[tuple[str, re.Pattern]]:
    padroes = []
    for p in palavras:
        norm = normalizar(str(p)).strip()
        if not norm:
            continue
        regex = r"\b" + re.escape(norm).replace(r"\*", r"\w*") + r"\b"
        padroes.append((str(p), re.compile(regex)))
    return padroes


def primeira(padroes, texto: str) -> str | None:
    for original, regex in padroes:
        if regex.search(texto):
            return original
    return None


@dataclass
class Filtro:
    nome: str
    palavras: list[str]
    exige: list[str] = field(default_factory=list)
    ativo: bool = True

    def __post_init__(self):
        self._palavras = compilar(self.palavras)
        self._exige = compilar(self.exige)

    def casa(self, texto_norm: str) -> str | None:
        """Retorna a palavra que fez a notícia passar, ou None."""
        achada = primeira(self._palavras, texto_norm)
        if achada and self._exige and not primeira(self._exige, texto_norm):
            return None
        return achada


@dataclass
class Tema:
    id: str
    nome: str
    filtros: list[Filtro]
    categorias: list[str] = field(default_factory=list)  # vazio = todas
    excluir: list[str] = field(default_factory=list)
    ativo: bool = True

    def __post_init__(self):
        self._excluir = compilar(self.excluir)


@dataclass
class Match:
    noticia: Noticia
    filtros: list[str]           # nomes dos filtros que casaram
    palavras: list[str]          # palavra que casou em cada filtro


@dataclass
class ResultadoTema:
    tema: Tema
    noticias: list[Match]
    excluidas: list[tuple[Noticia, str]] = field(default_factory=list)


def carregar_temas(caminho: str | Path = "temas.yaml") -> list[Tema]:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    temas = []
    for t in dados.get("temas") or []:
        filtros = [Filtro(**f) for f in t.pop("filtros", []) or []]
        tema = Tema(filtros=[f for f in filtros if f.ativo], **t)
        if tema.ativo:
            temas.append(tema)
    return temas


def classificar(noticias: list[Noticia], temas: list[Tema]) -> list[ResultadoTema]:
    resultados = []
    for tema in temas:
        res = ResultadoTema(tema, [])
        for n in noticias:
            if tema.categorias and not set(n.categorias) & set(tema.categorias):
                continue
            texto = normalizar(f"{n.titulo} {n.resumo}")
            casados = [(f.nome, p) for f in tema.filtros if (p := f.casa(texto))]
            if not casados:
                continue
            if bloqueio := primeira(tema._excluir, texto):
                res.excluidas.append((n, bloqueio))
                continue
            res.noticias.append(Match(n, [c[0] for c in casados], [c[1] for c in casados]))
        resultados.append(res)
    return resultados
