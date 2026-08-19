# AngelNotes — сімейний Telegram-бот Куромі

Бот для спільних справ і розкладу дитини. Інтерфейс українською, у стилі Куромі (Sanrio). Стікери з паку [`kuuuuurrrrooommmiii_by_e4zybot`](https://stickers.wiki/ru/telegram/kuuuuurrrrooommmiii_by_e4zybot/).

## Можливості

- Спільні **завдання** (назва, опис, посилання, строк, кілька нагадувань)
- **Розклад**: щотижневі уроки та разові події
- Нагадування «як у Google Calendar» + вечірній дайджест
- **Чат з Куромі** через локальну Ollama (`qwen2.5:3b` за замовчуванням)
- Ролі `parent` / `child`, прапорець адміна `is_admin` у SQLite

## Швидкий старт

1. Створи бота в [@BotFather](https://t.me/BotFather).
2. Скопіюй конфіг:

```bash
cp .env.example .env
# впиши BOT_TOKEN
```

3. Встанови залежності та запусти:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m bot.main
```

Перший користувач, який напише `/start`, стане адміном.

## Docker

Образ бота збирається в **GitHub Actions** і публікується в GHCR: `ghcr.io/sniffy1988/angelnotes-bot:latest`.

На Mac-сервері:

```bash
cp .env.example .env
# впиши BOT_TOKEN

docker compose pull
docker compose up -d
```

База зберігається в `./data` (том `/app/data`).

Оновлення після нового push у `main` (коли Actions зібрав образ):

```bash
docker compose pull bot
docker compose up -d
```

Репозиторій **публічний** — `docker pull` з GHCR зазвичай без логіну (після того, як пакет теж public). Якщо pull просить логін: Package settings → Change visibility → Public.
### Веб-морда до БД (Adminer)

Разом із ботом піднімається [Adminer](https://www.adminer.org/) на порт **8888**.

1. Відкрий `http://<IP-сервера>:8888` (локально: http://127.0.0.1:8888)
2. **System:** SQLite 3
3. **Database:** `/db/bot.db`
4. **Username / Password:** залиш порожніми → Login

Adminer збирається в GHCR як `ghcr.io/sniffy1988/angelnotes-adminer:latest` (разом із ботом у `image.yml`).

Якщо сторінка не відкривається або помилка `plugins-enabled/angelnotes.php`:

```bash
git pull
# якщо раніше був битий mount — angelnotes.php міг стати папкою:
rm -rf adminer/angelnotes.php && git checkout -- adminer/angelnotes.php

docker compose stop adminer
docker compose rm -f adminer
docker compose pull adminer
docker compose up -d adminer
docker compose exec adminer ls -la /var/www/html/plugins-enabled/
```

Остання команда має показати файл `001-angelnotes.php`, не папку.

Якщо база не відкривається (permission denied) — перезапусти adminer після оновлення compose (контейнер має читати `./data/bot.db`).

Локально без GHCR:

```bash
docker build -t angelnotes-adminer:local ./adminer
docker run --rm -p 8888:8080 -v "$PWD/data:/db" --user 0:0 angelnotes-adminer:local
```

Без пароля — доступ має лише довірена мережа (не відкривай порт у інтернет).

## Чат з Куромі (Ollama)

Кнопка **🖤 Поговорити** — вільна розмова з Куромі українською. Бот у Docker звертається до Ollama на Mac-хості.

1. Ollama має бути запущена локально, модель уже стягнута:

```bash
ollama list   # має бути qwen2.5:3b (або інша з OLLAMA_MODEL)
```

2. У `.env` (за замовчуванням уже підходить для Docker на Mac):

```bash
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_TIMEOUT=120
```

3. Перезапусти бота після змін:

```bash
docker compose up -d
```

Якщо модель відповідає повільно або «ламає» персонажа — спробуй `qwen2.5:7b` у `OLLAMA_MODEL`.

Локально без Docker: `OLLAMA_URL=http://127.0.0.1:11434`.

## Змінні середовища

| Змінна | Опис | За замовчуванням |
|---|---|---|
| `BOT_TOKEN` | токен від BotFather | обов’язково |
| `TZ` | часовий пояс | `Europe/Kyiv` |
| `STICKER_SET` | ім’я стікерпаку | `kuuuuurrrrooommmiii_by_e4zybot` |
| `DB_PATH` | шлях до SQLite | `data/bot.db` |
| `OLLAMA_URL` | URL Ollama API | `http://host.docker.internal:11434` |
| `OLLAMA_MODEL` | модель для чату | `qwen2.5:3b` |
| `OLLAMA_TIMEOUT` | таймаут запиту, сек | `120` |

## Ролі та адмін

| Дія | Батьки | Дитина |
|---|---|---|
| Дивитись справи / розклад | так | так |
| Додавати | так | так |
| Редагувати / видаляти справи | усі | лише свої |
| Розклад (усі слоти) | так | так |
| Час дайджесту | так | ні |
| Чат з Куромі | так | так |
| Адмін-панель | якщо `is_admin` | якщо `is_admin` |

Адмін у боті: кнопка `🛡 Адмін` або `/admin` — список користувачів, зміна ролі, прапорець адміна.

Запасний SQL:

```sql
UPDATE users SET role = 'parent' WHERE telegram_id = <id>;
UPDATE users SET is_admin = 1 WHERE telegram_id = <id>;
```

Telegram ID показується після `/start`.

## GitHub Actions

- **CI** (`ci.yml`) — Ruff + `compileall` на PR і `main`
- **Image** (`image.yml`) — на push у `main` (або вручну Run workflow) збирає Docker-образ і пушить у GHCR:
  - `ghcr.io/sniffy1988/angelnotes-bot:latest`
  - `ghcr.io/sniffy1988/angelnotes-bot:sha-<short>`

Локальний білд на сервері не потрібен — тільки `compose pull` + `up`.
## Структура

```
bot/
  main.py
  config.py
  db.py
  texts.py
  stickers.py
  llm.py
  keyboards.py
  middlewares.py
  reminders.py
  handlers/
```

## Ліцензія / контент

Офіційні зображення Sanrio в репозиторій не включені. Аватар бота налаштовується в BotFather. Стікери надсилаються через Telegram API з публічного стікерпаку.
