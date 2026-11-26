#!/bin/bash
# Collect listings and upload them. Runs on the AWS server (cron, 09:30, 13:30 and 17:30 IST, so listings are live by 10am, 2pm and 6pm:
# everything except BookMyShow) and on the Mac (collect-local.sh: BookMyShow only).
# Set COLLECTOR (aws / proxy / mac) and PYTHON before calling; sources.yaml's runs_on decides
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
  local ALT=ssh://git@ssh.github.com:443/gigsnshows/gigsnshows.git  # the same, over port 443, for networks that block or drop port 22
  local BOT=(-c user.name=listings-bot -c user.email=bot@users.noreply.github.com)
  export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/gigsnshows_deploy -o IdentitiesOnly=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o \"UserKnownHostsFile=$HERE/github_known_hosts $HOME/.ssh/known_hosts\""  # give up on a dead connection instead of hanging (the Mac's 2 Nov 13:35 run sat silent after its first fetch)
  : "${COLLECTOR:?set COLLECTOR to aws, proxy or mac}" "${PYTHON:=python3}"
  # Settings kept on the machine, never in the repo: BMS_PROXY (the proxy account BookMyShow is read through) lives here.
  if [ -f "$HOME/.gigsnshows.env" ]; then set -a; . "$HOME/.gigsnshows.env"; set +a; fi

  # GitHub sometimes drops a connection for a moment ("early EOF", "Broken pipe"). With set -e that used to end the whole run
  # and throw away 30 minutes of results (the Mac's 15 Oct 09:36 run), so network steps are tried a few times first.
  # Port 22 first, then port 443 (the Mac's 18 Nov 09:35 run timed out on port 22 four times and lost its upload).
  # Last resort: the Mac's network sometimes cannot look up GitHub's name at all ("Could not resolve hostname", 20-23 Nov)
  # while BookMyShow loads fine. Ask Cloudflare's, then Google's, lookup service over HTTPS (by their numeric addresses,
  # so no name lookup is needed) and connect to GitHub by address, still checking GitHub's published key (HostKeyAlias).
  ipof() {
    local u
    for u in "https://1.1.1.1/dns-query?name=$1&type=A" "https://8.8.8.8/resolve?name=$1&type=A"; do
      curl -s --max-time 15 -H 'accept: application/dns-json' "$u" | "$PYTHON" -c 'import json, sys
for a in json.load(sys.stdin).get("Answer", []):
    if a.get("type") == 1: print(a["data"]); break' 2>/dev/null | grep -E '^[0-9]{1,3}(\.[0-9]{1,3}){3}$' && return 0
    done
    return 1
  }
  remote() {
    local verb=$1 ip; shift
    git "$verb" --quiet "$REPO" "$@" && return 0
    echo "GitHub on port 22 failed; trying port 443"
    git "$verb" --quiet "$ALT" "$@" && return 0
    ip="$(ipof ssh.github.com)" || { echo "could not look up GitHub's address either"; return 1; }
    echo "trying GitHub by its address ($ip), looked up over HTTPS"
    GIT_SSH_COMMAND="$GIT_SSH_COMMAND -o HostKeyAlias=ssh.github.com" git "$verb" --quiet "ssh://git@$ip:443/gigsnshows/gigsnshows.git" "$@"
  }
  net() { local i; for i in 1 2 3 4; do "$@" && return 0; echo "network step failed ($*), try $i of 4"; sleep $((i * 20)); done; return 1; }

  echo "=== $(date) on $COLLECTOR ==="
  net remote fetch main
  git reset --quiet --hard FETCH_HEAD   # latest code and listings
  git clean -fdq
  "$PYTHON" run.py
  for attempt in 1 2 3 4 5; do
    git add -A  # listings, health record, share pages and the search pages (shows/, city folders, sitemap)
    if git diff --cached --quiet; then echo "no changes"; return 0; fi
    git "${BOT[@]}" commit --quiet -m "Refresh listings $(date +%F) ($COLLECTOR)"
    remote push HEAD:main && { echo "uploaded"; "$PYTHON" indexnow.py HEAD~1 || true; return 0; }
    echo "upload did not go through (another collector uploaded first, or the connection dropped); merging into the latest listings"
    # What this machine's sitemap reader has already read (data/district_pages.json on the server, data/bms_pages.json
    # on the Mac) would be lost by the reset below, and the reader would start again from nothing next time.
    local MEMORY=data/district_pages.json; [ "$COLLECTOR" = mac ] && MEMORY="${GNS_BMS_PAGES:-data/bms_pages.json}"  # (outside the clone when GNS_BMS_PAGES is set)
    local KEEP; KEEP="$(mktemp)"; cp "$MEMORY" "$KEEP" 2>/dev/null || : > "$KEEP"
    net remote fetch main
    git reset --quiet --hard FETCH_HEAD
    git clean -fdq
    [ -s "$KEEP" ] && cp "$KEEP" "$MEMORY"; rm -f "$KEEP"
    "$PYTHON" run.py --remerge
  done
  return 1
}
main "$@"
exit $?
