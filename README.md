# Юридический ассистент ПСБ

FastAPI API для закрытого корпуса: чаты, источники, импорт TXT/PDF/DOCX,
выбор редакций на дату события, BM25 и общее RAG-ядро для API и offline runner.
React + TypeScript frontend находится в `frontend/`, FastAPI — в `backend/`.
Реализация по ТЗ версии 1.0 для Hack&Change 2026. В репозитории только
синтетические примеры: они не являются нормативными актами или реальным корпусом банка.

## Запуск всего приложения

Локальная рабочая БД — SQLite. Из корня проекта:

```powershell
if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }
docker compose up --build -d
```

Интерфейс: http://127.0.0.1:8080. API: http://127.0.0.1:8000/docs.
Корневой Compose поднимает frontend и API с постоянным SQLite volume.
Это отдельное хранилище: локальный `backend/legal.db` автоматически в volume не переносится.
Ключи и модель настраиваются в `backend/.env`, в браузер они не передаются.
Пока `LLM_PROVIDER=disabled`, можно читать документы и историю; генерация
честно сообщает о недоступности модели.

Для фронтенда нужен Node.js 22.19+ и npm.
Без Docker запустите API по инструкции ниже, затем во втором терминале:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Интерфейс: http://127.0.0.1:5173. На Linux/macOS используйте `npm`.
Проверки и описание интерфейса — в [frontend/README.md](frontend/README.md).

## Отдельный запуск бэкенда

Весь бэкенд находится в `backend/`: код, тесты, данные примера, зависимости,
миграции, Docker и `.env.example`. README и общие настройки Git/CI находятся в корне.
Все команды ниже выполняются из `backend/`.

Python 3.12, Docker Engine и Docker Compose. Из корня репозитория:

```sh
cd backend
cp .env.example .env
docker compose up --build -d
```

API: http://localhost:8000, Swagger: http://localhost:8000/docs,
OpenAPI: http://localhost:8000/openapi.json, проверка зависимостей: `/health`.
Compose поднимает API и PostgreSQL 17 с постоянным volume, применяет Alembic.
Порт API опубликован только на loopback. Для frontend используйте корневой Compose или Vite, как описано выше.
Redis не требуется и в health обозначается как disabled.

По умолчанию `LLM_PROVIDER=disabled`: API, чаты и просмотр источников работают,
генерация ответа возвращает 503. Это проверяемое отсутствие провайдера, без фиктивного ответа.
Для реальных ответов задайте в `.env`:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=<идентификатор доступной вам модели Groq>
GROQ_API_KEY=<ваш ключ>
```

Затем `docker compose up -d --force-recreate api`. Модель намеренно не выбрана
за пользователя. Используется [OpenAI-compatible API Groq](https://console.groq.com/docs/openai).
Для организаторов: `LLM_PROVIDER=organizer`, `ORGANIZER_BASE_URL`,
`ORGANIZER_API_KEY`, `LLM_MODEL`. OrganizerProvider пока предполагает
`POST {base_url}/chat/completions`; фактический API надо сверить с регламентом.
Groq не используется автоматически для evaluator.

Локальный запуск без Docker (PowerShell, из корня репозитория;
на Linux используйте `.venv/bin/python`):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m scripts.build_index data/demo/manifest.json data/index/corpus.json
.\.venv\Scripts\python -m scripts.init_db --manifest data/demo/manifest.json
.\.venv\Scripts\python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

По умолчанию локальная БД — SQLite `legal.db`. `DATABASE_URL` переключает SQLAlchemy
на PostgreSQL. API, Alembic и команда инициализации читают одинаковый `DATABASE_URL` из `.env`
и окружения (окружение имеет приоритет). При старте API применяет Alembic;
уже применённые миграции повторно не выполняются. Docker и CI используют те же миграции.
Используйте один API worker: активный индекс и блокировка переиндексации находятся в процессе.

## База данных

Инициализация из `backend/`:

```powershell
python -m scripts.init_db --manifest data/demo/manifest.json
python -m alembic check
```

Команда создаёт/обновляет таблицы в настроенной БД. Для PostgreSQL сама база
и пользователь должны уже существовать; Compose создаёт их автоматически.
Без `--manifest` применяется только схема. Корпус загружается лишь в пустое
хранилище: повторный запуск сохраняет действующий корпус и историю чатов.
Для замены корпуса используйте существующую dev-переиндексацию.

Для отдельного сервера PostgreSQL укажите в `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://<user>:<url-encoded-password>@127.0.0.1:5432/<database>
```

Хранятся документы, редакции и сроки действия, связи с дополнениями, фрагменты,
чаты, сообщения, цитаты, задания импорта и `eval_runs` для метрик оценки.
У редакций есть отдельные `revision`, `source_name`, `source_hash`,
`is_current_only`; имя и хеш источника относятся к конкретной редакции,
чтобы разные файлы одного документа не теряли происхождение.
Чанки сохраняют страницу и переданный embedding. Миграция `0002` переносит
эти значения из существующих снимков, сохраняя ID, текст и ссылки.
В PostgreSQL вспомогательные поля используют JSONB; в SQLite — JSON.
`eval_runs` создаётся как хранилище для инструмента оценки; API не записывает
в него пользовательские диалоги. Векторные значения хранятся в JSONB/JSON;
pgvector и поиск по нему в этой реализации не включены.

## API для frontend

| Метод и путь | Результат |
| --- | --- |
| `GET /api/v1/chats?limit=50&offset=0` | История диалогов, счётчики и пагинация |
| `GET /api/v1/documents?q=...&kind=contract` | Редакции активного корпуса, поиск и пагинация |
| `POST /api/v1/chats` `{title?}` | 201 `{chat_id}` |
| `GET /api/v1/chats/{id}` | Чат и сохранённые сообщения с DTO ответа |
| `POST /api/v1/chats/{id}/messages` | AnswerResponse |
| `GET /api/v1/documents/{id}?version_id=...` | Метаданные редакции и `sections[]` |
| `GET /api/v1/chunks/{id}` | Текст, document/version ID и locator |
| `GET /health` | Состояние БД, версия индекса, размер корпуса |
| `POST /api/v1/admin/reindex` `{corpus_path}` | 202 `{job_id}`; только dev и токен |
| `GET /api/v1/admin/reindex/{job_id}` | Статус задания; те же ограничения |

Ввод сообщения: `question`, необязательные `event_date` (ISO `YYYY-MM-DD`),
`document_id`, `document_kind` (`law`, `contract`, `internal`, `amendment`),
`history: [{role: user|assistant, content}]` (не более 20 сообщений).
В существующем чате сервер использует сохранённую историю; передача дополнительной истории
возвращает 400. На первом сообщении можно импортировать короткую историю.
Дата в текущем вопросе в ISO-формате также распознаётся; для остальных форматов
передавайте `event_date` явно. Отсутствующие критичные данные уточняет LLM.

Ответ: `message_id`, `status`, `answer`, `citations[]`, `reason`, `missing_info[]`,
`clarifying_question`, `trace_id`, `timings_ms`. У citation есть `ref`,
`document_id`, `version_id`, `chunk_id`, `locator`, `quote`.
Ссылка `[N]` соответствует `ref=N`. Для подсветки найдите точную `quote` в тексте chunk;
для документа обязательно передавайте указанную в citation `version_id`.
Если у документа несколько редакций, запрос без version_id возвращает 400.

Статусы: `ANSWERED`, `PARTIAL`, `INSUFFICIENT_EVIDENCE`, `NEED_CLARIFICATION`,
`FALSE_PREMISE`, `HISTORICAL_LAW_UNAVAILABLE`, `OUT_OF_SCOPE`, `DISALLOWED`.
`IGNORE_INJECTION` — внутренний сигнал модели; при доказанном допустимом ответе API
выдаёт `ANSWERED`. Ошибки: 404 — объект отсутствует, 422 — формат,
503 — БД/LLM недоступна или выход LLM нарушает контракт. При 503 история не изменяется.
Не записывайте вопросы и тела ошибок в access logs; рекомендуемая команда их отключает.

## Корпус и индексация

Создайте разрешённый локальный каталог `data/raw` с файлами и `manifest.json`:

```json
{"documents":[{"key":"contract-123","path":"contract.txt",
"title":"Договор 123","kind":"contract","revision":"1",
"valid_from":"2025-01-01","valid_to":null}]}
```

Для нескольких редакций сохраняйте один `key`, указывайте разные revision/интервалы.
Интервалы полуоткрытые: `valid_from <= event_date < valid_to`. Даты не выводятся
из текста и не придумываются. Для дополнения: `kind=amendment`,
`amends_key=contract-123`, его собственные даты действия. Для единственной современной
редакции закона: `is_current_only=true`; вывод на дату до доступной редакции блокируется.
Неизвестная дата начала или пересечение редакций вызывают уточнение.

```sh
python -m scripts.build_index data/raw/manifest.json data/index/corpus.json
```

Стабильные UUID5 зависят от ключа документа, SHA-256 содержимого и метаданных редакции.
Чанки сохраняют точный текст, заголовок/пункт и страницу для PDF. DOCX-таблицы читаются,
но страницы DOCX без рендера не угадываются. Скан без текста требует OCR вне MVP.
Длинные разделы режутся по ~2800 символов с перекрытием ~400; параметры нужно
настроить на реальном корпусе. Максимальный исходный файл — 20 MiB.

Для dev-переиндексации настройте `APP_ENV=development`, непустой `ADMIN_TOKEN`,
`CORPUS_ROOT`; передайте `X-Admin-Token` и путь manifest относительно CORPUS_ROOT.
Выход за каталог и symlink за его пределы запрещены. Admin API не принимает загрузки.
Неуспешный импорт сохраняет предыдущий индекс. Успешный импорт заменяет активный
снимок целиком; передавайте полный manifest. Старые версии остаются в БД для просмотра
цитат из истории. Перезапуск не заменяет этот снимок bootstrap-индексом из INDEX_PATH.
Переиндексация — фоновая задача процесса; при аварии API повторите запрос.

Поиск по умолчанию BM25 (разрешённый ТЗ автономный fallback), без внешнего поиска.
`OfflineIndex` поддерживает готовые векторы BAAI/bge-m3 и callback query embedding
с cosine + RRF; автоматический расчёт эмбеддингов и pgvector-адаптер не включены.
PostgreSQL хранит документы/версии/чанки/чаты/цитаты/задания; миграция создаёт
русский FTS GIN-индекс для последующего SQL-адаптера. Текущее API использует OfflineIndex.

## Ядро и контроль достоверности

`packages/legal_core` не импортирует FastAPI, PostgreSQL или Redis.
Порты `SearchIndex` и `LLMGateway` используются одинаково в API и evaluator.
Пайплайн: запрос/история → поиск → отбор редакций и связанных дополнений →
ограниченный контекст → JSON DraftAnswer → проверка ID/quote → отдельная проверка
опоры утверждений моделью → ответ с серверными ссылками или мотивированный отказ.
Произвольный текст источника никогда не становится system/developer сообщением.
Существование chunk/quote/редакции проверяется детерминированно. Семантическая
проверка, ложные предпосылки, незаконные запросы и injection зависят от модели:
это не формальная гарантия юридической правильности. Для сложных дополнений нет
автоматического слияния текста; модель получает основание и действующие изменения,
а неподтверждённый вывод блокируется проверкой. Валидация JSON повторяется один раз.

## Offline evaluator

```sh
python -m scripts.package_submission --index data/index/corpus.json --output dist/submission.zip
python -m submission.solution < questions.jsonl
```

Один JSON Question на строку, один Answer на строку. Также доступен
`submission.solution.solve(payload)`. История не сохраняется между вызовами.
Нужны INDEX_PATH и разрешённый organizer API; БД/Redis/веб-сервер не используются.
Ошибка конфигурации/ввода возвращает отдельный `{error: ...}`, CLI завершится с кодом 1.
Архив включает корневой `solution.py`, Python-пакеты, lock-файл и выбранный индекс.
Проверьте разрешение на включение реальных данных до упаковки.

Это предварительный внутренний JSONL-контракт: образец solution.py, API,
лимиты и технический регламент организаторов не предоставлены. Совместимость
с их платформой и DeepSeek V4.1 Flash ещё не подтверждена.

## Проверки и ограничения

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m alembic upgrade head
python -m alembic check
python -m scripts.smoke
```

CI проверяет тесты, формат, миграции, сборку ZIP и отдельно PostgreSQL smoke.
Тестовые LLM используются только через dependency injection в тестах, не доступны
в настройках приложения. Проверяются настоящие ссылки и отказы на подделанные цитаты,
границы дат, дополнения, отсутствующая старая редакция закона, изоляция истории,
обработка сбоев провайдера, сохранение старых ссылок и атомарность импорта.
Проверка раскладки промпта не заменяет adversarial-прогон настоящей модели.

Реальный корпус, ключ Groq и образец организаторов отсутствуют. Поэтому качество
юридических ответов, 30 размеченных реальных кейсов, p50/p95 с моделью и leaderboard
пока не измерены. SSO/IAM, OCR, автоматический сбор законов и презентация
не входят в этот backend. Без IAM запуск предназначен для локального демо.
Перед командным деплоем нужны контроль доступа к чатам, TLS и политика хранения данных.

Оригинал ТЗ не добавлен в публичный репозиторий. Здесь нет рабочих ключей, ПД и
банковских документов. `.env`, исходный корпус, локальная БД и сгенерированные ZIP
исключены из Git.
