import re
import subprocess
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


if __name__ == "__main__":
    unittest.main()
