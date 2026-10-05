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
