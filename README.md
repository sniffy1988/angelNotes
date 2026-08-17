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

```bash
cp .env.example .env
docker compose up -d --build
```

База зберігається в `./data` (том `/app/data`).

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
- **Image** (`image.yml`) — збірка й push образу в GHCR (`ghcr.io/<owner>/<repo>:latest`)

Підтягнути образ:

```bash
docker pull ghcr.io/<owner>/angelnotes:latest
```

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
