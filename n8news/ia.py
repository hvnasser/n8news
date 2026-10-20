"""Acesso aos modelos de IA.

Dois provedores, escolhidos em temas.yaml → ia.provedor:
- openrouter (padrão): qualquer modelo do OpenRouter (Claude, GPT, Gemini,
  DeepSeek...). Chave em OPENROUTER_API_KEY. Lista de modelos:
  https://openrouter.ai/models
- anthropic: direto na API da Anthropic. Chave em ANTHROPIC_API_KEY.

Os dois oferecem o mesmo método: `json(...)`, que pede uma resposta em JSON
seguindo um schema e devolve o dicionário já lido.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request


class ErroCredencial(Exception):
    """Chave ausente ou inválida: não adianta tentar de novo."""


class ErroIA(Exception):
    """Falha numa chamada (modelo inexistente, limite, resposta inválida...)."""


def ler_json(texto: str) -> dict:
    """Lê JSON mesmo se o modelo cercar com ```json ... ``` ou texto extra."""
    texto = (texto or "").strip()
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        inicio, fim = texto.find("{"), texto.rfind("}")
        if inicio >= 0 and fim > inicio:
            return json.loads(texto[inicio : fim + 1])
        raise


class OpenRouter:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, chave: str, timeout: float = 180, enviar=None):
        self.chave = chave
        self.timeout = timeout
        self._enviar = enviar or self._enviar_http

    @classmethod
    def do_ambiente(cls) -> "OpenRouter":
        chave = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not chave:
            raise ErroCredencial("OPENROUTER_API_KEY não configurada")
        return cls(chave)

    def _enviar_http(self, corpo: dict) -> tuple[int, dict]:
        req = urllib.request.Request(
            self.URL,
            data=json.dumps(corpo).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.chave}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/hvnasser/n8news",
                "X-Title": "n8news",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except json.JSONDecodeError:
                return e.code, {"error": {"message": f"HTTP {e.code}"}}

    def json(self, *, modelo: str, sistema: str, usuario: str, schema: dict, esforco: str | None = None) -> dict:
        corpo = {
            "model": modelo,
            "max_tokens": 16000,
            "messages": [
                {"role": "system", "content": sistema + "\n\nResponda apenas com o JSON pedido, sem texto antes ou depois."},
                {"role": "user", "content": usuario},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "resposta", "strict": True, "schema": schema},
            },
        }
        if esforco:
            corpo["reasoning"] = {"effort": esforco}

        status, dados = self._enviar(corpo)
        erro = (dados.get("error") or {}).get("message", "") if isinstance(dados, dict) else ""
        if status == 400 and re.search(r"response_format|json_schema|structured", erro, re.I):
            # Modelo sem suporte a saída estruturada: tenta só com a instrução no prompt
            corpo.pop("response_format")
            status, dados = self._enviar(corpo)
            erro = (dados.get("error") or {}).get("message", "") if isinstance(dados, dict) else ""

        if status in (401, 403):
            raise ErroCredencial(f"OpenRouter recusou a chave ({status}: {erro})")
        if status != 200 or erro:
            raise ErroIA(f"OpenRouter {status}: {erro or dados}")

        try:
            escolha = dados["choices"][0]
            return ler_json(escolha["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            motivo = (dados.get("choices") or [{}])[0].get("finish_reason")
            raise ErroIA(f"resposta inválida do modelo {modelo} (finish_reason={motivo})") from e


class Anthropic:
    """API direta da Anthropic (modelos com nomes como claude-opus-5-5)."""

    def __init__(self, client=None):
        import anthropic

        self._sdk = anthropic
        try:
            self.client = client or anthropic.Anthropic()
        except anthropic.AnthropicError as e:
            raise ErroCredencial(str(e)) from e

    def json(self, *, modelo: str, sistema: str, usuario: str, schema: dict, esforco: str | None = None) -> dict:
        sdk = self._sdk
        config = {"format": {"type": "json_schema", "schema": schema}}
        if esforco:
            config["effort"] = esforco
        try:
            resp = self.client.beta.messages.create(
                model=modelo,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config=config,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
            )
        except (sdk.AuthenticationError, TypeError) as e:
            # TypeError: o SDK não achou nenhuma credencial configurada
            raise ErroCredencial("ANTHROPIC_API_KEY ausente ou inválida") from e
        except sdk.APIError as e:
            raise ErroIA(f"{type(e).__name__}: {e}") from e
        if resp.stop_reason == "refusal":
            raise ErroIA("o modelo recusou o pedido")
        texto = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return ler_json(texto)
        except json.JSONDecodeError as e:
            raise ErroIA(f"resposta inválida (stop_reason={resp.stop_reason})") from e


def criar_cliente(provedor: str):
    provedor = (provedor or "openrouter").lower()
    if provedor == "openrouter":
        return OpenRouter.do_ambiente()
    if provedor == "anthropic":
        return Anthropic()
    raise ErroIA(f"provedor de IA desconhecido: {provedor} (use openrouter ou anthropic)")
