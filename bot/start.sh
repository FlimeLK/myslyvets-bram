#!/bin/bash
# Запускає бота @myslyvets_bram_bot у фоні. Перший запуск попросить токен від @BotFather.
cd "$(dirname "$0")" || exit 1

PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "Не знайдено python3. Встанови його: xcode-select --install  (або brew install python)"
  exit 1
fi

if ! grep -q '^BOT_TOKEN=..*:..*' .env 2>/dev/null; then
  echo "Встав токен бота від @BotFather (повідомлення «Use this token to access the HTTP API»)."
  printf "Токен не буде видно під час вставки. Встав і натисни Enter: "
  read -rs TOKEN
  echo
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
  case "$TOKEN" in
    *:*) ;;
    *) echo "Це не схоже на токен (він має вигляд 1234567890:ABC...). Запусти скрипт ще раз."; exit 1 ;;
  esac
  umask 077
  printf 'BOT_TOKEN=%s\n' "$TOKEN" > .env
  echo "Токен збережено в bot/.env (у git він не потрапить)."
fi

if [ -f bot.pid ] && kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "Бот уже працює (PID $(cat bot.pid)). Перезапуск: bash bot/stop.sh && bash bot/start.sh"
  exit 0
fi

: >> bot.log
FROM=$(( $(wc -l < bot.log) + 1 ))
nohup "$PY" bot.py >> bot.log 2>&1 &
echo $! > bot.pid
disown 2>/dev/null || true

OK=""
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  sleep 1
  if tail -n +"$FROM" bot.log | grep -q "запущено"; then OK=1; break; fi
  kill -0 "$(cat bot.pid)" 2>/dev/null || break
done

if [ -n "$OK" ]; then
  echo "Готово: бот працює у фоні (PID $(cat bot.pid)). Відкрий https://t.me/myslyvets_bram_bot"
  echo "Лог: $(pwd)/bot.log  ·  Зупинити: bash $(pwd)/stop.sh"
elif kill -0 "$(cat bot.pid)" 2>/dev/null; then
  echo "Бот запущений, але ще не достукався до Telegram. Останнє в лозі:"
  tail -n +"$FROM" bot.log | tail -n 5
  echo "Він пробуватиме далі сам. Лог: $(pwd)/bot.log"
else
  echo "Бот не запустився:"
  tail -n +"$FROM" bot.log | tail -n 15
  rm -f bot.pid
  if tail -n +"$FROM" bot.log | grep -q "не прийняв токен"; then
    rm -f .env
    echo "Токен неправильний. Запусти bash bot/start.sh ще раз і встав його знову."
  fi
  exit 1
fi
