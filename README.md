# FirstTest Cinema

Легкий личный кино-сайт для одного пользователя: быстрый поиск через Kinopoisk API,
подбор плееров через KinoBD по клику на фильм, локальная библиотека, статусы, рейтинг и заметки.

## Быстрый запуск на сервере

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

После запуска сайт будет доступен на `http://SERVER_IP:8000`.

## Важные настройки

- `ADMIN_TOKEN` - пароль для действий записи. В интерфейсе нажмите кнопку с шестеренкой и введите этот токен.
- `DATABASE_PATH` - путь к SQLite базе внутри контейнера. По умолчанию `/data/app.db`.
- `PORT` - внешний порт. По умолчанию `8000`.
- `KINOPOISK_API_KEY` - ключ Kinopoisk Api Unofficial для поиска фильмов.
- `KINOBD_API_URL` - адрес KinoBD API. По умолчанию `https://kinobd.net`.
- `KINOBD_TOKEN` - опциональный токен KinoBD, если он понадобится.

## Команды обслуживания

```bash
docker compose ps
docker compose logs -f
docker compose restart
docker compose down
```

## Обновление

```bash
git pull origin main
docker compose up -d --build
```
