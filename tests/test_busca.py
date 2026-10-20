from datetime import datetime, timezone

from n8news.busca import (
    Config, Feed, buscar_noticias, carregar_config, chave_link, cortar, limpar_texto,
)

AGORA = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)

RSS_G1 = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel><title>G1</title>
<item>
  <title>Petrobras anuncia &amp; dividendos</title>
  <link>https://g1.globo.com/economia/noticia/petrobras.ghtml?utm_source=rss</link>
  <description><![CDATA[<img src="x.jpg"/><br/> A estatal   aprovou o pagamento &quot;extra&quot;.]]></description>
  <pubDate>Sun, 19 Oct 2026 10:00:00 -0300</pubDate>
  <media:content url="https://s2.glbimg.com/foto.jpg" medium="image"/>
</item>
<item>
  <title>Noticia antiga</title>
  <link>https://g1.globo.com/velha.ghtml</link>
  <pubDate>Mon, 13 Oct 2026 10:00:00 -0300</pubDate>
</item>
<item>
  <title>Sem data</title>
  <link>https://g1.globo.com/sem-data.ghtml</link>
</item>
<item><title></title><link>https://g1.globo.com/sem-titulo</link></item>
</channel></rss>"""

# Mesma notícia da Petrobras (link igual sem utm) + uma nova
RSS_FOLHA = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<rss version="2.0"><channel><title>Folha</title>
<item>
  <title>Petrobras anuncia &amp; dividendos</title>
  <link>https://www.g1.globo.com/economia/noticia/petrobras.ghtml/</link>
  <pubDate>Sun, 19 Oct 2026 10:05:00 -0300</pubDate>
</item>
<item>
  <title>Vale sobe na bolsa</title>
  <link>https://www1.folha.uol.com.br/mercado/vale.shtml</link>
  <description>Acoes da Vale avancam.</description>
  <pubDate>Sun, 19 Oct 2026 11:30:00 -0300</pubDate>
</item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Verge</title>
<entry>
  <title>New AI chip</title>
  <link rel="alternate" href="https://www.theverge.com/chip"/>
  <updated>2026-10-19T08:00:00Z</updated>
  <summary type="html">&lt;p&gt;A new chip.&lt;/p&gt;</summary>
</entry>
</feed>"""

FEEDS = {
    "https://g1/rss": RSS_G1,
    "https://folha/rss": RSS_FOLHA,
    "https://verge/rss": ATOM,
    "https://lixo/rss": b"<html>nao e feed</html>",
}


def fake_baixar(url, timeout):
    if url not in FEEDS:
        raise TimeoutError("timed out")
    return FEEDS[url]


def config(**kw):
    feeds = [
        Feed("G1", "economia", "https://g1/rss"),
        Feed("Folha", "mercado", "https://folha/rss"),
        Feed("The Verge", "tecnologia", "https://verge/rss"),
        Feed("Fora do ar", "brasil", "https://offline/rss"),
        Feed("Lixo", "brasil", "https://lixo/rss"),
    ]
    return Config(feeds=feeds, **kw)


def rodar(**kw):
    return buscar_noticias(config(**kw), agora=AGORA, baixar_fn=fake_baixar)


def test_busca_limpa_filtra_e_ordena():
    r = rodar()
    titulos = [n.titulo for n in r.noticias]
    # antiga e sem titulo descartadas; sem data vai pro fim
    assert titulos == ["Vale sobe na bolsa", "Petrobras anuncia & dividendos", "New AI chip", "Sem data"]

    petro = r.noticias[1]
    assert petro.resumo == 'A estatal aprovou o pagamento "extra".'
    assert petro.imagem == "https://s2.glbimg.com/foto.jpg"
    assert petro.publicado_em == datetime(2026, 10, 19, 13, 0, tzinfo=timezone.utc)

    chip = r.noticias[2]
    assert chip.link == "https://www.theverge.com/chip"
    assert chip.resumo == "A new chip."


def test_duplicada_vira_uma_com_varias_fontes():
    r = rodar()
    petro = [n for n in r.noticias if n.titulo.startswith("Petrobras")]
    assert len(petro) == 1
    assert petro[0].fontes == ["G1", "Folha"]
    assert petro[0].categorias == ["economia", "mercado"]


def test_status_dos_feeds_nao_quebra_com_erro():
    r = rodar()
    status = {s.fonte: s for s in r.status}
    assert status["Fora do ar"].status == "erro"
    assert "timed out" in status["Fora do ar"].erro
    assert status["Lixo"].status == "erro"
    assert status["G1"].status == "ok" and status["G1"].noticias == 2
    assert status["Folha"].noticias == 2  # conta a duplicada tambem
    assert r.status[0].status == "erro"  # erros aparecem primeiro


def test_janela_e_limite_por_feed():
    r = rodar(janela_horas=1)
    assert [n.titulo for n in r.noticias] == ["Vale sobe na bolsa", "Sem data"]
    r = rodar(max_por_feed=1)
    assert "Sem data" not in [n.titulo for n in r.noticias]


def test_helpers():
    assert limpar_texto("<p>Oi&nbsp;&amp; tchau</p>") == "Oi & tchau"
    assert cortar("a" * 10 + " " + "b" * 10, 15) == "a" * 10 + "…"
    assert chave_link("https://www.site.com/a/?utm_source=x&id=1#top") == "site.com/a?id=1"


def test_carrega_feeds_yaml_do_repo():
    cfg = carregar_config("feeds.yaml")
    assert len(cfg.feeds) > 10
    assert {f.categoria for f in cfg.feeds} >= {"brasil", "mundo", "economia", "mercado", "tecnologia"}
    assert all(f.url.startswith("https://") for f in cfg.feeds)


GOOGLE_NEWS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>site:wsj.com - Google News</title>
<item>
  <title>Dollar Could Underperform on AI Jitters - WSJ</title>
  <link>https://news.google.com/rss/articles/CBMiabc?oc=5</link>
  <pubDate>Sun, 19 Oct 2026 13:11:00 GMT</pubDate>
  <description>&lt;a href="https://news.google.com/rss/articles/CBMiabc?oc=5"&gt;Dollar Could Underperform on AI Jitters&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;WSJ&lt;/font&gt;</description>
  <source url="https://www.wsj.com">WSJ</source>
</item>
<item>
  <title>Hackathon de IA - Parte 2 - Valor Economico</title>
  <link>https://news.google.com/rss/articles/CBMixyz?oc=5</link>
  <pubDate>Sun, 19 Oct 2026 13:00:00 GMT</pubDate>
</item>
</channel></rss>"""

PATROCINADO = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Valor</title>
<item><title>Materia paga</title><link>https://valor.globo.com/patrocinado/dino/x.ghtml</link>
<pubDate>Sun, 19 Oct 2026 13:00:00 GMT</pubDate></item>
<item><title>Materia normal</title><link>https://valor.globo.com/empresas/y.ghtml</link>
<pubDate>Sun, 19 Oct 2026 13:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_google_news_limpa_titulo_e_resumo():
    FEEDS["https://gn/rss"] = GOOGLE_NEWS
    cfg = Config(feeds=[Feed("WSJ", "economia", "https://gn/rss")])
    r = buscar_noticias(cfg, agora=AGORA, baixar_fn=fake_baixar)
    assert [n.titulo for n in r.noticias] == ["Dollar Could Underperform on AI Jitters", "Hackathon de IA - Parte 2"]
    assert r.noticias[0].resumo == ""


def test_ignora_links_patrocinados():
    FEEDS["https://valor/rss"] = PATROCINADO
    cfg = Config(feeds=[Feed("Valor", "economia", "https://valor/rss")], ignorar_links_com=["/patrocinado/"])
    r = buscar_noticias(cfg, agora=AGORA, baixar_fn=fake_baixar)
    assert [n.titulo for n in r.noticias] == ["Materia normal"]


def test_google_news_so_aceita_fontes_permitidas():
    FEEDS["https://gn2/rss"] = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>GN</title>
<item><title>Ri Happy pede RE - Valor Investe</title><link>https://news.google.com/a</link>
<pubDate>Sun, 19 Oct 2026 13:00:00 GMT</pubDate><source url="https://valor.globo.com">Valor Investe</source></item>
<item><title>Ri Happy files - Stock Titan</title><link>https://news.google.com/b</link>
<pubDate>Sun, 19 Oct 2026 13:00:00 GMT</pubDate><source url="https://x.com">Stock Titan</source></item>
</channel></rss>"""
    cfg = Config(feeds=[Feed("Google News", "credito", "https://gn2/rss")],
                 google_news_fontes_permitidas=["Valor", "Reuters"])
    r = buscar_noticias(cfg, agora=AGORA, baixar_fn=fake_baixar)
    assert [(n.titulo, n.fonte) for n in r.noticias] == [("Ri Happy pede RE", "Valor Investe")]
    assert r.status[0].noticias == 1 and r.status[0].descartadas == 1
