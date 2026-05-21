import asyncio
import logging
from typing import Optional

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai_assistant import GroqAssistant
from config import BOT_TOKEN, SITE_NAME, SITE_URL
from keyboards import (
    ai_chat_kb,
    back_menu_kb,
    categories_kb,
    main_menu_kb,
    product_detail_kb,
    products_kb,
)
from scraper import get_categories, get_product_detail, get_products, search_products

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

ai = GroqAssistant()

# ─── Global cache ─────────────────────────────────────────────────────────────
_categories_cache: list[dict] = []


async def _load_categories() -> list[dict]:
    global _categories_cache
    if not _categories_cache:
        _categories_cache = await get_categories()
    return _categories_cache


# ─── Session helpers ──────────────────────────────────────────────────────────

def _save(ud: dict, **kw) -> None:
    ud.update(kw)


def _state(ud: dict) -> Optional[str]:
    return ud.get("state")


# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.clear()
    await update.message.reply_text(
        f"👋 Добро пожаловать в бот магазина <b>{SITE_NAME}</b>!\n\n"
        "Что умеет бот:\n"
        "📦 Просматривать каталог с фото и ценами\n"
        "🔍 Искать товары по названию или бренду\n"
        "🤖 Консультировать по выбору материалов через ИИ\n\n"
        f"🌐 Сайт: {SITE_URL}",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(),
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "ℹ️ <b>Команды</b>\n\n"
        "/start — запуск\n"
        "/menu — главное меню\n"
        "/catalog — каталог\n"
        "/search — поиск\n"
        "/ai — ИИ-консультант\n"
        "/help — справка\n\n"
        f"🌐 {SITE_URL}",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu_kb(),
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("state", None)
    await update.message.reply_text("🏠 Главное меню:", reply_markup=main_menu_kb())


# ─── Каталог ──────────────────────────────────────────────────────────────────

async def show_catalog(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    ctx.user_data.pop("state", None)
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()

    loading = await msg.reply_text("⏳ Загружаю категории…")
    categories = await _load_categories()
    await loading.delete()

    if not categories:
        await msg.reply_text(
            f"😔 Не удалось загрузить каталог.\n🌐 {SITE_URL}",
            reply_markup=back_menu_kb(),
        )
        return

    _save(ctx.user_data, categories=categories)
    await msg.reply_text(
        f"📦 <b>Каталог {SITE_NAME}</b>\n\nВыберите категорию:",
        parse_mode=ParseMode.HTML,
        reply_markup=categories_kb(categories),
    )


async def cb_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    cat_idx = int(q.data.split("_", 1)[1])

    categories = ctx.user_data.get("categories") or await _load_categories()
    if cat_idx >= len(categories):
        await q.message.reply_text("❌ Категория не найдена.", reply_markup=back_menu_kb())
        return

    category = categories[cat_idx]
    loading = await q.message.reply_text(f"⏳ Загружаю «{category['name']}»…")
    result = await get_products(category["url"], page=1)
    await loading.delete()

    products = result["products"]
    if not products:
        await q.message.reply_text(
            f"😔 В «{category['name']}» товары не найдены.\n{category['url']}",
            reply_markup=back_menu_kb(),
        )
        return

    _save(ctx.user_data, products=products, page=1,
          has_next=result["has_next"], cat_idx=cat_idx, categories=categories)

    await q.message.reply_text(
        f"🎨 <b>{category['name']}</b> — {len(products)} товаров\nВыберите:",
        parse_mode=ParseMode.HTML,
        reply_markup=products_kb(products, 1, result["has_next"], cat_idx),
    )


async def cb_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    _, cat_str, page_str = q.data.split("_", 2)
    cat_idx, page = int(cat_str), int(page_str)

    categories = ctx.user_data.get("categories") or await _load_categories()
    if cat_idx >= len(categories):
        return
    category = categories[cat_idx]

    loading = await q.message.reply_text(f"⏳ Страница {page}…")
    result = await get_products(category["url"], page=page)
    await loading.delete()

    products = result["products"]
    if not products:
        await q.message.reply_text("😔 Товары не найдены.", reply_markup=back_menu_kb())
        return

    _save(ctx.user_data, products=products, page=page,
          has_next=result["has_next"], cat_idx=cat_idx)

    await q.message.reply_text(
        f"🎨 <b>{category['name']}</b> — стр. {page}",
        parse_mode=ParseMode.HTML,
        reply_markup=products_kb(products, page, result["has_next"], cat_idx),
    )


async def cb_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer("⏳ Загружаю…")
    prod_idx = int(q.data.split("_", 1)[1])
    products = ctx.user_data.get("products", [])

    if prod_idx >= len(products):
        await q.message.reply_text("❌ Товар не найден.", reply_markup=back_menu_kb())
        return

    fallback = products[prod_idx]
    detail = await get_product_detail(fallback["url"]) or {
        **fallback, "properties": {}, "description": "", "brand": ""
    }

    lines = [f"🎨 <b>{detail['name']}</b>"]
    if detail.get("brand"):
        lines.append(f"🏷 Бренд: {detail['brand']}")
    lines.append(f"💰 Цена: <b>{detail['price']}</b>")
    if detail.get("description"):
        lines.append(f"\n📝 {detail['description'][:400]}")
    if detail.get("properties"):
        props = "\n".join(f"  • {k}: {v}" for k, v in list(detail["properties"].items())[:6])
        lines.append(f"\n📊 <b>Характеристики:</b>\n{props}")

    text = "\n".join(lines)
    kb = product_detail_kb(detail["url"])

    if detail.get("image"):
        try:
            await q.message.reply_photo(
                photo=detail["image"],
                caption=text[:1024],
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
            return
        except Exception:
            pass

    await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cb_go_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    ud = ctx.user_data
    products = ud.get("products", [])
    if not products:
        await q.message.reply_text("🏠 Главное меню:", reply_markup=main_menu_kb())
        return

    categories = ud.get("categories") or await _load_categories()
    cat_idx = ud.get("cat_idx", 0)
    cat_name = categories[cat_idx]["name"] if cat_idx < len(categories) else "Товары"

    await q.message.reply_text(
        f"🎨 <b>{cat_name}</b>\nВыберите товар:",
        parse_mode=ParseMode.HTML,
        reply_markup=products_kb(products, ud.get("page", 1), ud.get("has_next", False), cat_idx),
    )


# ─── Поиск ────────────────────────────────────────────────────────────────────

async def start_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    _save(ctx.user_data, state="searching")
    await msg.reply_text(
        "🔍 <b>Поиск товаров</b>\n\n"
        "Введите название товара или бренда:\n"
        "<i>Например: «Dulux», «краска для дерева», «молотковая»</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu_kb(),
    )


async def process_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.strip()
    ctx.user_data.pop("state", None)

    loading = await update.message.reply_text(f"🔍 Ищу: «{query}»…")
    products = await search_products(query)
    await loading.delete()

    if not products:
        await update.message.reply_text(
            f"😔 По запросу «{query}» ничего не найдено.",
            reply_markup=main_menu_kb(),
        )
        return

    _save(ctx.user_data, products=products, page=1, has_next=False, cat_idx=99)

    rows = []
    for i, p in enumerate(products):
        label = p["name"][:48] + "…" if len(p["name"]) > 48 else p["name"]
        rows.append([InlineKeyboardButton(f"🎨 {label}", callback_data=f"prod_{i}")])
    rows.append([InlineKeyboardButton("🔍 Новый поиск", callback_data="search"),
                 InlineKeyboardButton("🏠 Меню", callback_data="main_menu")])

    await update.message.reply_text(
        f"✅ Найдено {len(products)} товаров по запросу «{query}»:",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ─── ИИ-чат ───────────────────────────────────────────────────────────────────

async def start_ai_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message or update.callback_query.message
    if update.callback_query:
        await update.callback_query.answer()
    _save(ctx.user_data, state="ai_chat")
    await msg.reply_text(
        "🤖 <b>ИИ-консультант по краскам</b>\n\n"
        "Задайте вопрос о красках, лаках, грунтовках или малярных работах.\n\n"
        "<b>Примеры:</b>\n"
        "• Какую краску выбрать для детской комнаты?\n"
        "• Чем покрасить деревянный забор?\n"
        "• Сколько краски на 20 м²?\n"
        "• Разница между акриловой и алкидной?\n\n"
        "<i>Бот работает только по теме красок и стройматериалов.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ai_chat_kb(),
    )


async def process_ai_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text.strip()
    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    response = await ai.chat(update.effective_user.id, user_text)
    await update.message.reply_text(response, parse_mode=ParseMode.HTML, reply_markup=ai_chat_kb())


async def cb_clear_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer("История очищена!")
    ai.clear_history(update.effective_user.id)
    await update.callback_query.message.reply_text(
        "🗑 История диалога очищена. Начните новый разговор!",
        reply_markup=ai_chat_kb(),
    )


# ─── Контакты ─────────────────────────────────────────────────────────────────

async def cb_contacts(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        f"📞 <b>Контакты {SITE_NAME}</b>\n\n"
        f"🌐 Сайт: {SITE_URL}\n\n"
        "Специализируемся на красках, лаках, штукатурках\n"
        "и малярных инструментах в Казахстане.",
        parse_mode=ParseMode.HTML,
        reply_markup=back_menu_kb(),
    )


# ─── Главное меню ─────────────────────────────────────────────────────────────

async def cb_main_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.answer()
    ctx.user_data.pop("state", None)
    await update.callback_query.message.reply_text("🏠 Главное меню:", reply_markup=main_menu_kb())


# ─── Входящие сообщения ───────────────────────────────────────────────────────

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state = _state(ctx.user_data)
    if state == "searching":
        await process_search(update, ctx)
    elif state == "ai_chat":
        await process_ai_message(update, ctx)
    else:
        await update.message.reply_text(
            "🤔 Воспользуйтесь меню или введите /help.",
            reply_markup=main_menu_kb(),
        )


# ─── Запуск ───────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан! Заполните .env файл")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("catalog", show_catalog))
    app.add_handler(CommandHandler("search", start_search))
    app.add_handler(CommandHandler("ai", start_ai_chat))

    # Callbacks
    app.add_handler(CallbackQueryHandler(show_catalog,      pattern="^catalog$"))
    app.add_handler(CallbackQueryHandler(cb_main_menu,      pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(start_search,      pattern="^search$"))
    app.add_handler(CallbackQueryHandler(start_ai_chat,     pattern="^ai_chat$"))
    app.add_handler(CallbackQueryHandler(cb_contacts,       pattern="^contacts$"))
    app.add_handler(CallbackQueryHandler(cb_go_back,        pattern="^go_back$"))
    app.add_handler(CallbackQueryHandler(cb_clear_history,  pattern="^clear_history$"))
    app.add_handler(CallbackQueryHandler(cb_category,       pattern=r"^cat_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_page,           pattern=r"^page_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(cb_product,        pattern=r"^prod_\d+$"))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен. Ожидание сообщений…")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main()
