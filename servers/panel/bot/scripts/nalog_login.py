"""Одноразовый интерактивный вход в «Мой налог» по SMS.

См. docs/checkpoint-2026-10-17-payments.md, раздел 21.

Запуск на Panel интерпретатором из venv бота:
    /opt/netru-bot/venv/bin/python scripts/nalog_login.py /root/.secrets/nalog
Каталог состояния можно задать и переменной окружения NALOG_STATE_DIR.

В каталоге создаются (права каталога 700, файлов 600):
    device_id  - идентификатор устройства: создаётся один раз и дальше передаётся ботом;
    token.json - токены доступа (пишет библиотека nalogo).

Номер телефона и код вводятся в диалоге и в аргументы командной строки не попадают.
Код из SMS, токен вызова и токены доступа в вывод не попадают.
"""
import asyncio
import getpass
import json
import os
import re
import stat
import sys
from pathlib import Path

from nalogo.auth import generate_device_id
from nalogo.client import Client
from nalogo.exceptions import DomainException, NetworkException, UnauthorizedException

USAGE = "Использование: nalog_login.py <каталог состояния> (или переменная NALOG_STATE_DIR)"


def _mask(value, keep=2):
    text = str(value or "")
    if len(text) <= keep * 2:
        return "*" * len(text)
    return text[:keep] + "*" * (len(text) - keep * 2) + text[-keep:]


def _normalize_phone(raw):
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] == "8":
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if not re.fullmatch(r"7\d{10}", digits):
        raise ValueError("Ожидается номер из 11 цифр, например 79001234567")
    return digits


def _prepare_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def _read_or_create_device_id(state_dir):
    device_file = state_dir / "device_id"
    if device_file.exists():
        value = device_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = generate_device_id()
    fd = os.open(device_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    os.chmod(device_file, 0o600)
    return value


def _prepare_token_file(state_dir):
    token_file = state_dir / "token.json"
    if not token_file.exists():
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("{}")
    os.chmod(token_file, 0o600)
    return token_file


def _read_token_data(token_file):
    try:
        with token_file.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _fail(stage, exc):
    print(f"Ошибка на шаге «{stage}»: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
    return 1


async def _login(state_dir):
    device_id = _read_or_create_device_id(state_dir)
    token_file = _prepare_token_file(state_dir)

    if _read_token_data(token_file):
        answer = input("Токен уже есть. Войти заново и заменить его? [y/N]: ").strip().lower()
        if answer != "y":
            print("Отменено, токен не изменён.")
            return 0

    try:
        phone = _normalize_phone(input("Номер телефона из «Мой налог» (11 цифр): "))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    async with Client(storage_path=str(token_file), device_id=device_id) as client:
        stage = "запрос кода"
        try:
            challenge = await client.create_phone_challenge(phone)
            challenge_token = challenge.get("challengeToken")
            if not challenge_token:
                print("Ответ на запрос кода без challengeToken.", file=sys.stderr)
                return 1
            print("Код отправлен по SMS.")
            code = getpass.getpass("Код из SMS: ").strip()
            stage = "подтверждение кода"
            await client.create_new_access_token_by_phone(phone, challenge_token, code)
            stage = "проверка профиля"
            profile = await client.user().get()
        except UnauthorizedException as exc:
            return _fail(stage + " (отказ)", exc)
        except NetworkException as exc:
            return _fail(stage + " (сеть)", exc)
        except DomainException as exc:
            return _fail(stage, exc)

    data = _read_token_data(token_file)
    print("Вход выполнен.")
    print(f"  статус: {profile.get('status')}")
    print(f"  ИНН: {_mask(profile.get('inn'))}")
    print(f"  телефон: {_mask(profile.get('phone'))}")
    print(f"  ключи token.json: {', '.join(sorted(data)) or 'файл пуст'}")
    print(f"  права token.json: {oct(stat.S_IMODE(token_file.stat().st_mode))}")
    print(f"  права каталога: {oct(stat.S_IMODE(state_dir.stat().st_mode))}")
    return 0 if data else 1


def main():
    os.umask(0o077)
    arg = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("NALOG_STATE_DIR")
    if not arg or arg.startswith("-"):
        print(USAGE, file=sys.stderr)
        return 2
    state_dir = Path(arg)
    _prepare_dir(state_dir)
    return asyncio.run(_login(state_dir))


if __name__ == "__main__":
    sys.exit(main())
