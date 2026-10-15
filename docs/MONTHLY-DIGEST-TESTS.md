# Контракт месячного помощника

scripts/monthly_digest.py читает JSON на stdin и возвращает план без сети и создания задач. Пример синтетический:

```json
{"platform":"chatgpt","capabilities":{"persistent_scheduler":true,"web_search":true},"lookup_succeeded":true,"existing_tasks":[],"timezone":"Europe/Moscow","profile":{"role":"QA","topics":["API"],"formats":["online"],"languages":["ru"]}}
```

Новая установка → operation=create с нативными аргументами ChatGPT либо планом для фактического scheduler другой среды. Existing task — нормализованные id/title/prompt/enabled. Маркер v1 ищется во всех задачах, включая паузы; неоднозначный title без маркера требует сверки.

Для обновления только политики: refresh_prompt=true и сохранённые existing_tasks[].profile/timezone. Выход update_prompt содержит prompt и ID; schedule не передаётся, активность сохраняется. Языковой фильтр при миграции становится ru, остальные личные предпочтения сохраняются. Resume требует явного resume=true. Без прочитанного профиля/зоны — review_existing, а не сброс умолчаний.

Проверяются отсутствие дублей, отказ/пауза, ошибка чтения, session-only, отсутствие веба, индивидуальное время, DST/переход года, неизвестный город, минимальный публичный профиль, самостоятельный персональный промпт с 100 источниками/опросом/контактами. Фактическую подписку подтверждает только readback штатного инструмента после мутации; unit-тесты её не создают.
