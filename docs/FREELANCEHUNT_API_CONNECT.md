# Freelancehunt API — действующее подключение к VPS

## Подтверждённый результат (11.11.2026)

По отдельному распоряжению владельца использован ранее предоставленный токен. При помощи существующих GitHub Actions SSH secrets создан временный RSA-OAEP 3072-битный ключ на VPS. Токен передан через GitHub только как одноразовый RSA-OAEP-SHA256 шифротекст, расшифрован и помещён на VPS в `~/.freelancehunt-agent/token` (каталог 0700, файл 0600). Установочный приватный ключ удалён после расшифровки. Одноразовый зашифрованный файл удалён из текущего HEAD ветки (прежний commit с шифротекстом сохраняется в истории Git; приватный ключ уже удалён).

**Реальный API тест пройден**: GET https://api.freelancehunt.com/v2/my/profile → HTTP 200; GET https://api.freelancehunt.com/v2/projects → HTTP 200. Внешние профили и персональные данные в логи не выводились.

- GitHub Actions run: https://github.com/olegendorphine-star/ai-ecosystem/actions/runs/42901811799 — conclusion: success.
- Код начального коннектора и тестов: PR #179 https://github.com/olegendorphine-star/ai-ecosystem/pull/179 — пока draft и не слит.
- Рабочая авторизация сейчас существует **на VPS**, а не в GitHub Actions Secrets. Секрет `FREELANCEHUNT_API_TOKEN` в GitHub не создан и не требуется для уже проведённого VPS read-only теста.

## Что ещё не сделано

- Автоматический поиск с расписанием, скоринг заказов, персонализированные предложения и отклики — не внедрены.
- Отправка заявок POST /projects/{id}/bids не проверена, поэтому никакие отклики на Freelancehunt не отправлены.
- Нельзя считать офлайн-тесты, CI и факт HTTP 200 доказательством готовности коммерческих действий.
- Верность и полнота профиля, верификация и правила площадки для ставок не проверены.

## Правила

Токен не копировать в Issues, PR, код, .env, сообщения, артефакты или логи. Исторически токен был передан в чате; владелец сознательно сохранил его. Для будущих GitHub CI проверок нужен отдельный защищённый путь, никогда не считывать файл токена в публичные логи. Никаких платных действий или отправки откликов без отдельного допуска функциональности.

## Следующий этап

Разработать надёжный read-only сбор проектов на VPS с дедупликацией, scoring по ИИ-автоматизации и журналом лидов. Только после проверки профиля, прав и реального объявления — отдельный at-most-once модуль отправки откликов, тестируемый на одном конкретном заказе, с проверкой статуса отправки.

## Browser access investigation — 11.11.2026

Verified using owner VPS and a separate GitHub-hosted runner. Working VPS Chromium/SSH and valid API token do **not** imply access to Freelancehunt's website.

- VPS GET/HEAD `https://freelancehunt.com/` and GET to `/profile/login`, `/my/freelancer`, `/my/skills`: **HTTP 403** with Cloudflare `Server` and `Cf-Ray`, branded `Sorry, you have been blocked` HTML.
- `https://www.freelancehunt.com/` also 403. Browser on VPS returned the same 403 (earlier run #42904190980).
- VPS `https://freelancehunt.com/cdn-cgi/trace` 200; authorized `GET /v2/my/profile` 200; unrelated public HTTPS control 200. DNS resolves; no configured HTTP(S) proxy on VPS.
- Separate GitHub-hosted runner GET homepage: same Cloudflare HTTP 403.
- Latest proof: https://github.com/olegendorphine-star/ai-ecosystem/actions/runs/42955745846 .
- This establishes Cloudflare-layer blocking of web requests, **not** which exact rule/IP/ASN/browser condition caused it. No Cloudflare error 1020 observed.
- Official editor links are `https://freelancehunt.com/my/freelancer` (About), `https://freelancehunt.com/my/skills` (specialization), `https://freelancehunt.com/my/personal` (personal details); official Help Center: https://help-ua.freelancehunt.com/uk/profil/kliuchovi-nalashtuvannia . Prior `/my/profile` is **not** the documented edit link.

**Approved resolution path:** Freelancehunt site's owner must evaluate the blocked Cloudflare event using Ray ID and UTC time, and permit the VPS/network or describe an officially supported remote access path. Another option is an owner-authorized browser on an already permitted network with secure on-device authorization; not yet implemented. Do not use proxy/IP rotation, CAPTCHA bypass or undocumented profile-update requests. No external communications without explicit owner's permission.

**Result:** website profile still unmodified. Only the official API's read operations have been verified.
