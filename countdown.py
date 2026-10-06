import argparse
import json
import math
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

CHANNEL = "@reusham"
EVENT_AT = datetime.fromisoformat("2026-10-06T18:50:00+03:00")


def telegram(method, **data):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Не найден секрет TELEGRAM_BOT_TOKEN")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            description = json.loads(error.read()).get(
                "description", "Ошибка Telegram"
            )
        except Exception:
            description = "Ошибка Telegram"
        if "message is not modified" in description.lower():
            return None
        raise RuntimeError(description.replace(token, "[скрыто]")) from None
    except urllib.error.URLError:
        raise RuntimeError("Не удалось подключиться к Telegram") from None

    if not result.get("ok"):
        raise RuntimeError("Telegram отклонил запрос")
    return result["result"]


def plural(number, forms):
    if 11 <= number % 100 <= 14:
        return forms[2]
    if number % 10 == 1:
        return forms[0]
    if 2 <= number % 10 <= 4:
        return forms[1]
    return forms[2]


def countdown_text():
    seconds = (EVENT_AT - datetime.now(timezone.utc)).total_seconds()
    if seconds <= 0:
        return "🎭 Время кастинга в ШАМ наступило!\n\nНачало — в 18:50."

    total_minutes = math.ceil(seconds / 60)
    hours, minutes = divmod(total_minutes, 60)
    parts = []

    if hours:
        parts.append(
            f"{hours} {plural(hours, ('час', 'часа', 'часов'))}"
        )
    if minutes:
        parts.append(
            f"{minutes} {plural(minutes, ('минута', 'минуты', 'минут'))}"
        )

    return (
        "🎭 До кастинга в ШАМ осталось " + " ".join(parts)
        + "\n\nСегодня в 18:50"
        + "\n201 аудитория 8 корпуса"
        + "\nСбор в кафетерии"
        + "\n\nПодробности: https://t.me/reusham/1070"
    )


def main():
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--create", action="store_true")
    modes.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    text = countdown_text()

    if args.preview:
        print(text)
        return

    message_id = os.environ.get("TELEGRAM_MESSAGE_ID", "").strip()

    if args.create:
        if message_id:
            raise RuntimeError(
                "ID поста уже задан. Для обновления выберите update."
            )
        message = telegram(
            "sendMessage",
            chat_id=CHANNEL,
            text=text,
            disable_notification=True,
            link_preview_options={"is_disabled": True},
        )
        result = f"Создан отдельный пост. Его ID: {message['message_id']}"
        print(result)

        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as file:
                file.write(result + "\n")
        return

    if os.environ.get("ENABLE_COUNTDOWN", "").lower() != "true":
        print("Автоматическое обновление пока выключено.")
        return

    if not message_id:
        raise RuntimeError("Не задан TELEGRAM_MESSAGE_ID")

    if int(message_id) <= 1070:
        raise RuntimeError(
            "Нужен ID нового поста со счетчиком. Исходный пост защищен."
        )

    telegram(
        "editMessageText",
        chat_id=CHANNEL,
        message_id=int(message_id),
        text=text,
        link_preview_options={"is_disabled": True},
    )
    print("Счетчик обновлен.")


if __name__ == "__main__":
    main()
