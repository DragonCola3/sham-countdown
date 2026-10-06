"""Счетчик для @reusham. Запускается один раз через GitHub Actions.

TELEGRAM_BOT_TOKEN хранится в Secrets, TELEGRAM_MESSAGE_ID — в Variables.
По расписанию разрешено только редактирование выбранного поста.
Новый пост создается только вручную командой --create.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import sys
import urllib.error
import urllib.request

CHANNEL = "@reusham"
EVENT_AT = datetime.fromisoformat("2026-10-06T19:00:00+03:00")
TITLE = "Открытое занятие театра ШАМ"


class TelegramError(Exception):
    def __init__(self, code, description):
        super().__init__(description)
        self.code = code


def plural(number, forms):
    if 11 <= number % 100 <= 14:
        return forms[2]
    if number % 10 == 1:
        return forms[0]
    if 2 <= number % 10 <= 4:
        return forms[1]
    return forms[2]


def render(now=None):
    now = now or datetime.now(timezone.utc)
    seconds = (EVENT_AT - now).total_seconds()
    if seconds <= 0:
        line = "🎭 Время открытого занятия наступило!"
    else:
        days, rest = divmod(math.ceil(seconds / 60), 1440)
        hours, minutes = divmod(rest, 60)
        parts = []
        for n, forms in ((days, ("день", "дня", "дней")),
                         (hours, ("час", "часа", "часов")),
                         (minutes, ("минута", "минуты", "минут"))):
            if n:
                parts.append(f"{n} {plural(n, forms)}")
        line = "⏳ До начала: " + " ".join(parts)
    return f"🎭 {TITLE}\n\n{line}\n\n📅 6 октября 2026, 19:00 (Москва)"


def api(token, method, **payload):
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            result = json.loads(error.read())
        except (ValueError, UnicodeDecodeError):
            raise TelegramError(error.code, "Ошибка ответа Telegram.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        # Исключение с адресом запроса могло бы раскрыть токен.
        raise ConnectionError("Не получен ответ Telegram. Проверьте канал перед повторным созданием поста.") from None
    if not result.get("ok"):
        description = result.get("description", "Ошибка Telegram").replace(token, "[скрыто]")
        raise TelegramError(result.get("error_code", 0), description)
    return result["result"]


def run(mode):
    if mode == "preview":
        print(render())
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("Добавьте Secret TELEGRAM_BOT_TOKEN в настройках репозитория.")
    raw_id = os.environ.get("TELEGRAM_MESSAGE_ID", "").strip()
    if mode == "create":
        if raw_id:
            raise ValueError("Номер поста уже задан. Выберите update вместо create.")
        if datetime.now(timezone.utc) >= EVENT_AT:
            raise ValueError("Дата занятия уже прошла. Новый пост не создан.")
        message = api(token, "sendMessage", chat_id=CHANNEL, text=render(),
                      disable_notification=True)
        message_id = message["message_id"]
        # Этот номер нужно сохранить вручную, а не в исчезающем файле runner.
        print(f"TELEGRAM_MESSAGE_ID={message_id}", flush=True)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(f"Пост создан. Сохраните Variable **TELEGRAM_MESSAGE_ID** "
                             f"со значением **{message_id}**.\n\n"
                             "После этого выбирайте update. Повторный create до "
                             "сохранения номера создаст еще один пост.\n")
        try:
            api(token, "pinChatMessage", chat_id=CHANNEL, message_id=message_id,
                disable_notification=True)
        except (TelegramError, ConnectionError):
            print("Пост создан, но закрепление не удалось. Закрепите его вручную.")
        return
    if not raw_id:
        print("Номер поста пока не задан. Создание по расписанию запрещено; обновление пропущено.")
        return
    try:
        message_id = int(raw_id)
    except ValueError:
        raise ValueError("TELEGRAM_MESSAGE_ID должен содержать только номер поста.") from None
    if message_id <= 0:
        raise ValueError("Номер поста должен быть положительным.")
    try:
        api(token, "editMessageText", chat_id=CHANNEL, message_id=message_id, text=render())
    except TelegramError as error:
        if error.code == 400 and "message is not modified" in str(error).lower():
            print("Текст уже актуален.")
            return
        raise
    print("Пост обновлен.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--create", action="store_true")
    group.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        run("preview" if args.preview else "create" if args.create else "update")
    except (ValueError, TelegramError, ConnectionError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
