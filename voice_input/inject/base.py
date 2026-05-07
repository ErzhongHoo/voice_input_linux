from __future__ import annotations

from abc import ABC, abstractmethod
import logging


LOGGER = logging.getLogger(__name__)


class InjectionError(RuntimeError):
    pass


class TextInjectorBackend(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inject_text(self, text: str) -> None:
        raise NotImplementedError


class CompositeInjector(TextInjectorBackend):
    def __init__(self, candidates: list[TextInjectorBackend]) -> None:
        self.candidates = candidates
        self.name = " -> ".join(candidate.name for candidate in candidates)

    def is_available(self) -> bool:
        return any(candidate.is_available() for candidate in self.candidates)

    def inject_text(self, text: str) -> None:
        errors: list[str] = []
        for candidate in self.candidates:
            if not candidate.is_available():
                continue
            try:
                candidate.inject_text(text)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{candidate.name}: {exc}")
                LOGGER.warning("Text injector failed: %s: %s", candidate.name, exc)
                continue
            LOGGER.info("Text injected by backend: %s", candidate.name)
            return
        detail = "; ".join(errors) if errors else "没有可用文本输入 backend"
        raise InjectionError(detail)

