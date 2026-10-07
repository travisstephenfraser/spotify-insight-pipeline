import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

from tests import fixtures

DOCS = ("README.md", "cost/README.md", "evals/README.md", "runs/README.md")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
# Built from pieces so this file does not itself look like a secret to a scanner.
SECRET = re.compile(
    "|".join(
        (
            "AKIA" + "[0-9A-Z]{16}",
            "gh[pousr]" + "_[A-Za-z0-9]{20,}",
            "github" + "_pat_",
            "sk" + "-[A-Za-z0-9_-]{20,}",
            "sk" + "_(live|test)_",
            "AIza" + "[0-9A-Za-z_-]{30,}",
            "-----BEGIN [A-Z ]*PRIVATE " + "KEY",
            "eyJ" + r"[A-Za-z0-9_-]{20,}\.eyJ",
        )
    )
)


class Readme(unittest.TestCase):
    def tracked(self):
        out = subprocess.run(
            ["git", "-C", str(fixtures.ROOT), "ls-files", "-co", "--exclude-standard"], capture_output=True, text=True, check=True
        )
        return set(out.stdout.splitlines())

    def test_every_relative_link_points_at_a_file_a_clone_would_have(self):
        tracked = self.tracked()
        for doc in DOCS:
            base = (fixtures.ROOT / doc).parent
            for target in LINK.findall((fixtures.ROOT / doc).read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path = (base / target).resolve().relative_to(fixtures.ROOT.resolve()).as_posix()
                with self.subTest(doc=doc, link=target):
                    self.assertTrue(path in tracked or any(t.startswith(path.rstrip("/") + "/") for t in tracked), path)

    def test_no_document_carries_anything_shaped_like_a_secret_or_a_home_path(self):
        for doc in DOCS:
            text = (fixtures.ROOT / doc).read_text(encoding="utf-8")
            with self.subTest(doc=doc):
                self.assertIsNone(SECRET.search(text))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/home/", text)

    def test_the_readme_states_the_test_count_the_suite_reports(self):
        text = (fixtures.ROOT / "README.md").read_text(encoding="utf-8")
        stated = int(re.search(r"Ran (\d+) tests", text).group(1))
        loaded = unittest.defaultTestLoader.discover(str(fixtures.ROOT / "tests"), top_level_dir=str(fixtures.ROOT)).countTestCases()
        self.assertEqual(stated, loaded)

    def test_the_readme_does_not_claim_a_run_that_has_not_been_made(self):
        text = (fixtures.ROOT / "README.md").read_text(encoding="utf-8")
        has_pilot = (fixtures.ROOT / "cost/pilot_calls.jsonl").exists()
        has_export = (fixtures.ROOT / "grading/records.jsonl").exists() or (fixtures.ROOT / "grading/records.jsonl.gz").exists()
        if not (has_pilot or has_export):
            self.assertIn("No real run has been made", text)

    def test_the_memo_lines_quoted_in_the_readme_are_lines_of_the_memo(self):
        text = (fixtures.ROOT / "README.md").read_text(encoding="utf-8")
        memo = (fixtures.ROOT / "runs/full/memo.md").read_text(encoding="utf-8").splitlines()
        section = text.split("### Decision memo", 1)[1].split("\n### ", 1)[0]
        quoted = [line[2:] for line in section.splitlines() if line.startswith("> ")]
        self.assertTrue(quoted, "the README quotes nothing from the memo")
        for line in quoted:
            with self.subTest(line=line[:60]):
                self.assertIn(line, memo)


class Walkthrough(unittest.TestCase):
    """The README's terminal session, run again. It went stale once: the outside review of 2026-10-07 ran it and got other numbers."""

    @classmethod
    def setUpClass(cls):
        cls.section = (fixtures.ROOT / "README.md").read_text(encoding="utf-8").split("\n## Walkthrough\n", 1)[1].split("\n## ", 1)[0]
        cls.block = cls.section.split("```console\n", 1)[1].split("```", 1)[0]
        cls.steps = []  # (the command, the lines the README shows under it)
        for line in cls.block.splitlines():
            if line.startswith("$ "):
                cls.steps.append((line[2:], []))
            elif line.strip():
                cls.steps[-1][1].append(line)

    def test_every_line_the_walkthrough_shows_is_printed_by_its_command_in_that_order(self):
        self.assertEqual([shlex.split(command)[:4] for command, _ in self.steps], [["python3", "-m", "pipeline", "run"]] * 2 + [["python3", "-m", "pipeline", "export"]])
        with tempfile.TemporaryDirectory() as tmp:
            for command, shown in self.steps:
                args = [a.replace("/tmp/dry", tmp) for a in shlex.split(command)[1:]]
                self.assertIn("--standin" if args[2] == "run" else "export", args)  # nothing here may reach a real model
                done = subprocess.run([sys.executable, *args], cwd=fixtures.ROOT, capture_output=True, text=True)
                printed = (done.stdout + done.stderr).splitlines()
                self.assertTrue(shown, command)
                at = 0
                for line in shown:
                    with self.subTest(command=" ".join(args[1:4]), line=line[:70]):
                        self.assertIn(line, printed[at:])
                        at = printed.index(line, at) + 1 if line in printed[at:] else at

    def test_a_figure_the_walkthrough_quotes_from_its_own_output_is_in_that_output(self):
        prose = self.section.split("```console\n", 1)[0] + self.section.split("```", 2)[2]
        quoted = re.findall(r'"(\d+ of \d+)"', prose)
        self.assertTrue(quoted, "the walkthrough explains no figure from its output")
        for figure in quoted:
            self.assertIn(figure, self.block)


class RecordedStop(unittest.TestCase):
    """The 100-review run whose stop and resume is on video. What the README says of it is read from its exported files.

    The known answer from outside those files is the video itself: after the stop, the status command prints
    "completed 38, pending 62" (validation log entry 40).
    """

    DEMO = fixtures.ROOT / "runs/demo-100b"

    @classmethod
    def setUpClass(cls):
        grading = cls.DEMO / "grading"
        cls.before = set(json.loads((grading / "checkpoint_before.json").read_text(encoding="utf-8"))["completed_ids"])
        cls.after = set(json.loads((grading / "checkpoint_after.json").read_text(encoding="utf-8"))["completed_ids"])
        calls = [json.loads(line) for line in (grading / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        cls.enrich = [c for c in calls if c["role"] == "enrich"]

    def test_the_stop_saved_38_reviews_and_the_resume_finished_all_100(self):
        self.assertEqual((len(self.before), len(self.after)), (38, 100))
        self.assertLess(self.before, self.after)

    def test_no_review_finished_before_the_stop_was_sent_again(self):
        first = {r for c in self.enrich if c["phase"] == "initial" and c["outcome"] == "succeeded" for r in c["review_ids"]}
        later = [r for c in self.enrich if c["phase"] == "resume" for r in c["review_ids"]]
        self.assertEqual(first, self.before)
        self.assertEqual(len(later), 62)
        self.assertEqual(len(set(later)), 62)
        self.assertFalse(first & set(later))

    def test_the_readme_links_the_recording_and_gives_the_counts_it_shows(self):
        text = (fixtures.ROOT / "README.md").read_text(encoding="utf-8")
        self.assertTrue((self.DEMO / "stop_resume.mov").exists())
        self.assertIn("(runs/demo-100b/stop_resume.mov)", text)
        self.assertIn("38 completed and 62 pending", text)


if __name__ == "__main__":
    unittest.main()
