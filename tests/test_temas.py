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
    ("Empresa X entra com pedido de recuperação judicial", "Recuperação judicial e extrajudicial"),
    ("Retailer files for Chapter 11 bankruptcy protection", "Default e calote"),
    ("Argentina deixou de pagar cupom de bônus", "Default e calote"),
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
