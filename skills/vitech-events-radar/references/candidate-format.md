# JSON-карточка (необязательная машинная проверка)

Синтетический пример схемы, не рекомендация:

```json
{
  "id": "cfp-1",
  "kind": "cfp",
  "name": "Синтетическая конференция",
  "starts_at": "2027-02-01T10:00:00+03:00",
  "checked_at": "2026-10-16T09:00:00+03:00",
  "url": "https://example.org/cfp",
  "primary_url": "https://example.org/conference",
  "topics": ["Go"],
  "audience": "backend",
  "format": "offline",
  "accessible": true,
  "primary_verified": true,
  "free_for_attendee": false,
  "free_for_speaker": true,
  "language": "ru",
  "russian_community": true,
  "cfp_status": "open",
  "deadline": "2026-11-01T23:59:00+03:00",
  "evidence": {
    "date": "Дата текущего выпуска на официальной странице",
    "status": "Действующая форма подачи доклада прочитана",
    "speaker_price": "Условия подтверждают бесплатное участие принятого спикера",
    "attendee_price": "Билеты слушателей платные",
    "language": "Подтверждён русский язык докладов",
    "community": "Российское техническое сообщество",
    "section": "Секция Go подходит профилю backend-разработчика",
    "deadline": "Дедлайн указан в условиях подачи"
  }
}
```

| kind | Дополнительные условия |
|---|---|
| `event` | Посещение в окне `--days` (30); `free_for_attendee=true`, `evidence.attendee_price`, `registration=open/not_required` |
| `cfp` | Выступление в окне `--months` (6); `free_for_speaker=true`, `evidence.speaker_price/section/deadline`, открытый CFP и будущий дедлайн до события |
| `speaker` | Уточнение выступления в том же шестимесячном окне; цена спикеру и секция как у CFP, но вместо дедлайна `speaker_route`, `speaker_url`, `evidence.speaker_route` |

Для `speaker_route` допустимы `speaker_page` (официальная страница спикерам) или `external_talks` (текущий официальный маршрут внешних докладов). Требуется публичный HTTPS `speaker_url`; `cfp_status=unknown/not_announced`. Закрытый приём или `program_final=true` исключают условное выступление. Для `event` эти же поля плюс бесплатность спикеру/секция позволяют включить карточку в опрос; одна регистрация слушателя — нет.

Для `cfp/speaker/speaker_inquiry` `free_for_attendee` может быть true/false/null; при известной цене требуется `attendee_price`, при null явно покажи «цена слушателю не подтверждена». Старое общее поле `free` больше не подтверждает цену ни одной роли. Условия цены — в quality-rules.md.

Порядок всех карточек совпадает с общей выдачей: помощник сохраняет исходные номера, даже если часть карточек годится только для посещения. ID уникальны, одна площадка не дублируется.

Вызов: `python3 scripts/check_candidates.py карточки.json --now ISO8601 --days 30 --months 6`. Поля заполняй по прочитанным источникам; валидатор проверяет согласованность JSON, а не истину в вебе. Журнал аудитора — отдельный необязательный контракт.

Для speaker_contact.py передай `{"conferences":[карточки],"selection":{"conference_id":"cfp-1","topic_state":"no_idea"}}`. topic_state — has_idea/no_idea; необязательная публичная topic требует реальной проверки секций/правил, затем topic_fit=confirmed и краткую topic_fit_evidence. mismatch/unknown требуют уточнения. Скрипт сам эти правила в вебе не читает.

При явно заданном другом периоде передай одинаковые --days/--months в валидатор и speaker_contact.py; их умолчания — 30/6.

## Предварительная площадка и нулевой результат

`kind=speaker_inquiry` — проверенный будущий выпуск в шестимесячном окне, язык ru, российское сообщество, лично подходящая секция и официальный контакт. Общие поля как выше. `organizer_contact_url` — HTTPS-страница программы/участия с проверенным контактом; `evidence.speaker_contact` описывает контакт и назначение. `cfp_status=unknown/not_announced/open`; при open требуется будущий deadline и evidence.deadline. `free_for_speaker=null` допустим, true требует evidence.speaker_price, false исключает карточку. `program_final=true` или `external_talks=false` исключают её. Не создавать такой kind автоматическим переименованием отклонённого CFP; сведения об отказе/дедлайне сохранять. Обычная регистрация не доказывает наличие контакта по выступлениям.

Статус в выдаче и опросе: «Нужно уточнить возможность и условия выступления». Неизвестную цену спикеру и неизвестный приём обозначать явно. Это запрос условий, не подтверждение бесплатного выступления. Для темы допустим topic_fit=unknown или отсутствие поля с честным уточнением в обращении; mismatch требует адаптации. Для подтверждённых cfp/speaker требования topic_fit=confirmed и evidence прежние.

Если пригодных площадок нет, survey всё равно возвращает два вопроса: помощь с поиском (help_find/skip), идея (has_idea/no_idea). Compose принимает conference_id=help_find только при отсутствии пригодных карточек; текст просит Олега подобрать площадку, не содержит вымышленного события. Непригодный ID по-прежнему отклоняется.
