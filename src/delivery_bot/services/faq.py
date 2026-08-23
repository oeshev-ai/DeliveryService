"""Сценарий FAQ в Telegram-боте."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from delivery_bot.dialog.keyboards import main_menu_keyboard, operator_offer_keyboard
from delivery_bot.dialog.manager import DialogResponse
from delivery_bot.dialog.session import DialogSession
from delivery_bot.dialog.states import DialogState
from delivery_bot.integrations.faq.client import FaqClient, FaqError
from delivery_bot.integrations.faq.schemas import FaqArticleDTO, FaqAskResponse
from delivery_bot.logging_setup import get_logger

logger = get_logger(__name__)


def _topics_keyboard(articles: list[FaqArticleDTO]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for article in articles[:8]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=article.title[:40],
                    callback_data=f"faq:article:{article.id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _after_answer_keyboard(
    *,
    suggestions: list[FaqArticleDTO],
    escalate: bool,
    active_order_id: str | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for article in suggestions[:3]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📄 {article.title[:36]}",
                    callback_data=f"faq:article:{article.id}",
                )
            ]
        )
    if escalate:
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 Связаться с оператором",
                    callback_data="menu:operator",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="❓ Другой вопрос",
                callback_data="faq:again",
            )
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class FaqService:
    """Диалог FAQ: темы + свободный вопрос."""

    def __init__(self, faq: FaqClient) -> None:
        self._faq = faq

    async def start(
        self,
        session: DialogSession,
        *,
        query: str | None = None,
    ) -> DialogResponse:
        if query and len(query.strip()) >= 2:
            return await self.ask(session, query)

        session.state = DialogState.FAQ
        try:
            articles = await self._faq.list_articles()
        except FaqError:
            return DialogResponse(
                text="FAQ временно недоступен. Попробуйте позже или «оператор».",
                reply_markup=operator_offer_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )

        return DialogResponse(
            text=(
                "❓ <b>Частые вопросы</b>\n\n"
                "Выберите тему или напишите вопрос своими словами.\n"
                "Примеры: «зона доставки», «минимальная сумма», «как отменить»."
            ),
            reply_markup=_topics_keyboard(articles),
        )

    async def handle_callback(
        self, session: DialogSession, data: str
    ) -> DialogResponse:
        if data == "faq:again":
            return await self.start(session)
        if data.startswith("faq:article:"):
            article_id = int(data.split(":")[-1])
            return await self.show_article(session, article_id)
        return DialogResponse(text="Неизвестное действие FAQ.")

    async def handle_input(
        self, session: DialogSession, text: str
    ) -> DialogResponse:
        return await self.ask(session, text)

    async def ask(self, session: DialogSession, question: str) -> DialogResponse:
        session.state = DialogState.FAQ
        try:
            result = await self._faq.ask(question)
        except FaqError:
            return DialogResponse(
                text="Не удалось получить ответ FAQ. Попробуйте позже.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        return self._format_ask(session, result)

    async def show_article(
        self, session: DialogSession, article_id: int
    ) -> DialogResponse:
        session.state = DialogState.FAQ
        try:
            article = await self._faq.get_article(article_id)
        except FaqError:
            return DialogResponse(
                text="FAQ недоступен.",
                reply_markup=main_menu_keyboard(
                    active_order_id=session.context.get("verified_order_id")
                ),
            )
        if article is None:
            return DialogResponse(
                text="Статья не найдена.",
                reply_markup=await self._safe_topics(session),
            )
        return DialogResponse(
            text=f"<b>{article.title}</b>\n\n{article.answer}",
            reply_markup=_after_answer_keyboard(
                suggestions=[],
                escalate=False,
                active_order_id=session.context.get("verified_order_id"),
            ),
        )

    def _format_ask(
        self, session: DialogSession, result: FaqAskResponse
    ) -> DialogResponse:
        active = session.context.get("verified_order_id")
        header = ""
        if result.source == "llm":
            header = "💡 Ответ (по базе знаний):\n\n"
        elif result.source == "keyword" and result.ok:
            header = "📘 Из базы знаний:\n\n"

        text = header + result.answer
        if result.escalate and result.ok:
            text += (
                "\n\nЕсли ответ неполный — выберите другую тему "
                "или свяжитесь с оператором."
            )

        return DialogResponse(
            text=text,
            reply_markup=_after_answer_keyboard(
                suggestions=result.suggestions,
                escalate=result.escalate,
                active_order_id=str(active) if active else None,
            ),
        )

    async def _safe_topics(self, session: DialogSession) -> InlineKeyboardMarkup:
        try:
            articles = await self._faq.list_articles()
            return _topics_keyboard(articles)
        except FaqError:
            return main_menu_keyboard(
                active_order_id=session.context.get("verified_order_id")
            )
