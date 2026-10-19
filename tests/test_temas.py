import pytest

from n8news.busca import Noticia
from n8news.temas import Filtro, Tema, carregar_temas, classificar, normalizar


def noticia(titulo, resumo="", categoria="economia"):
    return Noticia(titulo=titulo, link="https://x/" + titulo, resumo=resumo, fonte="X",
                   categoria=categoria, publicado_em=None, fontes=["X"], categorias=[categoria])


@pytest.fixture(scope="module")
def credito():
    return next(t for t in carregar_temas("temas.yaml") if t.id == "credito")


def filtros_que_casam(tema, titulo, resumo="", categoria="economia"):
    res = classificar([noticia(titulo, resumo, categoria)], [tema])[0]
    return res.noticias[0].filtros if res.noticias else []


@pytest.mark.parametrize("titulo, filtro", [
    ("Spreads de debêntures voltam a cair com forte demanda por crédito privado", "Spreads corporativos"),
    ("High-yield bond spreads widen as investors flee risk", "Spreads corporativos"),
    ("Private credit funds face redemptions", "Spreads corporativos"),
    ("Risco-país do Brasil cai ao menor nível do ano", "Spreads soberanos e risco-país"),
    ("CDS de 5 anos do Brasil recua", "Spreads soberanos e risco-país"),
    ("French OAT-Bund spread hits widest since 2012", "Spreads soberanos e risco-país"),
    ("Gilts sell off as UK borrowing costs jump", "Spreads soberanos e risco-país"),
    ("Moody's rebaixa nota de crédito da Colômbia", "Ratings"),
    ("Fitch downgrades France's credit rating to A+", "Ratings"),
    ("Pedidos de recuperação judicial no agro caem 20,7%, diz Serasa", "Recuperação judicial e extrajudicial"),
    ("Empresa X entra com pedido de recuperação judicial", "Recuperação judicial e extrajudicial"),
    ("Retailer files for Chapter 11 bankruptcy protection", "Default e calote"),
    ("Argentina deixou de pagar cupom de bônus", "Default e calote"),
    ("O que está por trás do pedido de falência da Character.AI?", "Default e calote"),
    ("Investors are pushing up the cost of insurance against an Oracle default", "Default e calote"),
    ("Companhia aérea fecha renegociação de dívidas com credores", "Renegociação e reestruturação de dívida"),
    ("Ghana reaches debt restructuring deal with bondholders", "Renegociação e reestruturação de dívida"),
])
def test_entra_no_tema(credito, titulo, filtro):
    assert filtro in filtros_que_casam(credito, titulo)


@pytest.mark.parametrize("titulo, categoria", [
    ("Virus spread accelerates in Europe", "mundo"),
    ("Bundestag approves new budget", "mundo"),
    ("iPhone gets a major upgrade", "economia"),
    ("Time é rebaixado para a série B", "brasil"),
    ("Serasa faz feirão para renegociar dívidas", "economia"),
    ("S&P 500 fecha em alta com balanços", "mercado"),
    ("Petrobras anuncia dividendos", "economia"),
    ("Empresa entra em recuperação judicial", "tecnologia"),  # categoria fora do tema
    ("CDS-PP apresenta voto de pesar", "mundo"),
    ("Olhar de frente para um ovo é arriscar a falência do entendimento", "brasil"),
    ("Mercado Livre chega a três mega CDs no Rio Grande do Sul", "credito"),
    ("Best high-yield savings interest rates today: Earn up to 4.3% APY", "credito"),
    ("5 High-Yield Stocks to Buy Now Before Your Retirement Starts", "credito"),
    ("EchoStar gains Speculative Buy rating on $20B deal", "credito"),
    ("Oil prices fall as traders weigh Russia sanctions waiver", "economia"),
])
def test_nao_entra_no_tema(credito, titulo, categoria):
    assert filtros_que_casam(credito, titulo, categoria=categoria) == []


def test_regras_das_palavras():
    assert normalizar("Risco-País") == " risco pais "
    f = Filtro("t", palavras=["renegoci*", "high yield", "default"])
    assert f.casa(normalizar("Renegociação aprovada"))
    assert f.casa(normalizar("high-yield bonds"))
    assert not f.casa(normalizar("company defaulted"))  # palavra inteira


def test_exige_e_filtro_desligado(tmp_path):
    f = Filtro("t", palavras=["spread"], exige=["bond"])
    assert not f.casa(normalizar("spread of the virus"))
    assert f.casa(normalizar("bond spread widens"))

    arq = tmp_path / "t.yaml"
    arq.write_text("""
temas:
  - id: a
    nome: A
    filtros:
      - { nome: ligado, palavras: [default] }
      - { nome: desligado, palavras: [calote], ativo: false }
  - id: b
    nome: B
    ativo: false
    filtros: [{ nome: x, palavras: [x] }]
""")
    temas = carregar_temas(arq)
    assert [t.id for t in temas] == ["a"]
    assert [f.nome for f in temas[0].filtros] == ["ligado"]


def test_excluidas_ficam_registradas():
    tema = Tema("c", "C", [Filtro("d", ["dívida*"])], excluir=["Serasa"])
    res = classificar([noticia("Serasa ajuda a renegociar dívidas")], [tema])[0]
    assert res.noticias == [] and res.excluidas[0][1] == "Serasa"


def test_agrupa_mesma_noticia_de_jornais_diferentes(credito):
    titulos = [
        ("Ri Happy solicita recuperação extrajudicial com dívida de R$ 827,4 milhões", "Folha de Curitiba"),
        ("Grupo Ri Happy entra com pedido de recuperação extrajudicial", "Estadão"),
        ("Ri Happy pede recuperação extrajudicial 48 dias após mudar de dono", "Exame"),
        ("Empresa Alfa entra com pedido de recuperação judicial", "Valor"),
        ("Beta entra com pedido de recuperação judicial", "Valor"),
        ("BoE scrutinises Barclays over claim traders misrepresented private credit exposure", "FT"),
        ("Bank of England probes Barclays over private credit loans - report", "Reuters"),
        ("BoE probes Barclays’ handling of private credit risks, FT reports", "Yahoo"),
        ("Localiza aprova emissão de R$ 1 bilhão em debêntures", "UOL"),
        ("Localiza (RENT3) capta R$ 1 bi em debêntures com vencimento em 24 meses", "Visno"),
        ("Valid aprova emissão de R$ 200 milhões em debêntures, com prazo de cinco anos", "ADVFN"),
    ]
    noticias = []
    for t, fonte in titulos:
        n = noticia(t)
        n.fontes = [fonte]
        noticias.append(n)
    noticias[1].resumo = "O grupo pediu..."  # a com resumo vira a principal
    res = classificar(noticias, [credito])[0]
    grupos = sorted(sorted([m.noticia.fontes[0]] + [r.fontes[0] for r in m.relacionadas]) for m in res.noticias)
    assert grupos == sorted([
        ["Estadão", "Exame", "Folha de Curitiba"],
        ["Valor"], ["Valor"],
        ["FT", "Reuters", "Yahoo"],
        ["UOL", "Visno"],
        ["ADVFN"],
    ])
    ri = next(m for m in res.noticias if "Happy" in m.noticia.titulo)
    assert ri.noticia.fontes == ["Estadão"]
