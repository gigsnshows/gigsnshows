#!/bin/zsh
# Full collection from this Mac, then upload. District and BookMyShow block cloud
# servers, so GitHub's own scheduled run can't refresh them; this fills that gap.
# Scheduled by ~/Library/LaunchAgents/com.gigsnshows.collect.plist (07:30 and 17:30;
# if the Mac is asleep then, it runs on wake). Log: ~/Library/Logs/gigsnshows-collect.log

# Everything sits in main() so zsh reads the whole script before running it: the pull
# below can update this very file, which would otherwise change it mid-run.
main() {
  set -e
  cd "$(dirname "$0")"
  export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
  export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/gigsnshows_deploy -o IdentitiesOnly=yes"
  local REPO=git@github.com:gigsnshows/gigsnshows.git
  local BOT=(-c user.name=listings-bot -c user.email=bot@users.noreply.github.com)

  echo "=== $(date) ==="
  # Listings and share pages are rebuilt from scratch every run; clear any left by a run
  # that didn't finish, so they can't block the update below.
  git checkout -- data s 2>/dev/null || true
  git clean -fdq s
  git "${BOT[@]}" pull --rebase -X theirs --quiet "$REPO" main   # latest code and listings
  python3 run.py
  git add data/events.json s
  if git diff --cached --quiet; then echo "no changes"; return 0; fi
  git "${BOT[@]}" commit --quiet -m "Refresh listings $(date +%F) (Mac)"
  for attempt in 1 2 3; do
    git push --quiet "$REPO" main && { echo "uploaded"; return 0; }
    # GitHub's own refresh landed meanwhile; keep this run's fuller file on top of it.
    git "${BOT[@]}" pull --rebase -X theirs --quiet "$REPO" main
  done
  return 1
}
main "$@"
exit $?
