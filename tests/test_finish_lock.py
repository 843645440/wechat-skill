import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_runtime.py"
WORKER = r'''
import importlib.util
from pathlib import Path
import sys
import time
from types import SimpleNamespace

script, directory, token, mode = sys.argv[1:]
root = Path(directory)
spec = importlib.util.spec_from_file_location("locked_runtime", script)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

def critical(args):
    active = root / "active"
    with active.open("x") as stream:
        stream.write(token)
    try:
        (root / (token + ".entered")).touch()
        if mode == "raise":
            raise RuntimeError("intentional failure")
        deadline = time.monotonic() + 15
        while not (root / (token + ".release")).exists():
            if time.monotonic() > deadline:
                raise TimeoutError("parent did not release worker")
            time.sleep(0.01)
    finally:
        active.unlink()
    return {"status": "ok"}

runtime._cmd_finish = critical
(root / (token + ".ready")).touch()
try:
    runtime.cmd_finish(SimpleNamespace(job=str(root / "job.json")))
except RuntimeError:
    if mode != "raise":
        raise
'''


class FinishLockTests(unittest.TestCase):
    def wait_for(self, path, process):
        deadline = time.monotonic() + 10
        while not path.exists():
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                self.fail(f"worker exited {process.returncode}: {stdout}\n{stderr}")
            if time.monotonic() > deadline:
                self.fail(f"timed out waiting for {path.name}")
            time.sleep(0.01)

    def start(self, root, token, mode="normal"):
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        process = subprocess.Popen([sys.executable, "-c", WORKER, str(RUNTIME), str(root), token, mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        self.addCleanup(self.stop, process)
        return process

    def stop(self, process):
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)

    def assert_success(self, process):
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(0, process.returncode, stdout + stderr)

    def test_runtime_help_works_on_current_platform(self):
        result = subprocess.run([sys.executable, str(RUNTIME), "--help"], text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("finish", result.stdout)

    def test_three_processes_keep_one_stable_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.start(root, "first")
            self.wait_for(root / "first.entered", first)
            second = self.start(root, "second")
            self.wait_for(root / "second.ready", second)
            (root / "first.release").touch()
            self.wait_for(root / "second.entered", second)
            self.assert_success(first)
            self.assertTrue((root / ".finish.lock").is_file(), "retain the lock file while a waiter owns it")
            third = self.start(root, "third")
            self.wait_for(root / "third.ready", third)
            time.sleep(0.15)
            self.assertFalse((root / "third.entered").exists())
            self.assertIsNone(third.poll())
            (root / "second.release").touch()
            self.wait_for(root / "third.entered", third)
            (root / "third.release").touch()
            self.assert_success(second)
            self.assert_success(third)
            self.assertTrue((root / ".finish.lock").is_file())

    def test_exception_releases_lock_for_next_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failing = self.start(root, "failing", "raise")
            self.assert_success(failing)
            following = self.start(root, "following")
            self.wait_for(root / "following.entered", following)
            (root / "following.release").touch()
            self.assert_success(following)

    def test_process_exit_releases_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self.start(root, "first")
            self.wait_for(root / "first.entered", first)
            first.terminate()
            first.communicate(timeout=5)
            # This marker belongs to our synthetic critical section, not the lock.
            (root / "active").unlink()
            following = self.start(root, "following")
            self.wait_for(root / "following.entered", following)
            (root / "following.release").touch()
            self.assert_success(following)

    def test_different_jobs_do_not_block_each_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_root = Path(tmp) / "one"
            second_root = Path(tmp) / "two"
            os.makedirs(first_root)
            os.makedirs(second_root)
            first = self.start(first_root, "first")
            self.wait_for(first_root / "first.entered", first)
            second = self.start(second_root, "second")
            self.wait_for(second_root / "second.entered", second)
            (first_root / "first.release").touch()
            (second_root / "second.release").touch()
            self.assert_success(first)
            self.assert_success(second)


if __name__ == "__main__":
    unittest.main()
