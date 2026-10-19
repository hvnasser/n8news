import json
from types import SimpleNamespace

import pytest

from n8news.busca import Noticia
from n8news.paises import carregar_paises, detectar, expandir_permitidos
from n8news.resumo import ConfigResumo, resumir_temas
from n8news.temas import carregar_temas, classificar
from n8news.texto import normalizar


def noticia(titulo, resumo="", categoria="economia"):
    return Noticia(titulo=titulo, link="https://x/" + titulo, resumo=resumo, fonte="X",
                   categoria=categoria, publicado_em=None, fontes=["X"], categorias=[categoria])


@pytest.fixture(scope="module")
def paises():
    return carregar_paises("paises.yaml")


@pytest.fixture(scope="module")
def credito():
    return next(t for t in carregar_temas("temas.yaml") if t.id == "credito")


@pytest.mark.parametrize("texto, esperado", [
    ("Ghana reaches debt restructuring deal", {"GHA"}),
    ("Lanka's debt restructuring 99% complete", {"LKA"}),
    ("French-German bond spread widens", {"FRA", "DEU"}),
    ("Risco-país do Brasil cai", {"BRA"}),
    ("Argentina paga cupom de bônus", {"ARG"}),
    ("Russell 2000 sobe", set()),
    ("Ri Happy pede recuperação extrajudicial", set()),
])
def test_detecta_paises(paises, texto, esperado):
    assert {p.codigo for p in detectar(paises, normalizar(texto))} == esperado


def test_grupos(paises):
    permitidos = expandir_permitidos(paises, ["g10", "em"])
    assert {"EUA", "GBR", "JPN", "BRA", "MEX", "CHN", "ARG"} <= permitidos
    assert not {"GHA", "LKA", "PAK", "EGY", "UKR"} & permitidos
    assert expandir_permitidos(paises, ["GHA"]) == {"GHA"}


def test_tema_tira_paises_fora_da_lista(credito, paises):
    noticias = [
        noticia("Ghana reaches debt restructuring deal with bondholders"),
        noticia("Lanka's debt restructuring 99% complete"),
        noticia("Argentina e FMI discutem reestruturação de dívida"),
        noticia("Ri Happy pede recuperação extrajudicial"),
        noticia("Pakistan and China agree debt restructuring"),  # China está na lista
    ]
    res = classificar(noticias, [credito], paises)[0]
    titulos = {m.noticia.titulo for m in res.noticias}
    assert titulos == {
        "Argentina e FMI discutem reestruturação de dívida",
        "Ri Happy pede recuperação extrajudicial",
        "Pakistan and China agree debt restructuring",
    }
    motivos = {n.titulo: m for n, m in res.excluidas}
    assert motivos["Ghana reaches debt restructuring deal with bondholders"] == "país fora da lista: GHA"


class FakeClient:
    """Imita client.beta.messages.create e guarda os parâmetros recebidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def resposta(itens, stop_reason="end_turn"):
    bloco = SimpleNamespace(type="text", text=json.dumps({"itens": itens}))
    return SimpleNamespace(stop_reason=stop_reason, content=[bloco])


def test_resumo_preenche_e_remove_irrelevantes(credito, paises):
    noticias = [
        noticia("Ri Happy pede recuperação extrajudicial", "A Ri Happy pediu RE para renegociar R$ 827 mi."),
        noticia("Empresa X pede recuperação judicial em tom de piada"),
    ]
    res = classificar(noticias, [credito], paises)
    client = FakeClient([resposta([
        {"id": 0, "resumo": "Ri Happy pede RE para renegociar R$ 827 milhões.", "relevante": True},
        {"id": 1, "resumo": "...", "relevante": False},
    ])])
    avisos = resumir_temas(res, ConfigResumo(), client)
    assert avisos == []
    assert [m.resumo_ia for m in res[0].noticias] == ["Ri Happy pede RE para renegociar R$ 827 milhões."]
    assert res[0].excluidas[-1][1] == "IA: fora do tema"

    chamada = client.chamadas[0]
    assert chamada["model"] == "claude-opus-5-5"
    assert chamada["fallbacks"] == "default"
    assert chamada["output_config"]["format"]["type"] == "json_schema"
    entrada = json.loads(chamada["messages"][0]["content"])
    assert entrada["tema"] == "Crédito"
    assert entrada["noticias"][0]["trecho"].startswith("A Ri Happy")


def test_resumo_recusa_e_erro_nao_quebram(credito, paises):
    import anthropic

    res = classificar([noticia("Ri Happy pede recuperação extrajudicial")], [credito], paises)
    client = FakeClient([resposta([], stop_reason="refusal")])
    avisos = resumir_temas(res, ConfigResumo(), client)
    assert "recusou" in avisos[0]
    assert res[0].noticias[0].resumo_ia == ""

    erro = anthropic.APIConnectionError(request=SimpleNamespace(url="x", method="POST"))
    avisos = resumir_temas(res, ConfigResumo(), FakeClient([erro]))
    assert "erro na API" in avisos[0]
    assert len(res[0].noticias) == 1


def test_lotes(credito, paises):
    noticias = [noticia(f"Empresa{i} Ltda pede recuperação judicial") for i in range(5)]
    res = classificar(noticias, [credito], paises)
    n = len(res[0].noticias)
    lotes = [resposta([{"id": i, "resumo": f"r{i}", "relevante": True} for i in range(k)])
             for k in (2, 2, 1)][: (n + 1) // 2]
    client = FakeClient(lotes)
    resumir_temas(res, ConfigResumo(max_por_chamada=2), client)
    assert len(client.chamadas) == (n + 1) // 2
    assert all(m.resumo_ia for m in res[0].noticias)


def test_resumo_desligado(credito):
    assert "desligado" in resumir_temas([], ConfigResumo(ativo=False))[0]


def test_sem_credencial_avisa(credito, paises):
    res = classificar([noticia("Ri Happy pede recuperação extrajudicial")], [credito], paises)
    avisos = resumir_temas(res, ConfigResumo(), FakeClient([TypeError("Could not resolve authentication method")]))
    assert "ANTHROPIC_API_KEY" in avisos[0]
    assert len(res[0].noticias) == 1
