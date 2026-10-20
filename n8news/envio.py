"""Etapa 4: monta o e-mail do dia e envia pelo Gmail.

Precisa de:
- GMAIL_USER: o seu endereço Gmail (remetente)
- GMAIL_APP_PASSWORD: senha de app do Google (não é a senha normal), criada em
  https://myaccount.google.com/apppasswords
- EMAIL_PARA (opcional): destinatários separados por vírgula. Padrão: o próprio
  GMAIL_USER.
"""

from __future__ import annotations

import html
import os
import smtplib
from collections import defaultdict
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from .temas import ResultadoTema

FUSO = ZoneInfo("America/Sao_Paulo")
SMTP_GMAIL = ("smtp.gmail.com", 587)


def _hora(n) -> str:
    return n.publicado_em.astimezone(FUSO).strftime("%d/%m %H:%M") if n.publicado_em else ""


def _resumo(m) -> str:
    """Resumo a mostrar; vazio quando é só o título repetido."""
    r = (m.resumo_ia or m.noticia.resumo or "").strip()
    return "" if r == m.noticia.titulo.strip() else r


def _qtd(n: int) -> str:
    return f"{n} notícia" if n == 1 else f"{n} notícias"


def _desde(desde: datetime | None) -> str:
    return f" — novas desde o último e-mail ({desde.astimezone(FUSO):%d/%m %H:%M})" if desde else ""


def _recentes_primeiro(lista):
    return sorted(lista, key=lambda m: m.noticia.publicado_em or datetime.min.replace(tzinfo=FUSO), reverse=True)


def _grupos(res: ResultadoTema):
    """(filtro, [(subtítulo ou "", notícias)]) na ordem dos filtros do temas.yaml.
    Filtros com separar_brasil dividem em Brasil / Mundo."""
    por_filtro = defaultdict(list)
    for m in res.noticias:
        por_filtro[m.filtros[0]].append(m)
    for f in res.tema.filtros:
        lista = por_filtro.get(f.nome)
        if not lista:
            continue
        if f.separar_brasil and not f.regiao:
            partes = [("Brasil", [m for m in lista if m.regiao == "brasil"]),
                      ("Mundo", [m for m in lista if m.regiao != "brasil"])]
            yield f.nome, [(t, _recentes_primeiro(l)) for t, l in partes if l]
        else:
            yield f.nome, [("", _recentes_primeiro(lista))]


def _outros(m) -> list[tuple[str, str]]:
    vistos, outros = set(m.noticia.fontes), []
    for r in m.relacionadas:
        for f in r.fontes:
            if f not in vistos:
                vistos.add(f)
                outros.append((f, r.link))
    return outros


def _item(m, partes: list[str], texto: list[str]) -> None:
    e = html.escape
    n = m.noticia
    meta = " · ".join(x for x in [", ".join(n.fontes), _hora(n)] if x)
    resumo = _resumo(m)
    outros = _outros(m)
    partes.append('<div style="margin:0 0 14px;">')
    partes.append(f'<a href="{e(n.link, quote=True)}" style="font-size:15px;font-weight:bold;'
                  f'color:#0969da;text-decoration:none;">{e(n.titulo)}</a>')
    partes.append(f'<div style="font-size:12px;color:#59636e;margin-top:2px;">{e(meta)}</div>')
    if resumo:
        corpo = e(resumo)
        if resumo.startswith("Opinião") and ": " in resumo:
            rotulo, resto = resumo.split(": ", 1)
            corpo = f"<b>{e(rotulo)}:</b> {e(resto)}"
        partes.append(f'<div style="font-size:14px;line-height:1.45;margin-top:4px;">{corpo}</div>')
    if outros:
        links = ", ".join(f'<a href="{e(l, quote=True)}" style="color:#59636e;">{e(f)}</a>' for f, l in outros)
        partes.append(f'<div style="font-size:12px;color:#59636e;margin-top:3px;">Também em: {links}</div>')
    partes.append("</div>")
    texto += [f"* {n.titulo} ({meta})", f"  {n.link}"]
    if resumo:
        texto.append(f"  {resumo}")
    if outros:
        texto.append("  Também em: " + ", ".join(f for f, _ in outros))
    texto.append("")


def selecionar_novas(resultados: list[ResultadoTema], ja_enviadas: set[str], id_de) -> list[ResultadoTema]:
    """Cópia dos resultados só com notícias que ainda não foram enviadas."""
    return [ResultadoTema(r.tema, [m for m in r.noticias if id_de(m.noticia.link) not in ja_enviadas])
            for r in resultados]


def montar_email(resultados: list[ResultadoTema], agora: datetime | None = None,
                 desde: datetime | None = None) -> tuple[str, str, str]:
    """Devolve (assunto, html, texto simples)."""
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    data = agora.strftime("%d/%m/%Y")
    total = sum(len(r.noticias) for r in resultados)
    nomes = ", ".join(r.tema.nome for r in resultados if r.noticias)
    hora = agora.strftime("%Hh%M")
    assunto = (f"N8News {data} {hora} — {nomes}: {_qtd(total)}" if total
               else f"N8News {data} {hora} — sem notícias novas")

    e = html.escape
    partes = [
        '<div style="font-family:Arial,Helvetica,sans-serif;max-width:680px;margin:0 auto;color:#1f2328;">',
        f'<h1 style="font-size:20px;margin:0 0 4px;">N8News — {e(data)}</h1>',
        f'<p style="margin:0 0 20px;color:#59636e;font-size:13px;">{_qtd(total)}{e(_desde(desde))}</p>',
    ]
    texto = [f"N8News — {data} — {_qtd(total)}{_desde(desde)}", ""]

    for res in resultados:
        if not res.noticias:
            continue
        partes.append(f'<h2 style="font-size:18px;margin:24px 0 8px;padding-bottom:4px;'
                      f'border-bottom:2px solid #d1d9e0;">{e(res.tema.nome)} ({len(res.noticias)})</h2>')
        texto += [f"=== {res.tema.nome.upper()} ({len(res.noticias)}) ===", ""]
        for filtro, partes_filtro in _grupos(res):
            partes.append(f'<h3 style="font-size:14px;margin:18px 0 6px;color:#59636e;'
                          f'text-transform:uppercase;letter-spacing:.03em;">{e(filtro)}</h3>')
            texto += [f"-- {filtro} --"]
            for subtitulo, lista in partes_filtro:
                if subtitulo:
                    partes.append(f'<div style="font-size:13px;font-weight:bold;color:#1f2328;'
                                  f'margin:10px 0 6px;">{e(subtitulo)}</div>')
                    texto += [f"[{subtitulo}]"]
                for m in lista:
                    _item(m, partes, texto)
    if not total:
        partes.append("<p>Nenhuma notícia nova nos temas hoje.</p>")
        texto.append("Nenhuma notícia nova nos temas hoje.")
    partes.append('<p style="font-size:11px;color:#8c959f;margin-top:28px;">Gerado automaticamente pelo N8News.</p></div>')
    return assunto, "\n".join(partes), "\n".join(texto)


def enviar_gmail(assunto: str, corpo_html: str, corpo_texto: str, smtp_factory=smtplib.SMTP) -> list[str]:
    """Envia pelo Gmail. Devolve a lista de destinatários."""
    usuario = os.environ.get("GMAIL_USER", "").strip()
    senha = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not usuario or not senha:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD não configurados")
    para = [x.strip() for x in os.environ.get("EMAIL_PARA", "").split(",") if x.strip()] or [usuario]

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = f"N8News <{usuario}>"
    msg["To"] = ", ".join(para)
    msg.set_content(corpo_texto)
    msg.add_alternative(corpo_html, subtype="html")

    with smtp_factory(*SMTP_GMAIL, timeout=30) as smtp:
        smtp.starttls()
        try:
            smtp.login(usuario, senha)
        except smtplib.SMTPAuthenticationError as e:
            raise RuntimeError("Gmail recusou o login: confira GMAIL_USER e a senha de app") from e
        smtp.send_message(msg)
    return para
