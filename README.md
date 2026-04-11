# VK2TG POST

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=0B1220)
![Vite](https://img.shields.io/badge/Vite-7-646CFF?logo=vite&logoColor=white)
![Storage](https://img.shields.io/badge/Storage-JSON%20%2F%20JSONL-4B5563)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status](https://img.shields.io/badge/Status-Active%20Development-10B981)

Переносите посты из VK в Telegram через современную админку, с шифрованием токенов, историей переносов и простым файловым хранилищем без SQL-базы.

## Возможности

- Мониторинг нескольких сообществ VK из одной админки
- Перенос текста, фото, документов, ссылок, музыки и доступных видео-вложений в Telegram
- Настройка того, что именно переносить, отдельно для каждого источника
- Поддержка открытых стен и постов подписчиков
- Защита от повторной отправки уже обработанных постов
- История переносов со статусами, попытками и подробными ошибками
- Просмотр и очистка кэша вложений из интерфейса
- Автоматическая очистка кэша после успешной отправки
- Настройка proxy через админку
- Ручной запуск проверки, очистка очереди и просмотр логов без доступа к серверу

## Технологии

- Backend: FastAPI
- Frontend: React + Vite + TypeScript
- Хранилище: JSON / JSONL
- Обработка медиа: `ffmpeg`
- Авторизация: session auth для админки, HTTP Basic для API
- Секреты: локальное шифрование при хранении

## Как это выглядит в работе

В React-админке есть следующие разделы:

- Дашборд
- Источники
- Переносы
- Кэш
- Логи
- Настройки

Типовой сценарий использования:

1. Войти в админку
2. Добавить источник VK
3. Выбрать, что именно переносить из постов
4. Указать Telegram-назначение и токены интеграций
5. Запустить проверку вручную или оставить polling-воркер работать по расписанию
6. При необходимости посмотреть историю, логи и кэш

## Гибкая настройка источников

Для каждого источника можно отдельно выбрать, что именно переносить:

- текст
- картинки
- видео
- музыку
- документы
- ссылки

Дополнительно можно включать и выключать:

- подпись источника
- ссылку на оригинальный пост
- дату оригинальной публикации
- репосты
- посты подписчиков на открытой стене

Это позволяет использовать один сервис сразу для нескольких Telegram-каналов с разными правилами публикации.

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone <YOUR_REPO_URL>
cd botPerenos
```

### 2. Создание `.env`

```bash
cp .env.example .env
```

Минимальный пример:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
ADMIN_PASSWORD_HASH=
SESSION_SECRET=change-me-please
POLL_INTERVAL_SECONDS=300
RETRY_LIMIT=3
FFMPEG_BINARY=ffmpeg
DATA_DIR=data
CACHE_DIR=data/cache
LOG_LEVEL=INFO
```

## Запуск backend

### Windows

```bash
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Linux

Установите Python 3.14, `venv` и `ffmpeg`, затем:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Если `ffmpeg` ещё не установлен:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

## Запуск frontend

Админка лежит в каталоге `frontend/`.

### Режим разработки

Сначала запустите backend, затем во frontend:

```bash
cd frontend
npm install
npm run dev
```

Открывать:

- [http://localhost:5173/app/](http://localhost:5173/app/)

Vite автоматически проксирует `/api` на FastAPI на порту `8000`.

### Production-сборка

```bash
cd frontend
npm install
npm run build
```

После сборки FastAPI сам начнёт отдавать фронтенд по адресу:

- [http://localhost:8000/app/](http://localhost:8000/app/)

## Первый запуск

После старта приложения:

1. Откройте админку
2. Войдите с логином и паролем из `.env`
3. Перейдите в `Настройки`
4. Укажите:

- `VK token`
- `Telegram bot token`
- `Telegram proxy`, если Telegram в вашей стране недоступен напрямую
- `FFmpeg binary`, если нужен нестандартный путь

После этого можно добавлять источники и запускать перенос.

## API

Маршрут `GET /api/health` открыт для проверки доступности.

Остальные API-методы требуют:

- активную админскую сессию
- или HTTP Basic авторизацию с логином и паролем администратора

Для запросов из браузерной сессии, которые меняют состояние, также нужен заголовок `X-CSRF-Token`.

Основные маршруты:

- `GET /api/auth/session`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/dashboard`
- `GET /api/sources`
- `POST /api/sources`
- `PUT /api/sources/{source_id}`
- `DELETE /api/sources/{source_id}`
- `GET /api/transfers`
- `GET /api/transfers/{transfer_id}`
- `GET /api/logs`
- `GET /api/cache`
- `POST /api/cache/clear`
- `GET /api/settings/view`
- `PUT /api/settings/view`
- `POST /api/worker/run`
- `POST /api/worker/clear-queue`

## Как хранится состояние

Проект специально не использует SQL-базу в core-MVP.

Это даёт несколько преимуществ:

- состояние легко читать прямо с диска
- резервное копирование и перенос между машинами проще
- деплой не зависит от отдельной БД

Ключевые файлы:

- `data/settings.json`
- `data/sources.json`
- `data/transfers/index.jsonl`
- `data/transfers/<id>.json`
- `data/logs/service.jsonl`
- `data/state/runtime.json`
- `data/state/tokens.key`
- `data/cache/`

## Ограничения

- Не каждое видео VK можно скачать через доступные ответы API
- Для Telegram в некоторых регионах может потребоваться proxy
- Файловое хранилище выбрано осознанно, но для очень больших инсталляций со временем может понадобиться SQL

## Roadmap

- Повторный запуск конкретного неуспешного переноса
- Проверка токенов и proxy прямо из `Настроек`
- Более умная очередь и управление расписанием
- Улучшенные фильтры и экспорт логов
- Поддержка альтернативных backend-хранилищ

## Contributing

Идеи, баг-репорты и улучшения приветствуются.

Если создаёте issue, очень помогает приложить:

- какой источник использовался
- какой тип вложения не сработал
- был ли включён proxy для Telegram
- статус переноса или фрагмент логов

## Лицензия

Проект распространяется под лицензией MIT. Полный текст находится в файле [LICENSE](./LICENSE).

## Для кого это полезно

Проект особенно удобен, если вам нужен:

- self-hosted сервис `VK -> Telegram`
- внятный интерфейс управления, а не набор скриптов
- развёртывание без PostgreSQL и лишней инфраструктуры
- система, в которой можно быстро понять, почему именно интеграция не сработала

Если это похоже на ваш сценарий, репозиторий как раз про это.
