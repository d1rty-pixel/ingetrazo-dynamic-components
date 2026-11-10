#!/usr/bin/env bash
# Copy the extension into IngeTrazo's plugins folder.
#
# IngeTrazo does not follow the repository: whatever sits in its plugins folder
# is what runs, so run this after every change, then restart IngeTrazo.
#
#   ./install.sh [plugins-dir]
#
# Without an argument it picks the plugins folder of IngeTrazo for Windows when
# run from WSL (%APPDATA%\IngeTrazo\plugins), else the Linux one. The previous
# copy is kept as .dynamic_components.bak next to it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -ge 1 ]; then
    plugins="$1"
elif command -v cmd.exe >/dev/null 2>&1 && command -v wslpath >/dev/null 2>&1 \
        && appdata="$(cmd.exe /c 'echo %APPDATA%' 2>/dev/null | tr -d '\r')" \
        && [ -n "$appdata" ] && [ "$appdata" != '%APPDATA%' ]; then
    plugins="$(wslpath "$appdata")/IngeTrazo/plugins"
else
    plugins="${XDG_DATA_HOME:-$HOME/.local/share}/ingetrazo/plugins"
fi

mkdir -p "$plugins"
target="$plugins/dynamic_components"
rm -rf "$plugins/.dynamic_components.bak"
[ -e "$target" ] && mv "$target" "$plugins/.dynamic_components.bak"
mkdir "$target"
cp -r "$here/dynamic_components/." "$target/"
find "$target" -name __pycache__ -prune -exec rm -rf {} +
echo "Installed into $target - restart IngeTrazo."
