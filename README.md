# AngelNotes — сімейний Telegram-бот Куромі

Бот для спільних справ і розкладу дитини. Інтерфейс українською, у стилі Куромі (Sanrio). Стікери з паку [`kuuuuurrrrooommmiii_by_e4zybot`](https://stickers.wiki/ru/telegram/kuuuuurrrrooommmiii_by_e4zybot/).

## Можливості

- Спільні **завдання** (назва, опис, посилання, строк, кілька нагадувань)
- **Розклад**: щотижневі уроки та разові події
- Нагадування «як у Google Calendar» + вечірній дайджест
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

Образ бота збирається в **GitHub Actions** і публікується в GHCR: `ghcr.io/sniffy1988/angelnotes:latest`.

На Mac-сервері:

```bash
cp .env.example .env
# впиши BOT_TOKEN

# логін у GHCR (PAT з правом read:packages, або gh auth)
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u sniffy1988 --password-stdin

docker compose pull
docker compose up -d
```

База зберігається в `./data` (том `/app/data`).

Оновлення після нового push у `main` (коли Actions зібрав образ):

```bash
docker compose pull bot
docker compose up -d
```

### Веб-морда до БД (Adminer)

Разом із ботом піднімається [Adminer](https://www.adminer.org/) на `http://127.0.0.1:8888` (лише localhost, без пароля).

1. Відкрий http://127.0.0.1:8888
2. **System:** SQLite 3
3. **Database:** `/db/bot.db`
4. **Username / Password:** залиш порожніми

Якщо бот крутиться без Compose, лише Adminer:

```bash
docker run --rm -p 127.0.0.1:8888:8080 -v "$PWD/data:/db" adminer:4
```

Не публікуй порт на `0.0.0.0` — без пароля це повний доступ до бази.

## Змінні середовища

| Змінна | Опис | За замовчуванням |
|---|---|---|
| `BOT_TOKEN` | токен від BotFather | обов’язково |
| `TZ` | часовий пояс | `Europe/Kyiv` |
| `STICKER_SET` | ім’я стікерпаку | `kuuuuurrrrooommmiii_by_e4zybot` |
| `DB_PATH` | шлях до SQLite | `data/bot.db` |

## Ролі та адмін

| Дія | Батьки | Дитина |
|---|---|---|
| Дивитись справи / розклад | так | так |
| Додавати | так | так |
| Редагувати / видаляти справи | усі | лише свої |
| Розклад (усі слоти) | так | так |
| Час дайджесту | так | ні |
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
  - `ghcr.io/sniffy1988/angelnotes:latest`
  - `ghcr.io/sniffy1988/angelnotes:sha-<short>`

Пакет приватний, як репозиторій. Для `docker pull` потрібен логін у `ghcr.io`.

Локальний білд на сервері не потрібен — тільки `compose pull` + `up`.
## Структура

```
bot/
  main.py
  config.py
  db.py
  texts.py
  stickers.py
  keyboards.py
  middlewares.py
  reminders.py
  handlers/
```

## Ліцензія / контент

Офіційні зображення Sanrio в репозиторій не включені. Аватар бота налаштовується в BotFather. Стікери надсилаються через Telegram API з публічного стікерпаку.
