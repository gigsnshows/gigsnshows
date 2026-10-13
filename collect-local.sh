#!/bin/zsh
# The Mac's collector: BookMyShow only, since it refuses cloud servers (everything else is
# read by the AWS server). Scheduled by ~/Library/LaunchAgents/com.gigsnshows.collect.plist
# at 09:35, 13:35 and 17:35; if the Mac is asleep then, it runs on wake. If the Mac stays shut,
# BookMyShow's shows simply stay as last collected, dropping off as their dates pass.
# Log: ~/Library/Logs/gigsnshows-collect.log
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export COLLECTOR=mac PYTHON=python3
export GNS_BMS_PAGES="$HOME/.gigsnshows-bms-pages.json"  # what the BookMyShow reader has read: kept outside the clone, which is reset every run
exec /bin/bash "${0:A:h}/collect.sh"
