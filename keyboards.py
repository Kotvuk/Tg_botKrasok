from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Каталог товаров", callback_data="catalog"),
         InlineKeyboardButton("🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton("🤖 ИИ-консультант", callback_data="ai_chat")],
        [InlineKeyboardButton("📞 Контакты", callback_data="contacts")],
    ])


def categories_kb(categories: list) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(cat["name"], callback_data=f"cat_{i}")]
            for i, cat in enumerate(categories)]
    rows.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def products_kb(products: list, page: int, has_next: bool, cat_idx: int) -> InlineKeyboardMarkup:
    rows = []
    for i, p in enumerate(products):
        label = p["name"][:48] + "…" if len(p["name"]) > 48 else p["name"]
        rows.append([InlineKeyboardButton(f"🎨 {label}", callback_data=f"prod_{i}")])

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️ Пред.", callback_data=f"page_{cat_idx}_{page - 1}"))
    if has_next:
        nav.append(InlineKeyboardButton("След. ▶️", callback_data=f"page_{cat_idx}_{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton("🔙 Категории", callback_data="catalog"),
        InlineKeyboardButton("🏠 Меню", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(rows)


def product_detail_kb(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Купить на сайте", url=url)],
        [InlineKeyboardButton("🔙 К товарам", callback_data="go_back")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ])


def ai_chat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Очистить историю", callback_data="clear_history")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
    ])


def back_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
