from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="menu:trial")],
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="menu:tariffs")],
        [InlineKeyboardButton(text="📱 Мои подписки", callback_data="menu:subs")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="menu:ref")],
    ])


def tariffs_menu(plans) -> InlineKeyboardMarkup:
    rows = []
    for plan in plans:
        price_rub = plan.price // 100
        rows.append([InlineKeyboardButton(
            text=f"{plan.name} — {price_rub} ₽",
            callback_data=f"plan:detail:{plan.id}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"plan:paid:{plan_id}")],
        [InlineKeyboardButton(text="⬅️ К тарифам", callback_data="menu:tariffs")],
    ])


def admin_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:confirm:{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{payment_id}"),
        ],
    ])
