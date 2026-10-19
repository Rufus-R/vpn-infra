from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def consent_keyboard() -> InlineKeyboardMarkup:
    """Экран согласия на обработку ПДн — показывается до главного меню,
    см. app/handlers/start.py, require_consent()."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я согласен", callback_data="consent:accept")],
        [InlineKeyboardButton(
            text="📄 Политика конфиденциальности",
            url="https://netru.ru.net/privacy",
        )],
    ])


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="menu:trial")],
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="menu:tariffs")],
        [InlineKeyboardButton(text="📱 Мои подписки", callback_data="menu:subs")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="menu:ref")],
        [InlineKeyboardButton(text="📞 Поддержка", callback_data="menu:support")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛠 Админ", callback_data="adm:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    # Текст изменён 11.10.2026 (было «✅ Я оплатил») — кнопка больше не ведёт к
    # ручному fallback-подтверждению, см. app/handlers/tariffs.py, cb_plan_order().
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оформить заказ", callback_data=f"plan:paid:{plan_id}")],
        [InlineKeyboardButton(text="⬅️ К тарифам", callback_data="menu:tariffs")],
    ])


def pay_keyboard(url: str) -> InlineKeyboardMarkup:
    """Кнопка со ссылкой на оплату ЮKassa — см. app/handlers/tariffs.py, cb_plan_order()."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=url)],
        [InlineKeyboardButton(text="⬅️ К тарифам", callback_data="menu:tariffs")],
    ])


def admin_payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    # 11.10.2026: не вызывается из текущего кода (fallback отключён), оставлена
    # для переиспользования после интеграции ЮKassa — см. tariffs.py, cb_admin_confirm.
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin:confirm:{payment_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin:reject:{payment_id}"),
        ],
    ])


def subscriptions_keyboard(links: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Раздел «Мои подписки» — URL-кнопка на каждую активную подписку (если удалось
    получить subId), плюс «Назад» в любом случае."""
    rows = [[InlineKeyboardButton(text=f"🔗 Открыть: {name}", url=url)] for name, url in links]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню администратора, см. app/handlers/admin.py (доступ — только ADMIN_IDS)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats")],
        [InlineKeyboardButton(text="💳 Последние платежи", callback_data="adm:payments")],
        [InlineKeyboardButton(text="🧾 Чеки к выдаче", callback_data="adm:receipts")],
        [InlineKeyboardButton(text="📩 Обращения", callback_data="adm:support")],
        [InlineKeyboardButton(text="🩺 Проверка Panel", callback_data="adm:panel")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="menu:back")],
    ])


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Админ-меню", callback_data="adm:menu")],
    ])
