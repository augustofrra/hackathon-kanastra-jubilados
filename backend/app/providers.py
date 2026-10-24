from __future__ import annotations

import json
import threading
import time
from typing import Protocol
from urllib.request import urlopen


class ProvedorSituacaoCadastral(Protocol):
    def consultar(self, documento: str) -> str | None: ...


class ProvedorSimulado:
    """Determinístico: documentos válidos são ATIVA; exceções configuráveis em JSON."""
    def __init__(self, situacoes: dict[str, str | None] | None = None):
        self.situacoes = situacoes or {}

    def consultar(self, documento: str) -> str | None:
        return self.situacoes.get(documento, 'ATIVA')


class ProvedorBrasilAPI:
    def __init__(self, timeout: float = 2, retries: int = 1, ttl: int = 3600):
        self.timeout, self.retries, self.ttl = timeout, retries, ttl
        self.cache: dict[str, tuple[float, str | None]] = {}
        self.lock = threading.Lock()

    def consultar(self, documento: str) -> str | None:
        with self.lock:
            cached = self.cache.get(documento)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        result = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(f'https://brasilapi.com.br/api/cnpj/v1/{documento}', timeout=self.timeout) as response:
                    payload = json.load(response)
                result = payload.get('descricao_situacao_cadastral', '').upper() or None
                break
            except (OSError, ValueError):
                if attempt < self.retries:
                    time.sleep(0.1)
        with self.lock:
            self.cache[documento] = (time.monotonic() + (self.ttl if result else 30), result)
        return result
