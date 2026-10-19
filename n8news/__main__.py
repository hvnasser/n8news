"""Uso: python -m n8news [--config feeds.yaml] [--horas 24] [--json saida.json]"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from .busca import buscar_noticias, carregar_config


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="n8news", description="Busca notícias nos feeds RSS.")
    p.add_argument("--config", default="feeds.yaml", help="arquivo de feeds (padrão: feeds.yaml)")
    p.add_argument("--horas", type=float, help="sobrescreve a janela de tempo do config")
    p.add_argument("--json", metavar="ARQUIVO", help="salva as notícias em JSON")
    p.add_argument("--quieto", action="store_true", help="não lista as notícias, só o resumo")
    args = p.parse_args(argv)

    config = carregar_config(args.config)
    if args.horas:
        config.janela_horas = args.horas

    resultado = buscar_noticias(config)

    if not args.quieto:
        por_categoria = defaultdict(list)
        for n in resultado.noticias:
            por_categoria[n.categoria].append(n)
        for categoria, noticias in por_categoria.items():
            print(f"\n=== {categoria.upper()} ({len(noticias)}) ===")
            for n in noticias:
                quando = n.publicado_em.astimezone().strftime("%d/%m %H:%M") if n.publicado_em else "--"
                print(f"- [{quando}] {n.titulo}  ({', '.join(n.fontes)})")
                print(f"  {n.link}")
                if n.resumo:
                    print(f"  {n.resumo[:160]}")

    print("\n=== STATUS DOS FEEDS ===")
    for s in resultado.status:
        detalhe = s.erro if s.status == "erro" else f"{s.noticias} notícias"
        print(f"[{s.status.upper():5}] {s.fonte:20} {detalhe}")

    ok = sum(s.status == "ok" for s in resultado.status)
    print(f"\nTotal: {len(resultado.noticias)} notícias de {ok}/{len(resultado.status)} feeds "
          f"(últimas {config.janela_horas:g}h)")

    if args.json:
        dados = {
            "noticias": [n.to_dict() for n in resultado.noticias],
            "status": [s.__dict__ for s in resultado.status],
        }
        Path(args.json).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Salvo em {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
