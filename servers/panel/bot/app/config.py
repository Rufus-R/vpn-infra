"""Конфигурация бота. Секреты читаются из .env (git-crypt) и/или отдельных файлов на Panel."""
import os
from pathlib import Path
from dotenv import load_dotenv

ENV_FILE = os.environ.get("BOT_ENV_FILE")
if ENV_FILE:
    load_dotenv(ENV_FILE)
else:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Переменная окружения {name} не задана (см. .env.example)")
    return value


BOT_TOKEN = _require("BOT_TOKEN")

# Прокси для long polling (Telegram заблокирован с IP Panel напрямую,
# см. docs/system-state.md п.17). Бот ходит в тот же socks5-инбаунд tg-proxy на S2,
# что и встроенный бот панели (независимо от panelOutbound самого x-ui).
TG_PROXY_URL = os.environ.get("TG_PROXY_URL")

# БД бота (SQLite, отдельная от x-ui.db на Panel — см. docs/commercial/bot.md)
DB_PATH = os.environ.get("DB_PATH", "bot.db")

# API мастер-панели 3x-ui. Бот работает на том же сервере — обращается к localhost,
# не через прокси и не через внешнюю сеть.
PANEL_API_BASE = _require("PANEL_API_BASE")

# Токен можно передать напрямую (PANEL_API_TOKEN) либо указать файл с ним
# (PANEL_API_TOKEN_FILE) — второй вариант не дублирует значение в репозитории.
_token_file = os.environ.get("PANEL_API_TOKEN_FILE")
if _token_file:
    PANEL_API_TOKEN = Path(_token_file).read_text().strip()
else:
    PANEL_API_TOKEN = _require("PANEL_API_TOKEN")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]

# Сертификат Panel выписан на netru.ru.net, не на 127.0.0.1 — при обращении по IP
# hostname verification не пройдёт. Риска MITM нет (трафик не покидает loopback),
# поэтому по умолчанию проверка имени отключена для локального вызова.
PANEL_API_VERIFY_TLS = os.environ.get("PANEL_API_VERIFY_TLS", "true").lower() == "true"

# ID инбаунда reality-entry на S_RU, КАК ЕГО ВИДИТ МАСТЕР-ПАНЕЛЬ (не обязательно совпадает
# с локальным ID на самом S_RU) — используется при создании клиентов (add_client).
# Узнать: sqlite3 /etc/x-ui/x-ui.db "SELECT id, remark, tag FROM inbounds;" на Panel.
_reality_inbound_id_raw = os.environ.get("REALITY_INBOUND_ID")
REALITY_INBOUND_ID = int(_reality_inbound_id_raw) if _reality_inbound_id_raw else None

# Базовый URL страницы подписки Panel (домен+порт+секретный subPath), БЕЗ subId в конце.
# Полная ссылка клиенту = SUB_BASE_URL + subId. Путь secret — хранить только в
# secrets/panel-bot.env, не коммитить в .env.example. Узнать актуальное значение:
# sqlite3 /etc/x-ui/x-ui.db "SELECT key,value FROM settings WHERE key IN
# ('subDomain','subPort','subPath');" на Panel.
SUB_BASE_URL = os.environ.get("SUB_BASE_URL")


# Текст с реквизитами для fallback-оплаты (ручное подтверждение), показывается в
# карточке тарифа. Не хардкод — задаётся в .env, можно менять без деплоя кода.
PAYMENT_REQUISITES_TEXT = os.environ.get(
    "PAYMENT_REQUISITES_TEXT",
    "Реквизиты для оплаты временно не заданы — обратитесь к администратору через "
    "раздел «Поддержка».",
)

# ЮKassa (см. docs/checkpoint-2026-10-17-payments.md, раздел 10). Все значения необязательны
# при импорте: пока они не заданы, платежи не включены (YooKassaClient при создании
# сообщает об этом явной ошибкой), а бот остальными разделами работает как раньше.
# Секретный ключ в .env не кладём — только путь к файлу (права 600, вне git).
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY_FILE = os.environ.get("YOOKASSA_SECRET_KEY_FILE")
# Секретный сегмент пути вебхука: /yookassa-webhook/<секрет>/ (nginx -> 127.0.0.1:WEBHOOK_PORT).
YOOKASSA_WEBHOOK_SECRET = os.environ.get("YOOKASSA_WEBHOOK_SECRET")
# Куда ЮKassa возвращает пользователя после оплаты (ссылка на бота).
YOOKASSA_RETURN_URL = os.environ.get("YOOKASSA_RETURN_URL")
# Локальный порт aiohttp-сервера вебхука в процессе бота (8711 свободен, проверено 18.10.2026).
WEBHOOK_PORT = int(os.environ.get("WEBHOOK_PORT", "8711"))

# Чеки через «Мой налог» (см. docs/checkpoint-2026-10-17-payments.md, разделы 19–21).
# Необязательно при импорте: пока не задано, выпуск чеков не включён, остальные разделы бота
# работают как раньше. Каталог содержит token.json и device_id (создаются скриптом
# scripts/nalog_login.py; права каталога 700, файлов 600; вне git).
NALOG_STATE_DIR = os.environ.get("NALOG_STATE_DIR")
# Выпуск чеков из бота (патч №3): выключен по умолчанию, включается после запуска боевого
# магазина ЮKassa, чтобы тестовый платёж не стал настоящим доходом в «Мой налог».
NALOG_ISSUE_ENABLED = os.environ.get("NALOG_ISSUE_ENABLED", "").strip().lower() in ("1", "true", "yes")
