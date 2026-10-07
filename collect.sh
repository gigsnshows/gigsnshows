#!/bin/bash
# Collect listings and upload them. Runs on the AWS server (cron, 07:00 and 17:00 IST:
# everything except BookMyShow) and on the Mac (collect-local.sh: BookMyShow only).
# Set COLLECTOR (aws / mac) and PYTHON before calling; sources.yaml's runs_on decides
# which sources each one reads. Runs from its own clone, which it resets to GitHub's copy.
#
# Two collectors can finish at once. If GitHub has moved on when this one uploads, it
# starts again from the newer listings and merges its own fresh results back in
# (run.py --remerge), so neither machine's results overwrite the other's.

# Everything sits in main() so bash reads the whole script before running it: the reset
# below can update this very file, which would otherwise change it mid-run.
HERE="$(cd "$(dirname "$0")" && pwd)"
main() {
  set -e
  cd "$HERE"
  local REPO=git@github.com:gigsnshows/gigsnshows.git
  local BOT=(-c user.name=listings-bot -c user.email=bot@users.noreply.github.com)
  export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/gigsnshows_deploy -o IdentitiesOnly=yes"
  : "${COLLECTOR:?set COLLECTOR to aws or mac}" "${PYTHON:=python3}"

  echo "=== $(date) on $COLLECTOR ==="
  git fetch --quiet "$REPO" main
  git reset --quiet --hard FETCH_HEAD   # latest code and listings
  git clean -fdq s
  "$PYTHON" run.py
  for attempt in 1 2 3 4 5; do
    git add data/events.json data/health.json s
    if git diff --cached --quiet; then echo "no changes"; return 0; fi
    git "${BOT[@]}" commit --quiet -m "Refresh listings $(date +%F) ($COLLECTOR)"
    git push --quiet "$REPO" HEAD:main && { echo "uploaded"; return 0; }
    echo "another collector uploaded first; merging into its listings"
    git fetch --quiet "$REPO" main
    git reset --quiet --hard FETCH_HEAD
    git clean -fdq s
    "$PYTHON" run.py --remerge
  done
  return 1
}
main "$@"
exit $?
