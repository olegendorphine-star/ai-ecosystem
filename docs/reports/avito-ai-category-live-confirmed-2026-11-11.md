# Проверка категории ИИ Авито — 11.11.2026

## Источник и статус

Два отдельных успешных ручных read-only запуска на main, после слияния PR #181:

- https://github.com/olegendorphine-star/ai-ecosystem/actions/runs/43054914837
- https://github.com/olegendorphine-star/ai-ecosystem/actions/runs/43054955645

Оба журнала `live_readonly` содержат:

```json
{
  "oauth_http": 200,
  "oauth_ok": true,
  "ai_category_selected": true,
  "ai_category_fields_verified": true,
  "category_leaf_discovered": true,
  "category_fields_http": 200,
  "category_fields_observed": ["AdStatus", "Address", "Description", "Images", "ListingFee", "Price", "PriceList", "Title"],
  "pricelist_observed_in_fields": true,
  "autoload_enabled": true,
  "items": {"active_items_first_page_count": 4, "moscow_active": true, "petersburg_active_first_page": true},
  "writes": 0,
  "charges_rub": 0,
  "messages_read": 0,
  "messages_sent": 0
}
```

## Что доказано

- Выбранная программой ветвь дерева явно обозначает ИИ-услуги (в отличие от fallback «Программирование/CRM»).
- API возвратил поля этой ветви, включая PriceList.
- Четыре активных объявления на первой странице выдачи API, автозагрузка включена.
- Два запуска не меняли карточки и не списывали деньги.

## Что **не** доказано

- Точная категория каждой из четырёх текущих карточек.
- Наличие в карточках видимой метки/фильтра «Работа с ИИ, нейросетями».
- Полная схема допустимых значений категории (лог показал только whitelist имён полей).
- Показы, просмотры, позиции, контакты, конверсия, выручка.
- Улучшение SEO или изменение поискового трафика.

## Практический следующий шаг

1. Сопоставить текущую категорию каждой карточки с выбранной ветвью дерева (только read-only).
2. Получить полный официальный шаблон/справочник для ветви и проверить значения обязательных полей; не предполагать, что PriceList/Title достаточно для публикации.
3. Собрать baseline показов, просмотров и контактов из статистики кабинета или документированного read-only API.
4. После анализа подготовить отдельную карту предлагаемых изменений и тест одной карточки. Не менять production XML, категории, цены и платное продвижение без отдельного решения.

Не повторять API-вызовы ради уже подтверждённого факта.
