# Подключение Avito API из GitHub Actions — защищённый ручной запуск

Дата: 2026-11-04. Статус: **workflow подготовлен, но реальное соединение не выполнено**.

## Что уже есть
- `tools/avito_preflight.py`: получение `client_credentials` токена и единственное read-only чтение своего профиля. Не сохраняет/не выводит ключи, bearer-токен или персональные поля.
- `.github/workflows/avito-readonly-connection.yml`: только ручной `workflow_dispatch`, только ветка `main`, только при явном подтверждении, без публикаций и переписок.
- Историческая ошибка `unauthorized_client` от 2026-10-30 не устранена и может повториться.
- В текущем PR код **не в main**. Кнопка `Run workflow` появляется после отдельной приёмки и включения workflow в `main` (GitHub требует, чтобы ручной workflow был в default branch).

## Что делает владелец
1. Не отправлять ни `Client ID`, ни `Client Secret` по почте, в чат, Issue, PR, файл или комментарий. Скриншоты реквизитов не публиковать. Если секрет уже показывался, безопаснее отозвать его; владелец на текущем этапе отказался от перевыпуска, это принято как осознанный остаточный риск, но риск не исчез.
2. Зайти в приватный репозиторий `olegendorphine-star/ai-ecosystem` → Settings → Secrets and variables → Actions → **New repository secret** и вручную создать именно:
   - `AVITO_CLIENT_ID`
   - `AVITO_CLIENT_SECRET`
   В значения вставить соответствующие реквизиты из своего кабинета Avito Pro. **НЕ вводить** ключи в поле `Run workflow`: поля запуска и логи не являются хранилищем секретов.
3. После независимой проверки кода и согласованного merge PR #1 в main открыть Actions → “Avito API — manual read-only connection check” → Run workflow → выбрать `main` → отметить `approve_readonly` → Run workflow.
4. В результате смотреть только обезличенные коды стадий (`authorized`, `read_only_ok`, `unauthorized_client`, HTTP status). Не пересылать секреты, исходные тела ответа или полный лог, если в нём есть персональные данные.

## Безопасность / ограничения
- GitHub repository **private**, но `main` технически **не защищён** (`protected=false` на 2026-11-04), поэтому владелец должен проверить права участников: любой с write-доступом может изменить workflow и повлиять на секреты. Не приглашать сторонних исполнителей с write-доступом до ввода секретов и проверки защиты.
- GitHub Actions может расходовать включённые в тариф минуты. Лимит задания: 5 минут; удалённый запрос максимум два HTTP-вызова без повторов.
- Workflow не является постоянно работающей интеграцией/ИИ-агентом: это одноразовая диагностическая проверка. Она не изменяет объявление 449877076 и не пишет в Messenger.
- Проблемы с `unauthorized_client` требуют уточнения прав/типа приложения у Avito, а не механической замены кода.
- При сомнении предпочтителен запуск `tools/avito_terminal_connect.py` на доверенном устройстве владельца **без** помещения секрета в GitHub.

## Источники
- Авито: https://developers.avito.ru/api-catalog
- GitHub secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub ручной запуск: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
- Проектные ограничения: `AGENTS.md`, `docs/STATUS.md`, главный паспорт проекта в Google Drive.
