"""tools/setup-trader.sh, run for real against stand-in git and go (no network, no build)."""
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest

from _load import ROOT

SCRIPT = os.path.join(ROOT, "tools", "setup-trader.sh")

FAKE_GIT = """#!/bin/sh
# clone URL: make the folder a real clone would; anything else (pull) does nothing
if [ "$1" = clone ]; then
  dest=$(basename "$2")
  mkdir -p "$dest"
  case "$2" in *india-trader-skill*)
    mkdir -p "$dest/bharat-budget" "$dest/bharat-risk"
    echo '{"paper": true}' > "$dest/bharat-budget/config.example.json";;
  esac
fi
exit 0
"""
FAKE_GO = """#!/bin/sh
# go build -o NAME: leave an empty NAME behind
touch "$3"
"""


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class SetupScript(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.bin = os.path.join(self.d, "bin")
        os.mkdir(self.bin)
        for name, body in (("git", FAKE_GIT), ("go", FAKE_GO)):
            path = os.path.join(self.bin, name)
            with open(path, "w") as fh:
                fh.write(body)
            os.chmod(path, 0o755)
        self.ssd = os.path.join(self.d, "MySSD")
        os.mkdir(self.ssd)
        self.target = os.path.join(self.ssd, "trader")
        self.cfg = os.path.join(self.d, "home", "Claude", "claude_desktop_config.json")

    def tearDown(self):
        shutil.rmtree(self.d)

    def run_script(self, *args):
        env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ.get("PATH", ""),
                   HOME=os.path.join(self.d, "home"), CLAUDE_DESKTOP_CONFIG=self.cfg, INDIA_TRADER_SKIP_TESTS="1")
        return subprocess.run(["bash", SCRIPT] + list(args), env=env, capture_output=True, text=True)

    def kite(self):
        with open(self.cfg) as fh:
            return json.load(fh)

    def test_sets_up_the_folder_the_skills_and_the_kite_server(self):
        r = self.run_script(self.target)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        exe = os.path.join(self.target, "kite-mcp-server", "kite-mcp-server")
        self.assertTrue(os.stat(exe).st_mode & stat.S_IXUSR)
        self.assertTrue(os.path.isdir(os.path.join(self.target, ".claude", "skills", "bharat-risk")))
        with open(os.path.join(self.target, "trader", "config.json")) as fh:
            self.assertIs(json.load(fh)["paper"], True)
        kite = self.kite()["mcpServers"]["kite"]
        self.assertEqual(kite["command"], exe)
        self.assertEqual(kite["env"]["APP_MODE"], "stdio")
        self.assertEqual(kite["env"]["KITE_API_KEY"], "PASTE_KEY_LATER")
        self.assertEqual(kite["env"]["KITE_API_SECRET"], "PASTE_SECRET_LATER")
        self.assertEqual(kite["env"]["EXCLUDED_TOOLS"], "place_order,modify_order,cancel_order")
        # Claude Code keeps its own server list: the script says how to copy kite across, once the keys are in
        self.assertIn("claude mcp add-from-claude-desktop", r.stdout)

    def test_a_second_run_keeps_your_keys_and_other_servers_and_backs_up(self):
        os.makedirs(os.path.dirname(self.cfg))
        with open(self.cfg, "w") as fh:
            json.dump({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}, fh)
        self.assertEqual(self.run_script(self.target).returncode, 0)
        doc = self.kite()
        doc["mcpServers"]["kite"]["env"]["KITE_API_KEY"] = "typed-by-you"
        with open(self.cfg, "w") as fh:
            json.dump(doc, fh)
        r = self.run_script(self.target)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        doc = self.kite()
        self.assertEqual(doc["mcpServers"]["kite"]["env"]["KITE_API_KEY"], "typed-by-you")
        self.assertEqual(doc["mcpServers"]["other"], {"command": "x"})
        self.assertEqual(doc["theme"], "dark")
        backups = [f for f in os.listdir(os.path.dirname(self.cfg)) if ".backup-" in f]
        self.assertTrue(backups)

    def test_an_unplugged_drive_stops_before_making_anything(self):
        gone = os.path.join(self.d, "NotPlugged", "trader")
        r = self.run_script(gone)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ls /Volumes", r.stdout + r.stderr)
        self.assertFalse(os.path.exists(os.path.dirname(gone)))
        self.assertFalse(os.path.exists(self.cfg))

    def test_no_folder_given_prints_usage(self):
        r = self.run_script()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Usage", r.stdout + r.stderr)

    def test_the_readme_and_broker_skill_point_at_it(self):
        for path in ("README.md", os.path.join("bharat-broker", "SKILL.md")):
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("tools/setup-trader.sh", text, path)
            self.assertIn("claude mcp add-from-claude-desktop", text, path)


if __name__ == "__main__":
    unittest.main()
