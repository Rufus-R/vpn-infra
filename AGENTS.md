# AGENTS.md — vpn-infra

## Сессии: точка входа

Точка входа сессии — `/root/vpn-infra/docs/session-start.md` (на сервере `myserver`).
Она содержит чеклист старта: что читать (`system-state.md`, `commercial/overview.md`,
`commercial/operations-log.md`, `next-session-todo.md`, `commercial/bot.md`, свежие
`docs/checkpoint-*.md`) и блок команд для выгрузки всего сразу.

Источник истины по открытым задачам — `docs/next-session-todo.md`.
Текущее состояние системы — `docs/system-state.md` (обновляется после каждой сессии).

## Подключение к серверу из окружения OpenHands

- Хост: `myserver` (alias) → `root@194.55.236.229`, ключ `~/.ssh_work/mykey`,
  конфиг `~/.ssh_work/config` (пути `~/.ssh` read-only в контейнере).
- Пример: `ssh -F ~/.ssh_work/config myserver '<команда>'`
- Клон репо в OpenHands: `/workspace/project` (origin = `myserver:/root/vpn-infra`).
- Push/pull: `GIT_SSH_COMMAND="ssh -F /home/openhands/.ssh_work/config" git pull`
- Проект на сервере: `/root/vpn-infra` (S1). Пушить туда напрямую нельзя — на S1
  создаётся отдельная рабочая ветка.

## Что это за проект

Монорепо VPN-инфраструктуры: домашний контур (S1, S2, OpenVPN, Pi-hole, OPNsense) и
коммерческий проект (S_RU + 3x-ui, Panel на `31.77.78.144` — мастер-панель, Telegram-бот,
лендинг). GitHub: `github.com/Rufus-R/vpn-infra` (приватный, Deploy Key).

Структура: `docs/` (мета-доки: session-start, system-state, next-session-todo,
diagnostic-commands, checkpoints по датам), `docs/home/` (домашний контур),
`docs/commercial/` (коммерческий проект), `docs/shared/` (общая сеть), `servers/`
(panel — бот/панель, s1, s2, sru), `secrets/` (git-crypt).

## Секреты

`secrets/` зашифрован git-crypt (ключ в менеджере паролей владельца). В клоне OpenHands
файлы остаются зашифрованными — не пытаться их читать/расшифровывать, не выводить
содержимое в чат. Не добавлять расшифрованные копии в git.

## Правила работы

- Ключевой паттерн предыдущих сессий: сессия = чекпоинт. По завершении работы создаётся
  `docs/checkpoint-YYYY-MM-DD-<тема>.md`, обновляются живые документы
  (`system-state.md`, `next-session-todo.md`, при необходимости `bot.md`,
  `operations-log.md`), всё коммитится.
- Диагностика серверов — read-only командами из `docs/diagnostic-commands.md`.
  Изменения на живых серверах — только по явному запросу оператора.
- `docs/commercial/tariffs.md` устарел (placeholder-цены); фактический источник тарифов —
  `servers/panel/bot/app/db/seed.py`.
- Источник приоритетов — `docs/next-session-todo.md`; краткая сводка — в
  `docs/session-start.md` раздел 5.

## Стиль

Документация и коммиты — на русском. Стиль коммитов: префикс области
(`docs:`, `bot:`, ...) + краткое описание по-русски.
