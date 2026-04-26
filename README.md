# FirstTest Cinema

Легкий личный кино-сайт для одного пользователя: каталог, поиск, статусы просмотра,
рейтинг, заметки, комментарии и embed-плеер для легальных источников.

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
