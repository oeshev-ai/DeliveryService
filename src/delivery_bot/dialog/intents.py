"""Распознавание намерений: команды + keyword matching (без LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    """Поддерживаемые намерения клиента."""

    START = "start"
    HELP = "help"
    MENU = "menu"
    STATUS = "status"
    COURIER = "courier"
    CHANGE = "change"
    CANCEL = "cancel"
    FAQ = "faq"
    CLAIM = "claim"
    REVIEW = "review"
    REORDER = "reorder"
    OPERATOR = "operator"
    CONSENT_ACCEPT = "consent_accept"
    CONSENT_DECLINE = "consent_decline"
    CONTINUE = "continue"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class IntentMatch:
    """Результат распознавания намерения."""

    intent: Intent
    confidence: float
    source: str  # command | keyword | callback | unknown


# (intent, keywords) — порядок важен: более специфичные раньше
_KEYWORD_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.STATUS, ("статус", "где заказ", "отследить", "трек", "заказ номер")),
    (Intent.COURIER, ("курьер", "водитель", "где курьер", "трекинг")),
    (Intent.CHANGE, ("изменить", "сменить адрес", "другое время", "перенести")),
    (Intent.CANCEL, ("отмен", "отменить заказ", "не нужен")),
    (Intent.FAQ, ("вопрос", "faq", "зона доставки", "минимальная сумма", "оплата", "график")),
    (Intent.CLAIM, ("претензи", "жалоб", "рекламац", "проблема с заказом")),
    (Intent.REVIEW, ("отзыв", "оценк", "оставить отзыв")),
    (Intent.REORDER, ("повтор", "заказать снова", "из истории")),
    (Intent.OPERATOR, ("оператор", "человек", "поддержк", "менеджер")),
    (Intent.MENU, ("меню", "главное меню", "назад")),
    (Intent.HELP, ("помощ", "справка", "что умеешь")),
    (Intent.CONTINUE, ("продолжить", "продолжить диалог")),
]

_COMMAND_MAP: dict[str, Intent] = {
    "start": Intent.START,
    "help": Intent.HELP,
    "menu": Intent.MENU,
    "status": Intent.STATUS,
    "cancel": Intent.CANCEL,
    "faq": Intent.FAQ,
    "operator": Intent.OPERATOR,
}

_CALLBACK_MAP: dict[str, Intent] = {
    "consent:accept": Intent.CONSENT_ACCEPT,
    "consent:decline": Intent.CONSENT_DECLINE,
    "menu:main": Intent.MENU,
    "menu:status": Intent.STATUS,
    "menu:status_new": Intent.STATUS,
    "menu:courier": Intent.COURIER,
    "menu:change": Intent.CHANGE,
    "change:address": Intent.CHANGE,
    "change:time": Intent.CHANGE,
    "change:pay_confirm": Intent.CHANGE,
    "change:abort": Intent.CHANGE,
    "menu:cancel": Intent.CANCEL,
    "menu:faq": Intent.FAQ,
    "menu:claim": Intent.CLAIM,
    "menu:review": Intent.REVIEW,
    "menu:reorder": Intent.REORDER,
    "menu:operator": Intent.OPERATOR,
    "session:continue": Intent.CONTINUE,
}


class IntentMatcher:
    """Простой matcher: callback → команда → keywords."""

    def match_callback(self, data: str) -> IntentMatch:
        """Распознаёт callback_data кнопок."""
        intent = _CALLBACK_MAP.get(data)
        if intent is None:
            return IntentMatch(Intent.UNKNOWN, 0.0, "unknown")
        return IntentMatch(intent, 1.0, "callback")

    def match_command(self, command: str) -> IntentMatch:
        """Распознаёт slash-команду без ``/`` и аргументов."""
        name = command.lower().lstrip("/").split("@", 1)[0].split()[0]
        intent = _COMMAND_MAP.get(name)
        if intent is None:
            return IntentMatch(Intent.UNKNOWN, 0.0, "unknown")
        return IntentMatch(intent, 1.0, "command")

    def match_text(self, text: str) -> IntentMatch:
        """Keyword matching по нормализованному тексту."""
        normalized = _normalize(text)
        if not normalized:
            return IntentMatch(Intent.UNKNOWN, 0.0, "unknown")

        # точная команда без слэша
        if normalized in _COMMAND_MAP:
            return IntentMatch(_COMMAND_MAP[normalized], 0.95, "keyword")

        best: IntentMatch | None = None
        for intent, keywords in _KEYWORD_RULES:
            for kw in keywords:
                if _keyword_matches(normalized, kw):
                    confidence = min(0.9, 0.55 + 0.05 * len(kw.split()))
                    candidate = IntentMatch(intent, confidence, "keyword")
                    if best is None or candidate.confidence > best.confidence:
                        best = candidate
                    break

        return best or IntentMatch(Intent.UNKNOWN, 0.0, "unknown")

    def match_message(self, *, text: str | None = None, command: str | None = None) -> IntentMatch:
        """Унифицированный вход: сначала команда, затем текст."""
        if command:
            return self.match_command(command)
        if text:
            # /status как текст
            if text.startswith("/"):
                return self.match_command(text)
            return self.match_text(text)
        return IntentMatch(Intent.UNKNOWN, 0.0, "unknown")


def _keyword_matches(normalized: str, keyword: str) -> bool:
    """Точное вхождение фразы или наличие всех слов keyword в тексте."""
    if keyword in normalized:
        return True
    parts = keyword.split()
    if len(parts) <= 1:
        return False
    return all(part in normalized for part in parts)


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\sа-яё/+-]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text
