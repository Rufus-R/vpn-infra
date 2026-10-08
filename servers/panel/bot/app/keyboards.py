from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Попробовать бесплатно", callback_data="menu:trial")],
        [InlineKeyboardButton(text="💳 Тарифы", callback_data="menu:tariffs")],
        [InlineKeyboardButton(text="📱 Мои подписки", callback_data="menu:subs")],
        [InlineKeyboardButton(text="👥 Реферальная ссылка", callback_data="menu:ref")],
    ])
