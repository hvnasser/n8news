"""Detecta países citados numa notícia (lista em paises.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .texto import compilar


@dataclass
class Pais:
    codigo: str
    grupo: str
    nomes: list[str]

    def __post_init__(self):
        self._padroes = compilar(self.nomes)

    def citado(self, texto_norm: str) -> bool:
        return any(regex.search(texto_norm) for _, regex in self._padroes)


def carregar_paises(caminho: str | Path = "paises.yaml") -> list[Pais]:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    return [Pais(codigo, **info) for codigo, info in (dados.get("paises") or {}).items()]


def detectar(paises: list[Pais], texto_norm: str) -> list[Pais]:
    return [p for p in paises if p.citado(texto_norm)]


def expandir_permitidos(paises: list[Pais], permitidos: list[str]) -> set[str]:
    """Aceita grupos (g10, em) e códigos de país (ARG) na lista."""
    chaves = {str(x).lower() for x in permitidos}
    return {p.codigo for p in paises if p.grupo.lower() in chaves or p.codigo.lower() in chaves}
