from datetime import datetime, timezone

from n8news.artigo import baixar_textos, extrair_texto
from n8news.banco import Supabase, id_noticia, linha_noticia, reaproveitar
from n8news.busca import Noticia
from n8news.temas import Filtro, Match, ResultadoTema, Tema


def noticia(titulo, link, resumo=""):
    return Noticia(titulo, link, resumo, "G1", "economia",
                   datetime(2026, 10, 19, 13, tzinfo=timezone.utc), ["G1"], ["economia"])


def resultado(*matches):
    return [ResultadoTema(Tema("credito", "Crédito", [Filtro("f", ["x"])]), list(matches))]


class FakeHTTP:
    def __init__(self, respostas=None):
        self.chamadas, self.respostas = [], respostas or {}

    def __call__(self, metodo, caminho, corpo, headers):
        self.chamadas.append((metodo, caminho, corpo, headers))
        return self.respostas.get(metodo)


def test_id_ignora_rastreamento():
    assert id_noticia("https://www.g1.com/a/?utm_source=rss") == id_noticia("https://g1.com/a")


def test_salvar_monta_upserts():
    rel = noticia("Ri Happy pede RE", "https://estadao.com/x")
    rel.fontes = ["Estadão"]
    m = Match(noticia("Ri Happy pede RE", "https://g1.com/x", "trecho"), ["RJ"], ["recuperação extrajudicial"],
              relacionadas=[rel], paises=["BRA"], resumo_ia="Resumo")
    http = FakeHTTP()
    banco = Supabase("https://abc.supabase.co", "sb_secret_123", enviar=http)
    assert banco.salvar(resultado(m)) == 1

    (met1, cam1, corpo1, h1), (met2, cam2, corpo2, _) = http.chamadas
    assert (met1, cam1) == ("POST", "/noticias?on_conflict=id")
    assert h1["apikey"] == "sb_secret_123" and "Authorization" not in h1
    assert "merge-duplicates" in h1["Prefer"]
    linha = corpo1[0]
    assert linha["fontes"] == ["G1", "Estadão"]
    assert linha["outros_links"] == [{"fonte": "G1", "link": "https://estadao.com/x", "titulo": "Ri Happy pede RE"}]
    assert linha["resumo_ia"] == "Resumo" and linha["trecho_rss"] == "trecho"
    assert linha["publicado_em"] == "2026-10-19T13:00:00+00:00"
    assert "coletado_em" not in linha
    assert cam2 == "/noticias_temas?on_conflict=noticia_id,tema"
    assert corpo2 == [{"noticia_id": linha["id"], "tema": "credito", "filtros": ["RJ"],
                       "palavras": ["recuperação extrajudicial"]}]


def test_chave_jwt_vai_no_authorization():
    http = FakeHTTP()
    Supabase("https://abc.supabase.co", "eyJabc", enviar=http).existentes(["a"])
    assert http.chamadas[0][3]["Authorization"] == "Bearer eyJabc"
    assert http.chamadas[0][1] == "/noticias?select=id,resumo_ia,texto&id=in.(a)"


def test_todas_as_linhas_tem_as_mesmas_colunas():
    a = linha_noticia("a", Match(noticia("A", "https://a"), [], []), "agora")
    b = linha_noticia("b", Match(noticia("B", "https://b", "x"), [], [], resumo_ia="r", paises=["BRA"]), "agora")
    assert a.keys() == b.keys()


def test_reaproveitar():
    m1 = Match(noticia("A", "https://a"), [], [])
    m2 = Match(noticia("B", "https://b"), [], [], resumo_ia="novo")
    existentes = {id_noticia("https://a"): {"resumo_ia": "antigo", "texto": "texto antigo"},
                  id_noticia("https://b"): {"resumo_ia": "antigo", "texto": None}}
    assert reaproveitar(resultado(m1, m2), existentes) == 1
    assert (m1.resumo_ia, m1.noticia.texto) == ("antigo", "texto antigo")
    assert m2.resumo_ia == "novo"


def test_do_ambiente(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert Supabase.do_ambiente() is None
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    assert Supabase.do_ambiente().base == "https://abc.supabase.co/rest/v1"


HTML = """<html><head><title>Ri Happy</title></head><body>
<nav>Menu Home Economia Política</nav>
<article><h1>Ri Happy pede recuperação extrajudicial</h1>
<p>A Ri Happy e outras cinco empresas do grupo entraram com um pedido de recuperação extrajudicial
na Justiça de São Paulo, no domingo (18), para renegociar R$ 827,4 milhões em dívidas.</p>
<p>Segundo o pedido, a reestruturação envolve credores financeiros que detêm a maior parte das
debêntures emitidas pela companhia nos últimos anos, com alongamento de prazos e carência.</p>
<p>A empresa afirma que as lojas seguem funcionando normalmente durante o processo.</p>
</article><footer>Copyright Globo</footer></body></html>"""


def test_extrai_texto_principal():
    texto = extrair_texto(HTML)
    assert "R$ 827,4 milhões" in texto and "lojas seguem" in texto
    assert "Menu Home" not in texto and "Copyright" not in texto


def test_baixar_textos_pula_google_e_erros():
    ok = noticia("A", "https://g1.com/a", "curto")
    google = noticia("B", "https://news.google.com/rss/articles/x")
    fora = noticia("C", "https://fora.com/c")

    def baixar(url, timeout):
        if "fora" in url:
            raise TimeoutError()
        assert "google" not in url
        return HTML.encode()

    assert baixar_textos([ok, google, fora], baixar_fn=baixar) == 1
    assert "827,4" in ok.texto and google.texto == "" and fora.texto == ""
