"""Uso:
    python -m n8news                  # notícias separadas por tema
    python -m n8news --todas          # todas as notícias, sem filtro de tema
    python -m n8news --json saida.json
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from .busca import buscar_noticias, carregar_config
from .temas import carregar_temas, classificar


def quando(n) -> str:
    return n.publicado_em.astimezone().strftime("%d/%m %H:%M") if n.publicado_em else "--"


def imprimir_noticia(n, extra: str = "") -> None:
    print(f"- [{quando(n)}] {n.titulo}  ({', '.join(n.fontes)}){extra}")
    print(f"  {n.link}")
    if n.resumo:
        print(f"  {n.resumo[:200]}")


def imprimir_todas(noticias) -> None:
    por_categoria = defaultdict(list)
    for n in noticias:
        por_categoria[n.categoria].append(n)
    for categoria, lista in por_categoria.items():
        print(f"\n=== {categoria.upper()} ({len(lista)}) ===")
        for n in lista:
            imprimir_noticia(n)


def imprimir_temas(resultados) -> None:
    for res in resultados:
        print(f"\n{'=' * 70}\n{res.tema.nome.upper()} — {len(res.noticias)} notícias\n{'=' * 70}")
        # Agrupa pelo primeiro filtro que casou (na ordem do temas.yaml)
        grupos = defaultdict(list)
        for m in res.noticias:
            grupos[m.filtros[0]].append(m)
        for filtro in res.tema.filtros:
            lista = grupos.get(filtro.nome)
            if not lista:
                continue
            print(f"\n--- {filtro.nome} ({len(lista)}) ---")
            for m in lista:
                motivo = "; ".join(f"{f}: {p}" for f, p in zip(m.filtros, m.palavras))
                imprimir_noticia(m.noticia, f"\n  ↳ {motivo}")
        if res.excluidas:
            print(f"\n--- Excluídas pelo filtro 'excluir' ({len(res.excluidas)}) ---")
            for n, palavra in res.excluidas:
                print(f"- {n.titulo}  [{palavra}]")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="n8news", description="Busca notícias e separa por tema.")
    p.add_argument("--config", default="feeds.yaml", help="arquivo de feeds (padrão: feeds.yaml)")
    p.add_argument("--temas", default="temas.yaml", help="arquivo de temas (padrão: temas.yaml)")
    p.add_argument("--horas", type=float, help="sobrescreve a janela de tempo do config")
    p.add_argument("--todas", action="store_true", help="lista todas as notícias, sem separar por tema")
    p.add_argument("--json", metavar="ARQUIVO", help="salva notícias e temas em JSON")
    p.add_argument("--quieto", action="store_true", help="não lista as notícias, só o resumo")
    args = p.parse_args(argv)

    config = carregar_config(args.config)
    if args.horas:
        config.janela_horas = args.horas

    resultado = buscar_noticias(config)
    temas = carregar_temas(args.temas)
    por_tema = classificar(resultado.noticias, temas)

    if not args.quieto:
        if args.todas:
            imprimir_todas(resultado.noticias)
        else:
            imprimir_temas(por_tema)

    print("\n=== STATUS DOS FEEDS ===")
    for s in resultado.status:
        detalhe = s.erro if s.status == "erro" else f"{s.noticias} notícias"
        nome = f"{s.fonte} ({s.categoria})"
        print(f"[{s.status.upper():5}] {nome:36} {detalhe}")

    ok = sum(s.status == "ok" for s in resultado.status)
    print(f"\nTotal: {len(resultado.noticias)} notícias de {ok}/{len(resultado.status)} feeds "
          f"(últimas {config.janela_horas:g}h)")
    for res in por_tema:
        print(f"Tema {res.tema.nome}: {len(res.noticias)} notícias")

    if args.json:
        dados = {
            "noticias": [n.to_dict() for n in resultado.noticias],
            "temas": [
                {
                    "id": r.tema.id,
                    "nome": r.tema.nome,
                    "noticias": [
                        {**m.noticia.to_dict(), "filtros": m.filtros, "palavras": m.palavras}
                        for m in r.noticias
                    ],
                }
                for r in por_tema
            ],
            "status": [s.__dict__ for s in resultado.status],
        }
        Path(args.json).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Salvo em {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
