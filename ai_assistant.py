from groq import AsyncGroq
from config import GROQ_API_KEY, GROQ_MODEL, SITE_NAME, SITE_URL, AI_MAX_HISTORY

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
— Если пользователь спрашивает о чём-либо постороннем (политика, развлечения, технологии, кулинария, медицина, финансы и т.д.) — вежливо, но твёрдо объясни, что ты специализированный помощник только по теме лакокрасочных материалов
— Никогда не выходи за рамки тематики магазина, даже если пользователь настаивает
— Всегда рекомендуй проверить наличие и цену на сайте {SITE_URL}
— Отвечай только на русском языке
— Давай конкретные, практические советы

Формат ответа: понятно, структурированно, без лишней воды. Используй списки для перечислений."""


class GroqAssistant:
    def __init__(self) -> None:
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self._histories: dict[int, list[dict]] = {}

    async def chat(self, user_id: int, message: str) -> str:
        history = self._histories.setdefault(user_id, [])
        history.append({"role": "user", "content": message})

        # Keep context window manageable
        if len(history) > AI_MAX_HISTORY:
            history[:] = history[-AI_MAX_HISTORY:]

        try:
            response = await self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                max_tokens=1024,
                temperature=0.6,
            )
            reply: str = response.choices[0].message.content or "Нет ответа."
            history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as exc:
            return f"⚠️ Ошибка соединения с ИИ. Попробуйте ещё раз.\n<code>{exc}</code>"

    def clear_history(self, user_id: int) -> None:
        self._histories.pop(user_id, None)
