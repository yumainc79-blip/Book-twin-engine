from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str


class LLMClient:
    def complete(self, prompt: str, model: str | None = None) -> LLMResponse:
        raise NotImplementedError


class NoLLMClient(LLMClient):
    def complete(self, prompt: str, model: str | None = None) -> LLMResponse:
        return LLMResponse(
            text=(
                "LLM non configurato. Ecco il contesto recuperato o il prompt da usare con un modello:\n\n"
                + prompt[:12000]
            )
        )


class OpenAICompatibleClient(LLMClient):
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY non impostata.")

    def complete(self, prompt: str, model: str | None = None) -> LLMResponse:
        payload = {
            "model": model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a rigorous, text-grounded book analysis assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        return LLMResponse(out["choices"][0]["message"]["content"])


class OllamaClient(LLMClient):
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")

    def complete(self, prompt: str, model: str | None = None) -> LLMResponse:
        payload = {
            "model": model or os.getenv("OLLAMA_MODEL") or "llama3.1",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        return LLMResponse(out.get("response", ""))


def get_client(provider: str) -> LLMClient:
    provider = provider.lower().strip()
    if provider in {"none", "no", "off"}:
        return NoLLMClient()
    if provider in {"openai", "openai-compatible", "compatible"}:
        return OpenAICompatibleClient()
    if provider == "ollama":
        return OllamaClient()
    raise ValueError(f"Provider LLM non supportato: {provider}")
