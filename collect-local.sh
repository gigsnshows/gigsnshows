#!/bin/zsh
# Full collection from this Mac, then upload. District and BookMyShow block cloud
# servers, so GitHub's own scheduled run can't refresh them; this fills that gap.
# Scheduled by ~/Library/LaunchAgents/com.gigsnshows.collect.plist (07:30 and 17:30;
# if the Mac is asleep then, it runs on wake). Log: ~/Library/Logs/gigsnshows-collect.log
set -e
cd "$(dirname "$0")"
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/gigsnshows_deploy -o IdentitiesOnly=yes"
REPO=git@github.com:gigsnshows/gigsnshows.git
BOT=(-c user.name=listings-bot -c user.email=bot@users.noreply.github.com)

echo "=== $(date) ==="
git "${BOT[@]}" pull --rebase -X theirs --quiet "$REPO" main   # latest code and listings
python3 run.py
git add data/events.json
if git diff --cached --quiet; then echo "no changes"; exit 0; fi
git "${BOT[@]}" commit --quiet -m "Refresh listings $(date +%F) (Mac)"
for attempt in 1 2 3; do
  git push --quiet "$REPO" main && { echo "uploaded"; exit 0; }
  # GitHub's own refresh landed meanwhile; keep this run's fuller file on top of it.
  git "${BOT[@]}" pull --rebase -X theirs --quiet "$REPO" main
done
exit 1
