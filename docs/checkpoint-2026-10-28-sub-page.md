# Чекпоинт 28.10 — страница подписки «Штиль» + документация

## Страница подписки «Штиль» (sub-shtil)

### Проблема
У промо-подписки на 14 дней (клиент Panel id 30, `expiry_time=1794690000000`, до 15.11.2026 00:00 МСК) не было пути к покупке со страницы подписки — пользователь видел только приложения, QR-код и ссылки на конфигурации, но не ссылку на Telegram-бот @netrurunet_bot для покупки/продления.

### Что изменено

#### 1. Список приложений — только Happ
**Было:** 5 приложений (Happ, V2Box, V2RayNG, OneXray, V2ray VPN Client).
**Стало:** 1 приложение — Happ с deep-link `happ://add/<sub_url>` и тремя кнопками скачивания:
- App Store (iOS)
- Google Play (Android)
- **Новое:** Windows / macOS (happ.info) — ссылка на десктоп-версию

Файл шаблона: `/etc/3x-ui/sub_templates/sub-shtil/index.html` (строка 2479 → массив `const APPS`).
Исходник на S1: `/root/sub-shtil-build/page.html.tmpl` (строка 180).

#### 2. Кнопка «Купить / Продлить в Telegram»
Добавлена в карточку статуса после строки «Срок действия»:
```html
<a class="btn btn-primary" href="https://t.me/netrurunet_bot" target="_blank" rel="noopener">
  Купить / Продлить в Telegram → @netrurunet_bot
</a>
```
Для промо-пользователя это заметная кнопка прямо перед глазами. Для действующих клиентов — напоминание о боте.

#### 3. Футер «Поддержка» → бот
Заменён условный футер `{{ if .subSupportUrl }}...{{ end }}` (был пустой) на постоянную кнопку:
```html
<footer style="margin-top:16px">
  <a class="btn btn-sm" href="https://t.me/netrurunet_bot" target="_blank" rel="noopener">
    💬 Поддержка в Telegram → @netrurunet_bot
  </a>
</footer>
```

### Проверка
- Живая страница (`curl -skL -H "Accept: text/html"`): HTTP 200, 64233 байта, `netrurunet_bot` × 2, `name: 'Happ'`, `happ.info`, `Купить / Продлить`.
- Клиенты (без `Accept: text/html`): по-прежнему получают raw-конфигурацию, заголовки `Profile-Title`, `Subscription-Userinfo` (expire=1794690000), `Routing-Enable: true` — НЕ затронуты.
- x-ui active, порт 2096 слушает.
- Бэкап: `index.html.bak-20261028-promo` на Panel.

### Ссылки для выдачи промо
- Sub URL: `https://netru.ru.net:2096/wh0dstwjngxz86a1/6fmereq7vskvw0pp`
- Deep link: `happ://add/https://netru.ru.net:2096/wh0dstwjngxz86a1/6fmereq7vskvw0pp`
- Клиент: id 30, email `ekumqf26or`, comment «🎁 Пробный доступ», expiry_time=1794690000000 (15.11.2026 00:00 МСК), limit_ip=5

## Документация

### system-state.md
- Раздел 1 (Платежи): боевой магазин ShopID 1483176 подключён 27.10; чеки НПД выпущены автоматически (#1/#2 sent); напоминания о просроченных чеках работают.
- Раздел 3 (Бот): оплата ЮKassa в боевом режиме; статус family + безлимит (28.10); выпуск чеков НПД (27.10).
- Раздел 5 (Юридическое): РКН зарегистрировано (рег. номер 78-26-219239, приказ № 381 от 26.10.2026).
- Лог изменений: добавлены строки 27.10 (боевой запуск, РКН) и 28.10 (страница подписки).

### next-session-todo.md
- Раздел 2.1: Этапы 0–5 ВЫПОЛНЕНЫ; Этап 6 закрыт этой правкой.
- Раздел 3: п. 7 — промо-подписки (новая задача); нумерация исправлена (1..15).
- Раздел 4: РКН зарегистрирован; оферта п. 4.4 обновлена.

### session-start.md
- Раздел 5 (приоритеты): обновлён до 28.10.2026 — платежи запущены, РКН зарегистрирован, промо-подписки как отдельный пункт.

### overview.md
- Вступление: оплата ЮKassa в боевом режиме; страница «Штиль» обновлена 28.10.
- Риски п. 7: платежи — боевой магазин подключён, чеки автоматизированы.
- Оферта п. 4.4: обновлена и выложена.

## Файлы
- `/etc/3x-ui/sub_templates/sub-shtil/index.html` — живой шаблон (69717 байт, sha256 d2660249...)
- `/root/sub-shtil-build/page.html.tmpl` — исходник на S1 (12224 байта)
- `/root/sub-shtil-build/index.html` — собранный файл на S1 (sha256 совпадает)
- `/etc/3x-ui/sub_templates/sub-shtil/index.html.bak-20261028-promo` — бэкап
