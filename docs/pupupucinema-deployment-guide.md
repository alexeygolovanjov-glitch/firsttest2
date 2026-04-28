# Личный кинотеатр: гайд по запуску на новом сервере и домене

Дата: 28 апреля 2026

Этот документ сохраняет итог нашей работы: какие файлы нужны, как поднять такой же сайт на другом VPS, как подключить домен и HTTPS, какие ошибки уже встретились и как их чинить. В конце есть готовый промпт для Codex, чтобы быстро восстановить контекст в новом чате.

## 1. Что получилось

Мы собрали личный сайт-кинотеатр:

- пароль на вход без регистрации пользователей;
- профили внутри сайта: "Я", "Жена", "Ребёнок" и новые профили вручную;
- у каждого профиля отдельный список фильмов;
- поиск фильмов через Kinopoisk unofficial API;
- плееры через KinoBD;
- выбор и запоминание плеера для сохранённого фильма;
- удаление фильма из списка;
- заметки, оценка, статусы;
- запуск через Docker Compose на VPS;
- домен `pupupucinema.ru`;
- HTTPS через nginx и Let’s Encrypt.

## 2. Нужные файлы проекта

Минимальный набор файлов в репозитории:

```text
Dockerfile
docker-compose.yml
requirements.txt
.env.example
.gitignore
README.md
app/__init__.py
app/main.py
static/index.html
static/app.js
static/styles.css
static/poster-placeholder.svg
```

Назначение:

- `app/main.py` - FastAPI backend, SQLite, профили, фильмы, Kinopoisk, KinoBD.
- `static/index.html` - основная страница.
- `static/app.js` - логика интерфейса, авторизация, профили, поиск, плееры.
- `static/styles.css` - визуальная тема.
- `docker-compose.yml` - запуск контейнера и проброс `8000:8000`.
- `.env` на сервере - реальные токены и настройки. Его не надо коммитить.

## 3. Переменные окружения

На сервере нужен файл `.env` в корне проекта:

```env
APP_NAME=Личный кинотеатр
ADMIN_TOKEN=придумай-свой-пароль
DATABASE_PATH=/data/app.db
PORT=8000

KINOPOISK_API_KEY=твой_ключ_kinopoisk_unofficial_api
KINOBD_API_URL=https://kinobd.net
KINOBD_TOKEN=
PLAYER_API_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36
```

Важно:

- `ADMIN_TOKEN` - пароль от сайта.
- `KINOPOISK_API_KEY` - нужен для поиска фильмов.
- `KINOBD_API_URL=https://kinobd.net` - источник плееров.
- `DATABASE_PATH=/data/app.db` - база сохраняется в Docker volume/bind mount.

## 4. Подготовка нового VPS

Команды для Ubuntu 22.04:

```bash
apt update
apt install -y git curl ca-certificates docker.io docker-compose-plugin nginx certbot python3-certbot-nginx dnsutils
systemctl enable --now docker
systemctl enable --now nginx
```

Проверка Docker:

```bash
docker --version
docker compose version
```

## 5. Загрузка проекта

На новом сервере:

```bash
cd ~
git clone https://github.com/alexeygolovanjov-glitch/firsttest2.git
cd firsttest2
cp .env.example .env
nano .env
```

Заполнить `.env`, затем:

```bash
docker compose up -d --build
docker ps
curl -I http://127.0.0.1:8000
```

Если `curl -I` вернёт `405 Method Not Allowed`, это не страшно. FastAPI может не принимать `HEAD`, но сайт по `GET` работает.

Проверка в браузере до домена:

```text
http://IP_СЕРВЕРА:8000
```

## 6. DNS домена

Для нового домена нужно узнать IP сервера:

```bash
curl -4 ifconfig.me
```

Если команда вывела, например:

```text
82.25.39.164
```

В панели регистратора добавить DNS:

```text
A     @      82.25.39.164
A     www    82.25.39.164
```

Проверка:

```bash
dig +short example.ru
dig +short www.example.ru
```

Обе команды должны вернуть IP сервера.

Пока `dig` ничего не выводит или возвращает другой IP, Certbot запускать рано.

## 7. nginx reverse proxy

Создать конфиг:

```bash
nano /etc/nginx/sites-available/example.ru
```

Вставить:

```nginx
server {
    listen 80;
    server_name example.ru www.example.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включить сайт:

```bash
ln -s /etc/nginx/sites-available/example.ru /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx
```

Проверка:

```bash
curl -I http://example.ru
```

## 8. HTTPS через Let’s Encrypt

Когда DNS уже указывает на VPS:

```bash
certbot --nginx -d example.ru -d www.example.ru
```

Если Certbot спросит про redirect, выбрать вариант с редиректом HTTP -> HTTPS.

Проверка:

```bash
ss -ltnp | grep ':443'
curl -I https://example.ru
curl -I https://www.example.ru
curl -I http://example.ru
```

Ожидаемо:

- `:443` слушает `nginx`;
- `https://example.ru` отвечает без SSL-ошибки;
- `http://example.ru` отдаёт `301` на HTTPS.

## 9. Важный конфликт с VPN на 443

У нас была проблема: порт `443` занимал контейнер Amnezia/XRay:

```text
amnezia-xray  0.0.0.0:443->443/tcp
```

Из-за этого HTTPS-запросы попадали не в nginx, а в VPN-контейнер. Браузер видел неправильный сертификат, а `curl` писал:

```text
SSL: no alternative certificate subject name matches target host name
```

Решение:

1. В Amnezia перенести VPN на другой порт, например `444`.
2. Убедиться, что 443 свободен:

```bash
ss -ltnp | grep ':443'
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}"
```

3. Перезапустить nginx:

```bash
systemctl restart nginx
ss -ltnp | grep ':443'
```

После исправления должно быть:

```text
:443 -> nginx
```

А не:

```text
:443 -> docker-proxy
```

## 10. Ошибки, в которые мы упирались

### 10.1. `warning: You appear to have cloned an empty repository`

Причина: GitHub-репозиторий был пустой.

Решение: сначала залить файлы проекта в репозиторий, потом на сервере делать `git pull`.

### 10.2. `cd: -f: invalid option`

Причина: папка называлась `-firsttest`, а `cd -firsttest` воспринимается как флаг.

Решение: не начинать имя репозитория с дефиса. Новый репозиторий назвали `firsttest2`.

### 10.3. `Password authentication is not supported for Git operations`

Причина: GitHub больше не принимает пароль для `git push/pull` по HTTPS.

Решение: использовать Personal Access Token или пушить через уже авторизованную локальную среду.

### 10.4. `no configuration file provided: not found`

Причина: команда `docker compose up` была запущена не из папки проекта.

Решение:

```bash
cd ~/firsttest2
docker compose up -d --build
```

### 10.5. `Плеер не указан`

Причина: сначала не был подключён рабочий источник плееров.

Решение: оставить KinoBD и задать:

```env
KINOBD_API_URL=https://kinobd.net
```

### 10.6. `KinoBD: 403 error code: 1010`

Причина: временная защита/доступ KinoBD, либо неверный путь обращения.

Решение: использовать текущую схему KinoBD через backend, не обращаться к нему напрямую из браузера.

### 10.7. Профили не отображались, кнопки были пустыми

Причина: браузер держал старый `app.js`/`styles.css` в кеше.

Решение: добавить cache-busting:

```html
/assets/styles.css?v=profiles-20260427-2
/assets/app.js?v=profiles-20260427-2
```

И очистить данные сайта при необходимости.

### 10.8. После смены домена перестал подходить пароль

Причина: пароль хранится в браузере в `localStorage` как `adminToken`. После изменений мог остаться старый токен.

Решение в DevTools Console:

```js
localStorage.removeItem('adminToken')
```

Или полностью:

```js
localStorage.clear()
```

### 10.9. Certbot: `NXDOMAIN looking up A`

Причина: домен не был прописан в DNS или был указан неправильный домен.

Пример ошибки:

```text
DNS problem: NXDOMAIN looking up A for pupupuicinema.ru
```

Решение:

- проверить правильное написание домена;
- добавить `A @` и `A www`;
- дождаться DNS;
- проверить `dig +short domain`.

### 10.10. Перепутали домен

Было:

```text
pupupuicinema.ru
```

Правильно:

```text
pupupucinema.ru
```

Решение: поправить `server_name` в nginx и перевыпустить сертификат на правильный домен.

### 10.11. HTTPS отдавал неправильный сертификат

Причина: порт 443 был занят VPN-контейнером `amnezia-xray`.

Диагностика:

```bash
ss -ltnp | grep ':443'
docker ps --format "table {{.ID}}\t{{.Names}}\t{{.Ports}}"
```

Решение: перенести VPN на другой порт, перезапустить nginx.

### 10.12. В инкогнито HTTPS работает, в обычной вкладке нет

Причина: браузер закешировал старую ошибку сертификата или данные сайта.

Решение:

- открыть настройки сайта;
- удалить данные для домена;
- либо `chrome://settings/siteData`, найти домен и удалить;
- потом заново открыть `https://domain`.

## 11. Полная последовательность запуска на новом домене

Заменить `example.ru` и `IP_СЕРВЕРА` на свои значения.

```bash
apt update
apt install -y git curl ca-certificates docker.io docker-compose-plugin nginx certbot python3-certbot-nginx dnsutils
systemctl enable --now docker
systemctl enable --now nginx

cd ~
git clone https://github.com/alexeygolovanjov-glitch/firsttest2.git
cd firsttest2
cp .env.example .env
nano .env

docker compose up -d --build
curl -I http://127.0.0.1:8000

nano /etc/nginx/sites-available/example.ru
ln -s /etc/nginx/sites-available/example.ru /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

dig +short example.ru
dig +short www.example.ru

certbot --nginx -d example.ru -d www.example.ru

ss -ltnp | grep ':443'
curl -I https://example.ru
```

## 12. Готовый nginx-конфиг после Certbot

Пример итогового конфига:

```nginx
server {
    server_name example.ru www.example.ru;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/example.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.ru/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}

server {
    if ($host = www.example.ru) {
        return 301 https://$host$request_uri;
    }

    if ($host = example.ru) {
        return 301 https://$host$request_uri;
    }

    listen 80;
    server_name example.ru www.example.ru;
    return 404;
}
```

## 13. Обновление сайта после изменений

На локальной машине:

```bash
git add .
git commit -m "Описание изменений"
git push
```

На сервере:

```bash
cd ~/firsttest2
git pull
docker compose up -d --build
```

Если фронтенд выглядит старым, очистить кеш браузера или обновить версию в `static/index.html`:

```html
<link rel="stylesheet" href="/assets/styles.css?v=new-version" />
<script src="/assets/app.js?v=new-version" type="module"></script>
```

## 14. Промпт для Codex

Скопируй этот промпт в новый чат, если нужно развернуть такой же сайт на новом сервере:

```text
Ты Codex. Нужно помочь развернуть личный сайт-кинотеатр на VPS и домене.

Проект: FastAPI + SQLite + статический фронтенд + Docker Compose.
Репозиторий: https://github.com/alexeygolovanjov-glitch/firsttest2.git

Функции сайта:
- вход по ADMIN_TOKEN без регистрации;
- профили пользователей внутри сайта;
- отдельный список фильмов для каждого профиля;
- поиск фильмов через Kinopoisk unofficial API;
- плееры через KinoBD;
- сохранение выбранного плеера;
- Docker Compose на порту 8000;
- nginx reverse proxy;
- HTTPS через Let’s Encrypt.

Нужно:
1. Подготовить VPS Ubuntu.
2. Клонировать репозиторий.
3. Создать .env с ADMIN_TOKEN, KINOPOISK_API_KEY, KINOBD_API_URL=https://kinobd.net.
4. Запустить docker compose up -d --build.
5. Настроить DNS домена: A @ и A www на IP VPS.
6. Настроить nginx proxy_pass на 127.0.0.1:8000.
7. Выпустить сертификат certbot --nginx -d DOMAIN -d www.DOMAIN.
8. Проверить, что 443 слушает nginx, а не Docker/VPN.
9. Если есть Amnezia/XRay на 443, перенести VPN на другой порт.
10. Если браузер показывает старую ошибку сертификата, очистить site data.

Типовые ошибки:
- NXDOMAIN у Certbot = DNS не настроен или домен написан неверно.
- SSL certificate subject mismatch = 443 занят другим сервисом или nginx отдаёт не тот сертификат.
- select профилей пустой = старый app.js в кеше или не работает /api/profiles.
- пароль не подходит = старый adminToken в localStorage или ADMIN_TOKEN изменился.

Работай пошагово, проси вывод команд и объясняй, что именно проверяем.
```

## 15. Финальная проверка

На рабочем сервере:

```bash
docker ps
nginx -t
ss -ltnp | grep ':80'
ss -ltnp | grep ':443'
dig +short example.ru
dig +short www.example.ru
curl -I http://example.ru
curl -I https://example.ru
certbot certificates
```

Правильное состояние:

- `firsttest-cinema` слушает `8000`;
- nginx слушает `80` и `443`;
- VPN не занимает `443`;
- домен указывает на IP сервера;
- HTTP редиректит на HTTPS;
- HTTPS открывается без ошибок сертификата;
- сайт просит пароль и после входа показывает профили.
