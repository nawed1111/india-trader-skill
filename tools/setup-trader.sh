#!/bin/bash
# Set up the India Trader skills and Zerodha's Kite MCP server in one folder.
# An external SSD works: the folder can live anywhere. macOS or Linux.
#
#   bash setup-trader.sh /Volumes/MySSD/trader
#
# It makes the folder, clones and builds zerodha/kite-mcp-server, installs the
# 11 skills for that folder, writes a paper-trading config, and adds a "kite"
# server to Claude Desktop's config with placeholder keys and the order tools
# switched off. Safe to run again: nothing is cloned twice, your keys and other
# servers are kept, and Claude's config is backed up first.
#
# Your Kite key and secret go in Claude's config file afterwards, typed by
# you. Never in this repo, never in a chat.
set -euo pipefail

usage() { echo "Usage: bash setup-trader.sh /path/to/folder   (for example /Volumes/MySSD/trader)"; }
[ $# -eq 1 ] || { usage; exit 2; }
W="${1%/}"
PARENT="$(dirname "$W")"
# an unplugged SSD: mkdir -p would quietly make /Volumes/<name> on the internal disk
[ -d "$PARENT" ] || { echo "No folder at $PARENT. If it is an SSD, plug it in and check its name with: ls /Volumes"; exit 1; }

command -v git >/dev/null     || { echo "git is missing. macOS: xcode-select --install"; exit 1; }
command -v go >/dev/null      || { echo "Go is missing (1.21 or newer). macOS: brew install go, or go.dev/dl"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is missing. macOS: xcode-select --install"; exit 1; }

case "$(uname -s)" in
  Darwin) DEFAULT_CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
  Linux)  DEFAULT_CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
  *)      DEFAULT_CFG="" ;;
esac
CFG="${CLAUDE_DESKTOP_CONFIG:-$DEFAULT_CFG}"
[ -n "$CFG" ] || { echo "Not macOS or Linux: follow the manual steps in the README (Live trading setup)"; exit 1; }

echo "== 1. Folder: $W"
mkdir -p "$W/.claude/skills" "$W/trader"
cd "$W"

echo "== 2. Zerodha's Kite MCP server: clone and build"
[ -d kite-mcp-server ] || git clone https://github.com/zerodha/kite-mcp-server
(cd kite-mcp-server && go build -o kite-mcp-server)
chmod +x kite-mcp-server/kite-mcp-server   # exFAT drives can drop the run permission

echo "== 3. The India Trader skills, installed for this folder"
if [ -d india-trader-skill ]; then
  git -C india-trader-skill pull -q --ff-only || echo "   (could not update india-trader-skill; using the copy you have)"
else
  git clone https://github.com/nawed1111/india-trader-skill
fi
cp -R india-trader-skill/bharat-* .claude/skills/
[ -f trader/config.json ] || cp india-trader-skill/bharat-budget/config.example.json trader/config.json

if [ -z "${INDIA_TRADER_SKIP_TESTS:-}" ]; then
  echo "== 4. Skill tests (offline, about 30 seconds)"
  (cd india-trader-skill && python3 -m unittest discover -s tests 2>&1 | tail -1) \
    || echo "   Tests did not pass: the lines above say which"
fi

echo "== 5. Claude Desktop config: $CFG"
mkdir -p "$(dirname "$CFG")"
if [ -f "$CFG" ]; then
  cp "$CFG" "$CFG.backup-$(date +%Y%m%d-%H%M%S)"
fi
CFG="$CFG" KITE_BIN="$W/kite-mcp-server/kite-mcp-server" python3 - <<'PY'
import json, os
p, exe = os.environ["CFG"], os.environ["KITE_BIN"]
try:
    with open(p) as fh:
        c = json.load(fh)
except FileNotFoundError:
    c = {}
servers = c.setdefault("mcpServers", {})
if "kite" in servers:
    servers["kite"]["command"] = exe   # keep the keys you already typed
else:
    servers["kite"] = {"command": exe, "env": {
        "APP_MODE": "stdio", "KITE_API_KEY": "PASTE_KEY_LATER", "KITE_API_SECRET": "PASTE_SECRET_LATER",
        "EXCLUDED_TOOLS": "place_order,modify_order,cancel_order"}}
with open(p, "w") as fh:
    json.dump(c, fh, indent=2)
print("   kite server set (order tools off until you delete EXCLUDED_TOOLS)")
PY

echo
echo "Done. Next:"
echo " 1. Put your Kite Connect key and secret in: $CFG"
echo " 2. Quit Claude Desktop completely and reopen it (macOS: allow access to the removable volume if asked)"
echo " 3. Claude Code (the claude command) keeps its own server list. Once the keys are in, copy kite across"
echo "    (pick kite from the list; after any change of keys, run claude mcp remove kite, then copy it again):"
echo "      claude mcp add-from-claude-desktop"
echo " 4. Use the skills: cd \"$W\" && claude, then /bharat-scanner"
