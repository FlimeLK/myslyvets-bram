#!/bin/bash
# Мисливець Брам — одноразове налаштування:
#   1) публічний репозиторій FlimeLK/myslyvets-bram на GitHub,
#   2) GitHub Pages для гри: https://flimelk.github.io/myslyvets-bram/
#   3) запуск Telegram-бота @myslyvets_bram_bot на цьому Mac.
cd "$(dirname "$0")" || exit 1
OWNER="FlimeLK"
REPO="myslyvets-bram"
PAGES_URL="https://flimelk.github.io/myslyvets-bram/"

step() { printf '\n\033[1;36m▸ %s\033[0m\n' "$1"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$1"; }

chmod +x setup.sh bot/start.sh bot/stop.sh 2>/dev/null

step "1/3 Git-репозиторій"
if ! command -v git >/dev/null 2>&1; then
  warn "Немає git. Встанови Xcode Command Line Tools: xcode-select --install"
  exit 1
fi
if [ ! -d .git ]; then
  git init -q -b main
fi
git add -A
if ! git diff --cached --quiet 2>/dev/null; then
  git commit -q -m "Мисливець Брам: гра і Telegram-бот" \
    -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Qwq1fcKwKiAiUxzP5QqVE6" \
    || warn "Не вдалось зробити коміт (перевір git config user.name / user.email)."
fi

step "2/3 GitHub і GitHub Pages"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
    git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$OWNER/$REPO.git"
    git push -u origin main
  else
    gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push \
      --description "Мисливець Брам — українська RPG у Telegram"
  fi
  if gh api "repos/$OWNER/$REPO/pages" >/dev/null 2>&1; then
    echo "GitHub Pages уже ввімкнено."
  else
    gh api -X POST "repos/$OWNER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/" >/dev/null \
      && echo "GitHub Pages увімкнено." \
      || warn "Не вдалось увімкнути Pages автоматично: Settings → Pages → Deploy from a branch → main / (root)."
  fi
  echo "Гра з’явиться тут за 1–2 хвилини: $PAGES_URL"
else
  warn "Немає GitHub CLI або ти не залогінений у ньому."
  echo "Встанови й увійди:  brew install gh && gh auth login"
  echo "Потім запусти цей скрипт ще раз — він продовжить з цього місця."
  exit 1
fi

step "3/3 Telegram-бот"
exec bash bot/start.sh
