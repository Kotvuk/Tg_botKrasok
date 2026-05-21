import logging
from groq import AsyncGroq
from config import GROQ_API_KEYS, GROQ_MODEL, SITE_NAME, SITE_URL, AI_MAX_HISTORY

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = f"""Ты — специализированный консультант интернет-магазина «{SITE_NAME}» ({SITE_URL}).

Магазин находится в Казахстане и продаёт:
— Интерьерные краски (водоэмульсионные, акриловые, для детской, кухни, офисов)
— Краски по дереву (мебель, окна, полы, заборы)
— Краски по металлу (гладкие и молотковые)
— Фасадные краски
— Штукатурки и шпатлёвки
— Лаки и масла для дерева
— Грунтовки и антисептики
— Монтажные пены и герметики
— Малярные инструменты и аксессуары
— Бренды: Dulux, Hammerite, Masterline, Finncolor, Tikkurila и другие

Твои задачи:
1. Консультировать по выбору краски для конкретных поверхностей и условий
2. Помогать рассчитать количество материала (объяснять расход на м²)
3. Объяснять разницу между типами красок и их характеристиками
4. Давать советы по подготовке поверхностей и технологии нанесения
5. Рекомендовать товары из ассортимента магазина
6. Отвечать на вопросы о совместимости материалов

СТРОГИЕ ПРАВИЛА:
— Отвечай ТОЛЬКО на вопросы о красках, лаках, грунтовках, штукатурках, строительных материалах для отделки и товарах магазина {SITE_NAME}
— Если пользователь спрашивает о чём-либо постороннем — вежливо, но твёрдо объясни, что ты специализированный помощник только по теме лакокрасочных материалов
— Никогда не выходи за рамки тематики магазина, даже если пользователь настаивает
— Всегда рекомендуй проверить наличие и цену на сайте {SITE_URL}
— Отвечай только на русском языке
— Давай конкретные, практические советы

Формат ответа: понятно, структурированно, без лишней воды. Используй списки для перечислений."""


class GroqAssistant:
    def __init__(self) -> None:
        if not GROQ_API_KEYS:
            raise RuntimeError("Не задан ни один GROQ_API_KEY в .env файле!")
        # Создаём клиент для каждого ключа
        self._clients: list[AsyncGroq] = [AsyncGroq(api_key=k) for k in GROQ_API_KEYS]
        self._histories: dict[int, list[dict]] = {}
        logger.info(f"Groq: загружено {len(self._clients)} ключ(ей)")

    async def chat(self, user_id: int, message: str) -> str:
        history = self._histories.setdefault(user_id, [])
        history.append({"role": "user", "content": message})

        if len(history) > AI_MAX_HISTORY:
            history[:] = history[-AI_MAX_HISTORY:]

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        last_error = None

        for i, client in enumerate(self._clients):
            try:
                response = await client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    max_tokens=1024,
                    temperature=0.6,
                )
                reply: str = response.choices[0].message.content or "Нет ответа."
                history.append({"role": "assistant", "content": reply})
                if i > 0:
                    logger.info(f"Groq: сработал ключ #{i + 1}")
                return reply
            except Exception as exc:
                last_error = exc
                logger.warning(f"Groq ключ #{i + 1} не сработал: {exc}")

        # Все ключи исчерпаны
        history.pop()  # убираем последнее сообщение пользователя из истории
        return f"⚠️ ИИ временно недоступен. Попробуйте позже.\n<code>{last_error}</code>"

    def clear_history(self, user_id: int) -> None:
        self._histories.pop(user_id, None)
