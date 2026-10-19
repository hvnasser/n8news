"""Baixa a página de cada notícia e extrai o texto principal (trafilatura).

Em sites com paywall (Valor, FT, WSJ) normalmente só vem o começo da matéria.
Links do Google News passam por um redirecionamento em JavaScript e não são
baixados; essas notícias ficam só com o trecho do RSS.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import trafilatura

from .busca import Noticia, baixar

MAX_CARACTERES = 20000


def extrair_texto(html: bytes | str) -> str:
    texto = trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)
    return (texto or "").strip()


def _texto_da_noticia(n: Noticia, timeout: float, baixar_fn) -> str:
    if "news.google.com" in n.link:
        return ""
    try:
        return extrair_texto(baixar_fn(n.link, timeout))[:MAX_CARACTERES]
    except Exception:  # noqa: BLE001 - página fora do ar não pode parar o robô
        return ""


def baixar_textos(noticias: list[Noticia], timeout: float = 15, baixar_fn=baixar) -> int:
    """Preenche `texto` das notícias que ainda não têm. Devolve quantas ganharam texto."""
    pendentes = [n for n in noticias if not n.texto]
    with ThreadPoolExecutor(max_workers=8) as pool:
        textos = list(pool.map(lambda n: _texto_da_noticia(n, timeout, baixar_fn), pendentes))
    ok = 0
    for n, texto in zip(pendentes, textos):
        # Só vale se trouxer mais que o trecho do RSS
        if len(texto) > len(n.resumo) + 80:
            n.texto = texto
            ok += 1
    return ok
