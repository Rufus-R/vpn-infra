# Telegram-бот — схема и сценарии

## Технологии

- Python, aiogram
- Режим: long polling (webhook не требуется, домен не нужен)
- БД: Postgres (общая с Marzban или отдельная — уточнить при реализации)

## Схема данных

```
users
├── id (PK)
├── tg_id (unique)
├── phone_number (nullable, unique когда указан)
├── username
├── referrer_id (FK -> users.id, nullable)
├── trial_used (bool, default false)
├── created_at

plans
├── id (PK)
├── name
├── duration_days
├── device_count
├── price

subscriptions
├── id (PK)
├── user_id (FK)
├── marzban_username        -- при device_count > 1: несколько строк, по одной на слот
├── device_slot (int)
├── plan_id (FK)
├── start_at
├── end_at
├── status (trial/active/expired)

payments
├── id (PK)
├── user_id (FK)
├── subscription_id (FK)
├── amount
├── provider (manual/yookassa)
├── provider_payment_id (nullable)
├── status (pending/confirmed/rejected)
├── created_at

referral_bonuses
├── id (PK)
├── referrer_id (FK -> users.id)
├── referred_id (FK -> users.id)
├── bonus_days
├── granted_at
```

## Сценарий: /start

1. Если новый пользователь — создать запись в users
2. Показать меню: Тарифы / Попробовать бесплатно (триал) / Мои подписки / Реферальная ссылка

## Сценарий: активация триала

1. Проверить users.trial_used по tg_id
2. Запросить номер телефона (request_contact)
3. Проверить phone_number на использование триала другим tg_id
4. Если всё чисто — создать subscription (7 дней, 1 устройство, status=trial)
5. Создать пользователя в Marzban через API
6. Выдать subscription-ссылку клиенту
7. users.trial_used = true

## Сценарий: покупка тарифа (ручное подтверждение)

1. Клиент выбирает тариф (срок + кол-во устройств)
2. Бот показывает реквизиты для оплаты
3. Клиент нажимает "Я оплатил" -> создаётся payments (status=pending)
4. Админу приходит уведомление с деталями (кто, что, сумма) и кнопками Подтвердить/Отклонить
5. Админ подтверждает -> payments.status=confirmed
6. Бот создаёт/продлевает subscription, создаёт N пользователей в Marzban (по device_count)
7. Если у пользователя есть referrer_id и это его ПЕРВАЯ оплата ->
   начислить бонус рефереру согласно таблице (см. tariffs.md)
8. Клиенту выдаётся subscription-ссылка(и)

## Сценарий: реферальная ссылка

Формат: https://t.me/<bot_username>?start=ref_<user_id>
При /start с параметром ref_XXX -> записать referrer_id при создании нового user
(если пользователь уже существует - не перезаписывать referrer_id)

## Интеграция с Marzban API

TODO после разворачивания панели:
- Endpoint создания пользователя
- Endpoint продления/изменения срока
- Endpoint получения subscription-ссылки
- Аутентификация API (токен/логин-пароль админа панели)
