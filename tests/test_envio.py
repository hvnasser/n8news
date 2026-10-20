import smtplib
from datetime import datetime, timezone

import pytest

from n8news.busca import Noticia
from n8news.envio import enviar_gmail, montar_email
from n8news.temas import Filtro, Match, ResultadoTema, Tema

AGORA = datetime(2026, 10, 20, 9, 50, tzinfo=timezone.utc)


def noticia(titulo, link, fonte="Valor", hora=12, resumo=""):
    return Noticia(titulo, link, resumo, fonte, "economia",
                   datetime(2026, 10, 20, hora, tzinfo=timezone.utc), [fonte], ["economia"])


def resultado():
    tema = Tema("credito", "Crédito", [Filtro("Spreads corporativos", ["x"]), Filtro("Default e calote", ["y"])])
    ri = Match(noticia("Ri Happy pede RE <urgente> & cia", "https://g1.com/ri?a=1&b=2", "G1", 10),
               ["Default e calote"], ["calote"], resumo_ia="Grupo pede RE para R$ 827 mi.",
               relacionadas=[noticia("Ri Happy RE", "https://estadao.com/ri", "Estadão")])
    so_titulo = Match(noticia("Ares Warns of Credit Stress", "https://news.google.com/x", "Bloomberg", 13),
                      ["Spreads corporativos"], ["private credit"], resumo_ia="Ares Warns of Credit Stress")
    deb = Match(noticia("Debêntures batem recorde", "https://valor.com/d", hora=15),
                ["Spreads corporativos"], ["debênture*"], resumo_ia="Emissões somam R$ 50 bi.")
    return [ResultadoTema(tema, [ri, so_titulo, deb])]


def test_monta_email_por_tema_e_filtro():
    assunto, corpo, texto = montar_email(resultado(), AGORA)
    assert assunto == "N8News 20/10/2026 — Crédito: 3 notícias"
    # ordem dos filtros do tema; dentro do filtro, mais recente primeiro
    assert corpo.index("Spreads corporativos") < corpo.index("Default e calote")
    assert corpo.index("Debêntures batem recorde") < corpo.index("Ares Warns")
    # caracteres especiais escapados
    assert "Ri Happy pede RE &lt;urgente&gt; &amp; cia" in corpo
    assert 'href="https://g1.com/ri?a=1&amp;b=2"' in corpo
    # resumo que só repete o título não aparece duas vezes
    assert corpo.count("Ares Warns of Credit Stress") == 1
    assert "Grupo pede RE para R$ 827 mi." in corpo
    # outros jornais com link
    assert 'Também em: <a href="https://estadao.com/ri"' in corpo
    # horário de Brasília
    assert "G1 · 20/10 07:00" in corpo
    assert "* Ri Happy pede RE <urgente> & cia (G1 · 20/10 07:00)" in texto


def test_dia_sem_noticias():
    tema = Tema("credito", "Crédito", [Filtro("f", ["x"])])
    assunto, corpo, _ = montar_email([ResultadoTema(tema, [])], AGORA)
    assert "sem notícias novas" in assunto and "Nenhuma notícia nova" in corpo


class FakeSMTP:
    instancias = []

    def __init__(self, host, porta, timeout):
        self.host, self.porta = host, porta
        self.passos, self.mensagens = [], []
        FakeSMTP.instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.passos.append("quit")

    def starttls(self):
        self.passos.append("starttls")

    def login(self, usuario, senha):
        if senha != "abcdefghijklmnop":
            raise smtplib.SMTPAuthenticationError(535, b"bad")
        self.passos.append(("login", usuario))

    def send_message(self, msg):
        self.mensagens.append(msg)


def test_envia_pelo_gmail(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "eu@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcd efgh ijkl mnop")  # Google mostra com espaços
    monkeypatch.delenv("EMAIL_PARA", raising=False)
    assunto, corpo, texto = montar_email(resultado(), AGORA)
    assert enviar_gmail(assunto, corpo, texto, smtp_factory=FakeSMTP) == ["eu@gmail.com"]
    smtp = FakeSMTP.instancias[-1]
    assert (smtp.host, smtp.porta) == ("smtp.gmail.com", 587)
    assert smtp.passos[:2] == ["starttls", ("login", "eu@gmail.com")]
    msg = smtp.mensagens[0]
    assert msg["Subject"] == assunto and msg["To"] == "eu@gmail.com"
    tipos = [p.get_content_type() for p in msg.iter_parts()]
    assert tipos == ["text/plain", "text/html"]


def test_varios_destinatarios_e_erros(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "eu@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "abcdefghijklmnop")
    monkeypatch.setenv("EMAIL_PARA", "a@x.com, b@y.com")
    assert enviar_gmail("s", "<p>h</p>", "t", smtp_factory=FakeSMTP) == ["a@x.com", "b@y.com"]

    monkeypatch.setenv("GMAIL_APP_PASSWORD", "errada")
    with pytest.raises(RuntimeError, match="senha de app"):
        enviar_gmail("s", "h", "t", smtp_factory=FakeSMTP)

    monkeypatch.delenv("GMAIL_USER")
    with pytest.raises(RuntimeError, match="não configurados"):
        enviar_gmail("s", "h", "t", smtp_factory=FakeSMTP)


def test_opiniao_em_negrito():
    res = resultado()
    res[0].noticias[2].resumo_ia = "Opinião — Fulano: Texto da coluna."
    _, corpo, _ = montar_email(res, AGORA)
    assert "<b>Opinião — Fulano:</b> Texto da coluna." in corpo
