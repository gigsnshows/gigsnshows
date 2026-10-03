#!/bin/zsh
# The Mac's collector: BookMyShow only, since it refuses cloud servers (everything else is
# read by the AWS server). Scheduled by ~/Library/LaunchAgents/com.gigsnshows.collect.plist
# at 07:30 and 17:30; if the Mac is asleep then, it runs on wake. If the Mac stays shut,
# BookMyShow's shows simply stay as last collected, dropping off as their dates pass.
# Log: ~/Library/Logs/gigsnshows-collect.log
export PATH="/Library/Frameworks/Python.framework/Versions/3.14/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export COLLECTOR=mac PYTHON=python3
exec /bin/bash "${0:A:h}/collect.sh"
