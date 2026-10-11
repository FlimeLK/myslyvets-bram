#!/usr/bin/env python3
"""Мисливець Брам — Telegram-бот, що відкриває гру як Mini App.

Без сторонніх бібліотек: лише стандартна бібліотека Python 3.8+.
Токен береться з bot/.env (BOT_TOKEN=...) або зі змінної середовища BOT_TOKEN.
"""
import html
import json
import os
import signal
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env():
    env = {}
    path = HERE / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


ENV = load_env()
TOKEN = os.environ.get("BOT_TOKEN") or ENV.get("BOT_TOKEN", "")
WEBAPP_URL = os.environ.get("WEBAPP_URL") or ENV.get("WEBAPP_URL") or "https://flimelk.github.io/myslyvets-bram/"
API = "https://api.telegram.org/bot{}/{}"
SSL_CTX = ssl.create_default_context()
BOT_USERNAME = "myslyvets_bram_bot"
RUNNING = True

WELCOME = (
    "<b>{name}, ти загинув. Але Система обрала твою душу.</b>\n\n"
    "Переродися мисливцем: обери одну з 8 форм, зачищай брами поверх за поверхом, "
    "виноси здобич і піднімайся з рангу E до S.\n\n"
    "Натисни «Грати» — гра відкриється просто тут, у Telegram. "
    "Прогрес зберігається у твоєму акаунті, тож на телефоні й комп’ютері герой той самий."
)
HELP = (
    "<b>Як грати</b>\n\n"
    "• <b>Брама</b> — 3 поверхи: на кожному двоє монстрів і страж, у кінці бос. Вхід ⚡4, спуск глибше ⚡2.\n"
    "• Після поверху вибираєш: вийти зі здобиччю чи ризикнути глибше. Смерть забирає все з рюкзака.\n"
    "• Над кнопками видно намір ворога. Замах означає Сокрушення ×2,2 — став Захист або оглуши.\n"
    "• Кожен рівень дає 5 очок характеристик. ★ — головна характеристика класу.\n"
    "• Ранг піднімає Випробування на 8, 15, 22, 29 і 36 рівнях.\n"
    "• Енергія відновлюється сама: +1 кожні 5 хвилин. Без енергії є фарм-зона й арена.\n\n"
    "/play — відкрити гру\n/help — ця довідка"
)
ABOUT = (
    "<b>Мисливець Брам</b> — українська рольова гра в Telegram.\n\n"
    "8 класів, 22 брами, випробування рангів E→S, арена, кузня, квест дня і колесо долі. "
    "Гра безкоштовна: без реклами й реальних платежів."
)
COMMANDS = [
    {"command": "start", "description": "Почати гру"},
    {"command": "play", "description": "Відкрити гру"},
    {"command": "help", "description": "Як грати"},
    {"command": "about", "description": "Про гру"},
]


def log(*parts):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *parts, flush=True)


def call(method, params=None, timeout=30):
    body = json.dumps({k: v for k, v in (params or {}).items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(API.format(TOKEN, method), data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", "replace")
        try:
            desc = json.loads(raw).get("description", raw)
        except ValueError:
            desc = raw
        raise RuntimeError("{}: {} {}".format(method, err.code, desc)) from None
    if not data.get("ok"):
        raise RuntimeError("{}: {}".format(method, data.get("description", "помилка API")))
    return data["result"]


def play_keyboard(private):
    if private:
        play = {"text": "⚔️ Грати", "web_app": {"url": WEBAPP_URL}}
    else:
        play = {"text": "⚔️ Грати", "url": "https://t.me/{}?start=play".format(BOT_USERNAME)}
    return {"inline_keyboard": [[play], [{"text": "Як грати", "callback_data": "help"}]]}


def send(chat_id, text, private=True, keyboard=True):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if keyboard:
        params["reply_markup"] = play_keyboard(private)
    call("sendMessage", params)


def handle(update):
    query = update.get("callback_query")
    if query:
        call("answerCallbackQuery", {"callback_query_id": query["id"]})
        msg = query.get("message")
        if msg and query.get("data") == "help":
            send(msg["chat"]["id"], HELP, private=msg["chat"].get("type") == "private")
        return

    msg = update.get("message")
    if not msg:
        return
    chat = msg["chat"]
    private = chat.get("type") == "private"
    text = (msg.get("text") or "").strip()
    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
    name = html.escape((msg.get("from") or {}).get("first_name") or "Мисливцю")

    if command in ("/start", "/play"):
        send(chat["id"], WELCOME.format(name=name) if command == "/start" else "Брами чекають. Тисни «Грати».", private)
    elif command == "/help":
        send(chat["id"], HELP, private)
    elif command == "/about":
        send(chat["id"], ABOUT, private)
    elif private:
        send(chat["id"], "Я відкриваю гру. Тисни «Грати» або /help, щоб дізнатися правила.", private)


def setup():
    global BOT_USERNAME
    me = call("getMe")
    BOT_USERNAME = me.get("username") or BOT_USERNAME
    call("deleteWebhook", {"drop_pending_updates": False})
    call("setMyCommands", {"commands": COMMANDS})
    call("setChatMenuButton", {"menu_button": {"type": "web_app", "text": "Грати", "web_app": {"url": WEBAPP_URL}}})
    log("Бот @{} запущено. Гра: {}".format(BOT_USERNAME, WEBAPP_URL))


def stop(_signum, _frame):
    global RUNNING
    RUNNING = False
    log("Зупиняюсь…")
    sys.exit(0)


def main():
    if not TOKEN or ":" not in TOKEN:
        print("Немає токена. Запусти bot/start.sh — він попросить вставити токен від @BotFather.")
        sys.exit(1)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    delay = 5
    while RUNNING:
        try:
            setup()
            break
        except ssl.SSLError as err:
            log("SSL-помилка:", err, "— якщо це python.org Python, запусти «Install Certificates.command».")
            time.sleep(30)
        except Exception as err:  # мережа ще не готова або неправильний токен
            log("Не вдалось підключитися:", err)
            if "401" in str(err) or "Unauthorized" in str(err):
                print("Telegram не прийняв токен. Видали bot/.env і запусти bot/start.sh ще раз.")
                sys.exit(1)
            time.sleep(delay)
            delay = min(delay * 2, 120)

    offset = None
    while RUNNING:
        try:
            updates = call("getUpdates", {"timeout": 50, "offset": offset,
                                          "allowed_updates": ["message", "callback_query"]}, timeout=65)
        except Exception as err:
            log("getUpdates:", err)
            time.sleep(5)
            continue
        for update in updates:
            offset = update["update_id"] + 1
            try:
                handle(update)
            except Exception as err:
                log("Помилка обробки:", err)


if __name__ == "__main__":
    main()
