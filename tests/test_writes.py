"""A write cut short (a crash, Ctrl-C, a full disk) must leave the file as it was: every tool writes a
temp file next to it and swaps it in, so a half-written state file never breaks the next run."""
import json
import os
import shutil
import tempfile
import unittest

from _load import load

WRITERS = [  # (skill folder, module, the function that writes its JSON)
    ("bharat-news", "news", "save_state"),
    ("bharat-insider", "insider", "save_state"),
    ("bharat-entry", "entry", "write_json"),
    ("bharat-exit", "exit", "write_json"),
    ("bharat-scanner", "scan", "write_json"),
    ("bharat-timemachine", "timemachine", "_write"),
]


class InterruptedWrite(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_a_write_that_fails_halfway_keeps_the_old_file(self):
        for folder, mod, fn in WRITERS:
            write = getattr(load(folder, mod), fn)
            path = os.path.join(self.d, "state", mod + ".json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                json.dump({"kept": True}, fh)
            # json.dump streams: the long "a" goes out, then object() cannot be written
            with self.assertRaises(TypeError):
                write(path, {"a": "x" * 20000, "b": object()})
            with open(path) as fh:
                self.assertEqual(json.load(fh), {"kept": True}, "%s.%s" % (mod, fn))

    def test_a_write_makes_its_folder_and_leaves_no_temp_file(self):
        for folder, mod, fn in WRITERS:
            write = getattr(load(folder, mod), fn)
            path = os.path.join(self.d, mod, "out.json")
            write(path, {"ok": 1})
            with open(path) as fh:
                self.assertEqual(json.load(fh), {"ok": 1}, mod)
            self.assertEqual(os.listdir(os.path.dirname(path)), ["out.json"], mod)


if __name__ == "__main__":
    unittest.main()
