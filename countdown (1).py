"""Пост @reusham/1070: меняем первую строку подписи, отсчет до 18:50.

--capture: получить пересланный пост и сохранить post_template.json.
--preview: показать новую подпись без публикации.
Без аргументов: обновить подпись при ENABLE_COUNTDOWN=true.
Все старые команды --create удалены: этот скрипт новых постов не создает.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request

CHANNEL = "@reusham"
MESSAGE_ID = 1070
EVENT_AT = datetime.fromisoformat("2026-10-06T18:50:00+03:00")
TEMPLATE = Path(__file__).resolve().with_name("post_template.json")
STYLES = {"bold", "italic", "underline", "strikethrough", "spoiler", "blockquote", "expandable_blockquote"}


class TelegramError(Exception):
    def __init__(self, code, description):
        super().__init__(description)
        self.code = code


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
        raise ConnectionError("Не получен ответ Telegram. Повторите позже.") from None
    if not result.get("ok"):
        raise TelegramError(result.get("error_code", 0),
                            result.get("description", "Ошибка Telegram").replace(token, "[скрыто]"))
    return result["result"]


def units(text):
    return len(text.encode("utf-16-le")) // 2


def plural(number, forms):
    if 11 <= number % 100 <= 14:
        return forms[2]
    if number % 10 == 1:
        return forms[0]
    if 2 <= number % 10 <= 4:
        return forms[1]
    return forms[2]


def first_line(now=None):
    seconds = (EVENT_AT - (now or datetime.now(timezone.utc))).total_seconds()
    if seconds <= 0:
        return "Время кастинга наступило!"
    minutes = math.ceil(seconds / 60)
    if minutes >= 60:
        hours = math.ceil(minutes / 60)
        return f"Осталось менее {hours} {plural(hours, ('часа', 'часов', 'часов'))}…"
    return f"Осталось {minutes} {plural(minutes, ('минута', 'минуты', 'минут'))}…"


def replace_first_line(snapshot, replacement):
    original = snapshot["caption"]
    first, separator, rest = original.partition("\n")
    if not separator or "Осталось" not in first:
        raise ValueError("В первой строке исходного поста не найдено «Осталось». Изменение отменено.")
    old_len = units(first)
    new_len = units(replacement)
    delta = new_len - old_len
    entities = copy.deepcopy(snapshot.get("caption_entities", []))
    for entity in entities:
        start = entity["offset"]
        end = start + entity["length"]
        if start >= old_len:
            entity["offset"] += delta
        elif start == 0 and entity["type"] in STYLES:
            entity["length"] = new_len if end <= old_len else entity["length"] + delta
        else:
            # Не удаляем незаметно ссылку или премиум-значок в заменяемой строке.
            raise ValueError("В первой строке сложное оформление. Нужна отдельная настройка; пост не изменен.")
    caption = replacement + separator + rest
    if units(caption) > 1024:
        raise ValueError("Подпись превышает лимит Bot API 1024 символа. Пост не изменен.")
    return caption, entities


def capture(token):
    chat = api(token, "getChat", chat_id=CHANNEL)
    updates = api(token, "getUpdates", timeout=0, limit=100,
                  allowed_updates=["message", "channel_post", "edited_channel_post"])
    candidates = []
    for update in updates:
        message = update.get("message", {})
        origin = message.get("forward_origin", {})
        if (origin.get("type") == "channel" and origin.get("message_id") == MESSAGE_ID
                and origin.get("chat", {}).get("id") == chat["id"]):
            candidates.append(message)
    if not candidates:
        raise ValueError("Пересланный пост №1070 не найден. Перешлите его боту с указанием источника "
                         "и повторите capture. Не скрывайте имя отправителя при пересылке.")
    message = candidates[-1]
    if "caption" not in message:
        raise ValueError("В пересланном сообщении нет подписи к картинке.")
    snapshot = {"chat_id": chat["id"], "message_id": MESSAGE_ID,
                "caption": message["caption"],
                "caption_entities": message.get("caption_entities", []),
                "show_caption_above_media": message.get("show_caption_above_media", False)}
    # Проверяем, что можем заменить строку, еще до сохранения шаблона.
    replace_first_line(snapshot, first_line())
    TEMPLATE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    custom = sum(e["type"] == "custom_emoji" for e in snapshot["caption_entities"])
    print(f"Исходный пост получен. Премиум-эмодзи: {custom}.")
    print("Пост в канале не изменен. Сохранен post_template.json.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"Исходный пост **1070** получен. Премиум-эмодзи: **{custom}**.\n\n"
                         "Пост в канале не изменен. Скачайте артефакт **post-template**.\n")


def run(mode):
    if mode == "update" and os.environ.get("ENABLE_COUNTDOWN", "").lower() != "true":
        print("Автообновление пока выключено. Пост не изменен.")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if mode == "capture":
        if not token:
            raise ValueError("Не задан Secret TELEGRAM_BOT_TOKEN.")
        capture(token)
        return
    if not TEMPLATE.exists():
        raise ValueError("Сначала получите исходное оформление командой capture и добавьте post_template.json.")
    snapshot = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    if snapshot.get("message_id") != MESSAGE_ID or not snapshot.get("chat_id"):
        raise ValueError("Шаблон относится к другому посту.")
    caption, entities = replace_first_line(snapshot, first_line())
    if mode == "preview":
        print(caption)
        print("\nЭто предпросмотр. Пост не изменен.")
        return
    if any(e["type"] == "custom_emoji" for e in entities):
        raise ValueError("В исходном посте есть премиум-эмодзи. Обновление заблокировано "
                         "до проверки возможности их сохранения в канале. Пост не изменен.")
    if not token:
        raise ValueError("Не задан Secret TELEGRAM_BOT_TOKEN.")
    chat = api(token, "getChat", chat_id=CHANNEL)
    if chat["id"] != snapshot["chat_id"]:
        raise ValueError("Канал в шаблоне не совпадает с @reusham.")
    try:
        api(token, "editMessageCaption", chat_id=chat["id"], message_id=MESSAGE_ID,
            caption=caption, caption_entities=entities,
            show_caption_above_media=snapshot.get("show_caption_above_media", False))
    except TelegramError as error:
        if error.code == 400 and "message is not modified" in str(error).lower():
            print("Текст уже актуален.")
            return
        raise
    print("Первая строка поста №1070 обновлена.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--capture", action="store_true")
    group.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        run("capture" if args.capture else "preview" if args.preview else "update")
    except (ValueError, KeyError, TelegramError, ConnectionError, OSError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
