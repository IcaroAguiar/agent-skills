import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

MODULE = Path(__file__).with_name("inspect_checkout.py")
SPEC = importlib.util.spec_from_file_location("inspect_checkout", MODULE)
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


class CheckoutInventoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="task-closeout-test-")
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / "repo"
        self.repo.mkdir()
        self.git("init", "--initial-branch=main")
        self.write("file.txt", "original\n")
        self.commit()
        self.initial = self.git("rev-parse", "HEAD").strip()
        self.git("update-ref", "refs/remotes/origin/main", self.initial)

    def git(self, *args, check=True):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "-c", "commit.gpgsign=false", "-C", str(self.repo), *args],
            check=check, capture_output=True, text=True,
        ).stdout

    def write(self, path, value):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value)

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-m", "fixture")

    def advance_base(self):
        self.commit()
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD").strip())
        self.git("reset", "--hard", self.initial)

    def inspect(self, **kwargs):
        return inspector.inspect_checkout(self.repo, **kwargs)

    def test_clean_checkout_does_not_imply_worktree_is_abandoned(self):
        self.git("worktree", "add", "-b", "worker", str(Path(self.directory.name) / "worker"))
        result = self.inspect()
        self.assertEqual(result["dirty_paths"], 0)
        self.assertEqual(len(result["worktrees"]), 2)
        self.assertEqual(result["ownership_and_live_activity"], "not_checked")

    def test_change_already_present_in_base(self):
        self.write("file.txt", "integrated\n")
        self.advance_base()
        self.write("file.txt", "integrated\n")
        self.assertEqual(self.inspect()["changes"][0]["comparison"], "matches_base")

    def test_squash_equivalence_does_not_claim_branch_was_merged(self):
        self.git("checkout", "-b", "feature")
        self.write("file.txt", "feature result\n")
        self.commit()
        self.git("checkout", "main")
        self.git("merge", "--squash", "feature")
        self.git("commit", "-m", "squashed feature")
        self.git("update-ref", "refs/remotes/origin/main", self.git("rev-parse", "HEAD").strip())
        self.git("checkout", "feature")
        result = self.inspect()
        self.assertNotEqual(result["head"], result["base_sha"])
        self.assertEqual(result["dirty_paths"], 0)
        self.assertEqual(result["ownership_and_live_activity"], "not_checked")

    def test_staged_work_is_not_hidden_by_matching_working_copy(self):
        self.write("file.txt", "integrated\n")
        self.advance_base()
        self.write("file.txt", "pending staged work\n")
        self.git("add", "file.txt")
        self.write("file.txt", "integrated\n")
        result = self.inspect()["changes"][0]
        self.assertEqual(result["comparison"], "staged_residue")
        self.assertTrue(result["working_matches_base"])
        self.assertFalse(result["staged_matches_base"])

    def test_untracked_file_with_special_name_can_match_base(self):
        name = "new [file]\nwith spaces.txt"
        self.write(name, "integrated\n")
        self.advance_base()
        self.write(name, "integrated\n")
        result = self.inspect()["changes"][0]
        self.assertEqual(result["path"], name)
        self.assertEqual(result["comparison"], "matches_base")

    def test_deletion_already_in_base(self):
        (self.repo / "file.txt").unlink()
        self.advance_base()
        (self.repo / "file.txt").unlink()
        self.assertEqual(self.inspect()["changes"][0]["comparison"], "matches_base")

    def test_conflict_requires_review(self):
        self.git("branch", "side")
        self.write("file.txt", "main change\n")
        self.commit()
        self.git("checkout", "side")
        self.write("file.txt", "side change\n")
        self.commit()
        self.git("merge", "main", check=False)
        self.assertEqual(self.inspect()["changes"][0]["comparison"], "conflict")

    def test_rename_preserves_both_paths(self):
        self.git("mv", "file.txt", "renamed.txt")
        result = self.inspect()["changes"][0]
        self.assertEqual(result["previous_path"], "file.txt")
        self.assertEqual(result["path"], "renamed.txt")
        self.assertEqual(result["comparison"], "rename_or_copy_needs_review")

    def test_sensitive_contents_are_not_reported(self):
        self.write(".env", "TOKEN=fixture-value-never-in-output\n")
        result = self.inspect()
        self.assertEqual(result["changes"][0]["comparison"], "protected_not_read")
        self.assertNotIn("fixture-value-never-in-output", json.dumps(result))

    def test_large_files_and_omitted_paths_are_explicit(self):
        self.write("a.txt", "x" * 30)
        self.write("b.txt", "pending")
        result = self.inspect(limit=1, max_bytes=20)
        self.assertEqual(result["changes"][0]["comparison"], "large_file_not_read")
        self.assertEqual(result["omitted_paths"], 1)

    def test_symlink_target_is_not_read(self):
        outside = Path(self.directory.name) / "absent-target"
        (self.repo / "link").symlink_to(outside)
        self.advance_base()
        (self.repo / "link").symlink_to(outside)
        self.assertEqual(self.inspect()["changes"][0]["comparison"], "matches_base")

    @unittest.skipIf(os.name == "nt", "POSIX executable bit")
    def test_mode_change_is_not_content_equivalence(self):
        (self.repo / "file.txt").chmod(0o755)
        self.assertEqual(self.inspect()["changes"][0]["comparison"], "differs_from_base")

    def test_missing_base_stays_unknown(self):
        self.write("file.txt", "pending\n")
        result = self.inspect(base_ref="origin/unknown")
        self.assertIsNone(result["base_sha"])
        self.assertEqual(result["changes"][0]["comparison"], "base_unavailable")

    def test_cli_does_not_change_files_index_or_refs(self):
        self.write("file.txt", "pending\n")
        self.git("add", "file.txt")
        self.write("another.txt", "untracked\n")
        status_before = self.git("status", "--porcelain=v1", "--untracked-files=all")
        index_before = (self.repo / ".git/index").read_bytes()
        refs_before = self.git("show-ref")
        paths_before = sorted(str(path.relative_to(self.repo)) for path in self.repo.rglob("*"))
        result = subprocess.run([sys.executable, str(MODULE), str(self.repo)], capture_output=True, check=True, text=True)
        self.assertTrue(json.loads(result.stdout)[0]["read_only"])
        self.assertEqual(self.git("status", "--porcelain=v1", "--untracked-files=all"), status_before)
        self.assertEqual((self.repo / ".git/index").read_bytes(), index_before)
        self.assertEqual(self.git("show-ref"), refs_before)
        self.assertEqual(sorted(str(path.relative_to(self.repo)) for path in self.repo.rglob("*")), paths_before)


if __name__ == "__main__":
    unittest.main()
