"""Адмін-панель бота «Мисливець Брам»: облік гравців, статистика, розсилка, стан бота.

Доступ лише для ID з ADMIN_IDS (bot/.env) — за замовчуванням 1859870653.
Дані гравців лежать у bot/users.json (у git не потрапляє).
"""
import html
import json
import os
import random
import re
import string
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
USERS_FILE = HERE / "users.json"
STARTED_AT = time.time()
DAY = 86400


def parse_ids(raw):
    ids = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


class Admin:
    def __init__(self, call, log, env):
        self.call = call
        self.log = log
        self.ids = parse_ids(os.environ.get("ADMIN_IDS") or env.get("ADMIN_IDS") or "1859870653")
        self.users = {}
        self.lock = threading.Lock()
        self.dirty = False
        self.saved_at = 0
        self.pending = {}       # admin_id -> стан: {"mode": "broadcast"} або {"mode": "confirm", "chat": .., "msg": ..}
        self.broadcasting = False
        self.handled = 0
        self.errors = 0
        self.webapp_url = env.get("WEBAPP_URL") or "https://flimelk.github.io/myslyvets-bram/"
        self.load()

    # ---------- зберігання ----------
    def load(self):
        try:
            data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
            self.users = {int(k): v for k, v in data.get("users", {}).items()}
        except (OSError, ValueError):
            self.users = {}

    def save(self, force=False):
        if not self.dirty or (not force and time.time() - self.saved_at < 10):
            return
        with self.lock:
            data = {"users": {str(k): v for k, v in self.users.items()}}
            tmp = USERS_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, USERS_FILE)
            self.dirty = False
            self.saved_at = time.time()

    def track(self, user, chat_type, is_start=False):
        if not user or user.get("is_bot") or chat_type != "private":
            return
        now = int(time.time())
        with self.lock:
            u = self.users.get(user["id"])
            if not u:
                u = {"first": now, "starts": 0, "msgs": 0}
                self.users[user["id"]] = u
            u["name"] = ((user.get("first_name") or "") + " " + (user.get("last_name") or "")).strip()[:64]
            u["username"] = user.get("username") or ""
            u["lang"] = user.get("language_code") or ""
            u["last"] = now
            u["msgs"] = u.get("msgs", 0) + 1
            u.pop("blocked", None)
            if is_start:
                u["starts"] = u.get("starts", 0) + 1
            self.dirty = True
        self.save()

    def is_admin(self, user_id):
        return user_id in self.ids

    # ---------- тексти ----------
    def stats_text(self):
        now = time.time()
        us = list(self.users.values())
        total = len(us)
        blocked = sum(1 for u in us if u.get("blocked"))
        new1 = sum(1 for u in us if now - u.get("first", 0) < DAY)
        new7 = sum(1 for u in us if now - u.get("first", 0) < 7 * DAY)
        act1 = sum(1 for u in us if now - u.get("last", 0) < DAY)
        act7 = sum(1 for u in us if now - u.get("last", 0) < 7 * DAY)
        langs = {}
        for u in us:
            langs[u.get("lang") or "?"] = langs.get(u.get("lang") or "?", 0) + 1
        top_langs = ", ".join("{} {}".format(k, v) for k, v in sorted(langs.items(), key=lambda x: -x[1])[:4]) or "—"
        return (
            "<b>🛡 Адмін-панель · Мисливець Брам</b>\n\n"
            "<b>Гравці</b>\n"
            "Усього: <b>{total}</b> · заблокували бота: {blocked}\n"
            "Нових: за добу <b>{new1}</b> · за тиждень {new7}\n"
            "Активних: за добу <b>{act1}</b> · за тиждень {act7}\n"
            "Мови: {langs}\n\n"
            "<b>Бот</b>\n"
            "Працює: {uptime} · оброблено оновлень: {handled} · помилок: {errors}\n"
            "Оновлено: {now}"
        ).format(total=total, blocked=blocked, new1=new1, new7=new7, act1=act1, act7=act7,
                 langs=html.escape(top_langs), uptime=fmt_dur(now - STARTED_AT),
                 handled=self.handled, errors=self.errors, now=time.strftime("%d.%m %H:%M:%S"))

    def recent_text(self, n=15):
        rows = sorted(self.users.items(), key=lambda kv: -kv[1].get("last", 0))[:n]
        if not rows:
            return "<b>👥 Останні гравці</b>\n\nПоки нікого. Поділись посиланням t.me/myslyvets_bram_bot"
        lines = ["<b>👥 Останні гравці</b> (до {}):\n".format(n)]
        for uid, u in rows:
            nick = "@" + u["username"] if u.get("username") else ""
            lines.append("• <a href=\"tg://user?id={}\">{}</a> {} — {} назад{}".format(
                uid, html.escape(u.get("name") or str(uid)), html.escape(nick),
                fmt_dur(time.time() - u.get("last", 0)), " · 🚫" if u.get("blocked") else ""))
        return "\n".join(lines)

    def status_text(self):
        size = USERS_FILE.stat().st_size if USERS_FILE.exists() else 0
        return (
            "<b>⚙️ Стан бота</b>\n\n"
            "PID: <code>{pid}</code>\n"
            "Працює: {uptime} (з {since})\n"
            "Оброблено оновлень: {handled} · помилок: {errors}\n"
            "Файл гравців: {size} КБ\n"
            "Адміни: {admins}\n\n"
            "Перезапуск на Mac: <code>bash ~/codes/myslyvets-bram/bot/stop.sh && bash ~/codes/myslyvets-bram/bot/start.sh</code>"
        ).format(pid=os.getpid(), uptime=fmt_dur(time.time() - STARTED_AT),
                 since=time.strftime("%d.%m %H:%M", time.localtime(STARTED_AT)),
                 handled=self.handled, errors=self.errors, size=round(size / 1024, 1),
                 admins=", ".join("<code>{}</code>".format(i) for i in sorted(self.ids)))

    # ---------- клавіатури ----------
    @staticmethod
    def panel_kb():
        return {"inline_keyboard": [
            [{"text": "🔄 Оновити", "callback_data": "adm:home"}, {"text": "👥 Гравці", "callback_data": "adm:users"}],
            [{"text": "📣 Розсилка", "callback_data": "adm:bc"}, {"text": "⚙️ Стан бота", "callback_data": "adm:status"}],
            [{"text": "📁 Експорт гравців", "callback_data": "adm:export"}],
        ]}

    @staticmethod
    def back_kb():
        return {"inline_keyboard": [[{"text": "← До панелі", "callback_data": "adm:home"}]]}

    # ---------- дії ----------
    def show(self, chat_id, text, kb, edit_msg=None):
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True, "reply_markup": kb}
        if edit_msg:
            params["message_id"] = edit_msg
            try:
                self.call("editMessageText", params)
                return
            except Exception as err:
                if "not modified" in str(err):
                    return
        params.pop("message_id", None)
        self.call("sendMessage", params)

    def open_panel(self, chat_id, edit_msg=None):
        self.show(chat_id, self.stats_text(), self.panel_kb(), edit_msg)

    def on_command(self, msg, command):
        """Повертає True, якщо повідомлення оброблене адмінкою."""
        user = msg.get("from") or {}
        if not self.is_admin(user.get("id")) or msg["chat"].get("type") != "private":
            return False
        chat_id = msg["chat"]["id"]
        state = self.pending.get(user["id"])
        payload = text_payload(msg) if command == "/start" else ""
        if command in ("/admin", "/stats") or payload == "admin":
            self.pending.pop(user["id"], None)
            self.open_panel(chat_id)
            return True
        if payload.startswith("give_"):
            self.give(chat_id, payload)
            return True
        if command == "/cancel" and state:
            self.pending.pop(user["id"], None)
            self.call("sendMessage", {"chat_id": chat_id, "text": "Скасовано.", "reply_markup": self.back_kb()})
            return True
        if state and state.get("mode") == "broadcast" and not command:
            self.pending[user["id"]] = {"mode": "confirm", "chat": chat_id, "msg": msg["message_id"]}
            self.call("sendMessage", {"chat_id": chat_id, "text": "Так виглядатиме розсилка 👇"})
            self.call("copyMessage", {"chat_id": chat_id, "from_chat_id": chat_id, "message_id": msg["message_id"]})
            n = sum(1 for u in self.users.values() if not u.get("blocked"))
            self.call("sendMessage", {"chat_id": chat_id, "parse_mode": "HTML",
                                      "text": "Надіслати це <b>{}</b> гравцям?".format(n),
                                      "reply_markup": {"inline_keyboard": [[
                                          {"text": "✅ Надіслати всім", "callback_data": "adm:bc_go"},
                                          {"text": "✖️ Скасувати", "callback_data": "adm:bc_no"}]]}})
            return True
        return False

    def on_callback(self, query):
        """Повертає True, якщо це кнопка адмінки."""
        data = query.get("data") or ""
        if not data.startswith("adm:"):
            return False
        user = query.get("from") or {}
        if not self.is_admin(user.get("id")):
            self.call("answerCallbackQuery", {"callback_query_id": query["id"], "text": "Немає доступу"})
            return True
        msg = query.get("message") or {}
        chat_id = msg.get("chat", {}).get("id")
        mid = msg.get("message_id")
        action = data[4:]
        note = None
        if action == "home":
            self.open_panel(chat_id, mid)
            note = "Оновлено"
        elif action == "users":
            self.show(chat_id, self.recent_text(), self.back_kb(), mid)
        elif action == "status":
            self.show(chat_id, self.status_text(), self.back_kb(), mid)
        elif action == "export":
            self.save(force=True)
            rows = ["id;ім’я;username;мова;перший_візит;останній_візит;старти;повідомлення;заблокував"]
            for uid, u in sorted(self.users.items(), key=lambda kv: kv[1].get("first", 0)):
                rows.append(";".join(str(x).replace(";", ",") for x in [
                    uid, u.get("name", ""), u.get("username", ""), u.get("lang", ""),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(u.get("first", 0))),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(u.get("last", 0))),
                    u.get("starts", 0), u.get("msgs", 0), "так" if u.get("blocked") else ""]))
            self.send_document(chat_id, "gravtsi.csv", "﻿" + "\n".join(rows))
            note = "Файл надіслано"
        elif action == "bc":
            if self.broadcasting:
                note = "Розсилка вже йде"
            else:
                self.pending[user["id"]] = {"mode": "broadcast"}
                self.show(chat_id, "<b>📣 Розсилка</b>\n\nНадішли наступним повідомленням те, що треба розіслати: "
                          "текст, фото, відео чи стікер — усе піде як є, з форматуванням.\n\n/cancel — скасувати.",
                          self.back_kb(), mid)
        elif action == "bc_no":
            self.pending.pop(user["id"], None)
            self.show(chat_id, "Розсилку скасовано.", self.back_kb(), mid)
        elif action == "bc_go":
            state = self.pending.pop(user["id"], None)
            if not state or state.get("mode") != "confirm":
                note = "Немає що надсилати"
            elif self.broadcasting:
                note = "Розсилка вже йде"
            else:
                self.show(chat_id, "📣 Розсилка почалась… Звіт прийде сюди.", None, mid)
                threading.Thread(target=self.broadcast, args=(chat_id, state["chat"], state["msg"]), daemon=True).start()
        self.call("answerCallbackQuery", {"callback_query_id": query["id"], "text": note} if note else {"callback_query_id": query["id"]})
        return True

    def broadcast(self, report_chat, from_chat, message_id):
        self.broadcasting = True
        ok = fail = blocked = 0
        started = time.time()
        targets = [uid for uid, u in list(self.users.items()) if not u.get("blocked")]
        for i, uid in enumerate(targets):
            try:
                self.call("copyMessage", {"chat_id": uid, "from_chat_id": from_chat, "message_id": message_id})
                ok += 1
            except Exception as err:
                text = str(err)
                if "403" in text or "blocked" in text or "deactivated" in text or "chat not found" in text:
                    blocked += 1
                    with self.lock:
                        if uid in self.users:
                            self.users[uid]["blocked"] = 1
                            self.dirty = True
                elif "429" in text:
                    time.sleep(5)
                    fail += 1
                else:
                    fail += 1
            if i % 25 == 24:
                time.sleep(1.1)
        self.save(force=True)
        self.broadcasting = False
        self.log("Розсилка: {} доставлено, {} заблокували, {} помилок".format(ok, blocked, fail))
        self.call("sendMessage", {"chat_id": report_chat, "parse_mode": "HTML", "reply_markup": self.back_kb(),
                                  "text": "<b>📣 Розсилку завершено</b> за {}\n\n✅ Доставлено: <b>{}</b>\n🚫 Заблокували бота: {}\n⚠️ Помилки: {}".format(
                                      fmt_dur(time.time() - started), ok, blocked, fail)})

    # ---------- подарунки з веб-адмінки ----------
    def give(self, chat_id, payload):
        """payload: give_<to>_<parts>; to=0 — усім. parts: g/c/e/h/m/s + число, i + (рідкість*10+слот)."""
        m = GIVE_RE.match(payload)
        if not m:
            self.call("sendMessage", {"chat_id": chat_id, "text": "Не вдалося прочитати подарунок. Сформуй його ще раз в адмін-панелі гри."})
            return
        to, parts = int(m.group(1)), m.group(2)
        gid = "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(8))
        url = "{}{}gift={}.{}.{}".format(self.webapp_url, "&" if "?" in self.webapp_url else "?", parts, gid, to)
        desc = gift_text(parts)
        targets = [uid for uid, u in list(self.users.items()) if not u.get("blocked")] if to == 0 else [to]
        self.call("sendMessage", {"chat_id": chat_id, "parse_mode": "HTML",
                                  "text": "🎁 Надсилаю {} {}:\n{}".format(
                                      "<b>усім</b> гравцям" if to == 0 else "гравцю", "({})".format(len(targets)) if to == 0 else "<code>{}</code>".format(to), desc)})
        threading.Thread(target=self.deliver_gift, args=(chat_id, targets, url, desc), daemon=True).start()

    def deliver_gift(self, report_chat, targets, url, desc):
        ok = fail = blocked = 0
        text = "🎁 <b>Подарунок від Системи</b>\n\n{}\n\nНатисни «Забрати» — дари чекатимуть у пошті гри.".format(desc)
        kb = {"inline_keyboard": [[{"text": "🎁 Забрати", "web_app": {"url": url}}]]}
        for i, uid in enumerate(targets):
            try:
                self.call("sendMessage", {"chat_id": uid, "parse_mode": "HTML", "text": text, "reply_markup": kb})
                ok += 1
            except Exception as err:
                e = str(err)
                if "403" in e or "blocked" in e or "deactivated" in e:
                    blocked += 1
                    with self.lock:
                        if uid in self.users:
                            self.users[uid]["blocked"] = 1
                            self.dirty = True
                else:
                    fail += 1
                    if "429" in e:
                        time.sleep(5)
            if i % 25 == 24:
                time.sleep(1.1)
        self.save(force=True)
        self.log("Подарунок: {} доставлено, {} заблокували, {} помилок".format(ok, blocked, fail))
        note = ""
        if len(targets) == 1 and not ok:
            note = "\n\nГравець ще не запускав бота або заблокував його — Telegram не дає написати першим." if blocked or fail else ""
        self.call("sendMessage", {"chat_id": report_chat, "parse_mode": "HTML", "reply_markup": self.back_kb(),
                                  "text": "<b>🎁 Видачу завершено</b>\n\n✅ Доставлено: <b>{}</b>\n🚫 Недоступні: {}\n⚠️ Помилки: {}{}".format(ok, blocked, fail, note)})

    def send_document(self, chat_id, filename, content):
        self.call("sendDocument", {"chat_id": chat_id, "caption": "Гравці «Мисливця Брам»"},
                  files={"document": (filename, content.encode("utf-8"), "text/csv")})


GIVE_RE = re.compile(r"^give_(\d{1,15})_((?:[gcehms]\d{1,8}|i\d{1,2})+)$")
GIFT_NAMES = {"g": "🪙 Золото", "c": "💎 Кристали", "e": "⚡ Енергія", "h": "❤️ Зілля HP", "m": "🔷 Зілля мани", "s": "✨ Осколки мани"}
RARITIES = ["Звичайне", "Незвичайне", "Рідкісне", "Епічне", "Легендарне", "Міфічне"]
SLOTS = ["зброя", "шолом", "нагрудник", "поножі", "чоботи", "рукавиці", "намисто", "сережка", "перстень"]


def text_payload(msg):
    bits = (msg.get("text") or "").split(maxsplit=1)
    return bits[1].strip() if len(bits) > 1 else ""


def gift_text(parts):
    lines = []
    for k, v in re.findall(r"([gcehmsi])(\d+)", parts):
        v = int(v)
        if k == "i":
            r, si = divmod(v, 10)
            lines.append("🗡 Предмет: {} ({})".format(RARITIES[r] if r < len(RARITIES) else "?", SLOTS[si] if si < len(SLOTS) else "?"))
        elif v > 0:
            lines.append("{}: <b>{:,}</b>".format(GIFT_NAMES[k], v).replace(",", " "))
    return "\n".join(lines) or "—"


def fmt_dur(sec):
    sec = int(max(0, sec))
    d, sec = divmod(sec, DAY)
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    if d:
        return "{} д {} год".format(d, h)
    if h:
        return "{} год {} хв".format(h, m)
    if m:
        return "{} хв".format(m)
    return "{} с".format(s)
