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
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .busca import Noticia
from .paises import Pais, detectar, expandir_permitidos
from .texto import compilar, normalizar, primeira


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
    paises_permitidos: list[str] = field(default_factory=list)  # grupos (g10, em) ou códigos; vazio = todos
    ativo: bool = True

    def __post_init__(self):
        self._excluir = compilar(self.excluir)

    def radicais_genericos(self) -> set[str]:
        """Radicais das palavras-chave do tema (comuns a muitas notícias)."""
        termos = " ".join(p for f in self.filtros for p in f.palavras + f.exige)
        return _radicais(termos.replace("*", ""))


@dataclass
class Match:
    noticia: Noticia
    filtros: list[str]           # nomes dos filtros que casaram
    palavras: list[str]          # palavra que casou em cada filtro
    relacionadas: list[Noticia] = field(default_factory=list)  # mesma história, outros jornais
    paises: list[str] = field(default_factory=list)  # códigos dos países citados
    resumo_ia: str = ""  # preenchido pela etapa de resumo
    relevante: bool = True  # a IA pode marcar como fora do tema


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


_STOPWORDS = set("""
a o e de da do das dos em no na nos nas um uma com por para que se ao aos apos sobre
diz mais seu sua the of and to in on for with by at as is are from after over its
empresa empresas grupo company companhia report reports ltda inc corp holding holdings
""".split())


def _radicais(texto: str) -> set[str]:
    """Palavras do texto reduzidas aos 5 primeiros caracteres
    (pede/pediu/pedido -> pede/pediu/pedid; recuperação -> recup)."""
    return {
        w[:5]
        for w in normalizar(texto).split()
        if (len(w) >= 3 or w.isdigit()) and w not in _STOPWORDS
    }


def _nomes_proprios(titulo: str) -> set[str]:
    """Radicais de palavras com maiúscula ou números: nomes de empresas,
    países, valores (Ri Happy, Barclays, 827)."""
    palavras = [w for w in re.split(r"[^\w$]+", titulo) if w]
    return _radicais(" ".join(w for w in palavras if w[0].isupper() or w[0].isdigit()))


def _parecidas(a: tuple[set[str], set[str]], b: tuple[set[str], set[str]], genericas: set[str]) -> bool:
    (rad_a, nomes_a), (rad_b, nomes_b) = a, b
    comum = rad_a & rad_b
    if len(comum) < 3 or len(comum) / min(len(rad_a), len(rad_b)) < 0.5:
        return False
    # Precisa de um nome próprio/número em comum, senão "A pede recuperação
    # judicial" juntaria com "B pede recuperação judicial"
    return bool((comum & (nomes_a | nomes_b)) - genericas)


def _qualidade(n: Noticia) -> tuple:
    # Prefere link direto do jornal (não Google News), com resumo e mais fontes
    return ("news.google.com" not in n.link, bool(n.resumo), len(n.fontes))


def agrupar_parecidas(matches: list[Match], genericas: set[str] = frozenset()) -> list[Match]:
    """Junta notícias sobre o mesmo fato com títulos diferentes
    (ex: 8 jornais noticiando a mesma recuperação judicial).
    `genericas`: radicais comuns no tema (ex: recup, judic) que sozinhos não
    bastam para dizer que é a mesma notícia."""
    grupos: list[tuple[list, list[Match]]] = []
    for m in matches:
        palavras = (_radicais(m.noticia.titulo), _nomes_proprios(m.noticia.titulo))
        iguais = [g for g in grupos if any(_parecidas(palavras, c, genericas) for c in g[0])]
        if not iguais:
            grupos.append(([palavras], [m]))
            continue
        # Se parece com mais de um grupo, junta todos num só
        chaves, membros = iguais[0]
        for outro in iguais[1:]:
            chaves.extend(outro[0])
            membros.extend(outro[1])
            grupos.remove(outro)
        chaves.append(palavras)
        membros.append(m)

    resultado = []
    for _, membros in grupos:
        principal = max(membros, key=lambda m: _qualidade(m.noticia))
        for outro in membros:
            if outro is principal:
                continue
            principal.relacionadas.append(outro.noticia)
            principal.paises += [c for c in outro.paises if c not in principal.paises]
            for f, p in zip(outro.filtros, outro.palavras):
                if f not in principal.filtros:
                    principal.filtros.append(f)
                    principal.palavras.append(p)
        resultado.append(principal)
    return resultado


def classificar(noticias: list[Noticia], temas: list[Tema], paises: list[Pais] | None = None) -> list[ResultadoTema]:
    paises = paises or []
    resultados = []
    for tema in temas:
        res = ResultadoTema(tema, [])
        permitidos = expandir_permitidos(paises, tema.paises_permitidos) if tema.paises_permitidos else set()
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
            citados = [p.codigo for p in detectar(paises, texto)]
            # Cita países, mas nenhum da lista permitida (ex: só Gana) -> fora
            if permitidos and citados and not set(citados) & permitidos:
                res.excluidas.append((n, "país fora da lista: " + ", ".join(citados)))
                continue
            res.noticias.append(Match(n, [c[0] for c in casados], [c[1] for c in casados], paises=citados))
        res.noticias = agrupar_parecidas(res.noticias, tema.radicais_genericos())
        resultados.append(res)
    return resultados
