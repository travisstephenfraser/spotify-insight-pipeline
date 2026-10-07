"""Nothing a clone holds names the home folder or the machine the work was done on.

The repo is public. On 2026-10-07 thirteen tracked lines held a home-folder path, eight held the laptop's name in a
pasted shell prompt, and a screenshot showed that name eight times (validation log entry 42). A picture cannot be
read here, so the screenshot is held by the hash of the copy that showed the name; the video was checked by eye.
"""

import gzip
import hashlib
import re
import subprocess
import unittest

from tests import fixtures

# Written so that this file matches none of them.
PATTERNS = {
    "home path": re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+/"),
    "machine name": re.compile(
        rb"[A-Za-z0-9]+-(?:MacBook|iMac|Mac-mini|Mac-Studio|Mac-Pro)\b"
    ),
    "shell prompt with a host": re.compile(
        rb"^(?:\([^)\n]*\) )?[a-z_][a-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*[: ]\S* ?[%$#](?: |$)",
        re.M,
    ),
}
# The compressed exports are hundreds of megabytes unpacked, so they get a plain search for the fixed part of each shape.
NEEDLES = tuple(b"/" + part for part in (b"Users/", b"home/")) + (
    b"-Mac" + b"Book",
    b"-iM" + b"ac",
)
UNREAD = (".png", ".mov")  # pictures and video: see the module's first lines
SCREENSHOT_THAT_SHOWED_THE_NAME = (
    "68bff6181d98d3a2ed91e95255b7c3be9b28da7360656e5d85cce7702bf6a497"
)


def hits(data):
    """(line number, kind) for every match in a file's bytes."""
    return sorted(
        (data.count(b"\n", 0, m.start()) + 1, kind)
        for kind, pattern in PATTERNS.items()
        for m in pattern.finditer(data)
    )


def tracked():
    """{path: blob ID} for every file a clone would hold. Two paths with the same bytes share a blob ID."""
    out = subprocess.run(
        ["git", "-C", str(fixtures.ROOT), "ls-files", "-s", "-z"],
        capture_output=True,
        check=True,
    ).stdout
    files = {}
    for entry in out.split(b"\0"):
        if entry:
            meta, path = entry.split(b"\t", 1)
            files[path.decode("utf-8")] = meta.split()[1].decode("ascii")
    return files


class Detector(unittest.TestCase):
    """The scan below reports nothing when it works, so it is first shown to see each shape."""

    def test_each_shape_is_seen(self):
        someone = "/" + "Users" + "/someone/Developer/x.py"
        linux = "/" + "home" + "/someone/x.py"
        mac = "Someones" + "-MacBook" + "-Pro-2"
        for text, kinds in (
            (f'DATA = "{someone}"', ["home path"]),
            (f"see {linux}:12", ["home path"]),
            (f"host {mac}.local", ["machine name"]),
            (
                f"(base) someone@{mac} repo % ls",
                ["machine name", "shell prompt with a host"],
            ),
            ("someone@devbox:~/repo$ ls", ["shell prompt with a host"]),
        ):
            with self.subTest(text=text[:30]):
                self.assertEqual(sorted(kind for _, kind in hits(text.encode())), kinds)
                self.assertTrue(
                    any(n in text.encode() for n in NEEDLES)
                    or kinds == ["shell prompt with a host"]
                )

    def test_the_line_number_is_the_line_of_the_match(self):
        text = "one\ntwo\n" + "/" + "Users" + "/someone/x\nfour\n"
        self.assertEqual(hits(text.encode()), [(3, "home path")])

    def test_ordinary_lines_are_not_flagged(self):
        for text in (
            "(base) someone@[laptop] repo % ls",  # the prompt as the terminal text now shows it
            "[checker](<../feed/check_submission.py#L369>)",
            'self.assertNotIn("/Users/", text)',
            "only on iphones and MacBooks, for Android",
            "fills a MacBook 16 inch window",
            "git@github.com:someone/repo.git`, private until",
            "Co-Authored-By: Someone <noreply@example.com>",
            "$ python3 -m pipeline run --run demo-100b --go",
        ):
            with self.subTest(text=text[:30]):
                self.assertEqual(hits(text.encode()), [])


class Clone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = tracked()

    def test_no_tracked_text_file_holds_a_home_path_a_machine_name_or_a_prompt_with_a_host(
        self,
    ):
        found, read = [], 0
        for path in sorted(self.files):
            if path.endswith(UNREAD + (".gz",)):
                continue
            read += 1
            found += [
                f"{path}:{line} {kind}"
                for line, kind in hits((fixtures.ROOT / path).read_bytes())
            ]
        self.assertGreater(read, 300, "the scan read too few files to mean anything")
        self.assertIn("runs/full/run_full_text.txt", self.files)
        self.assertEqual(found, [])

    def test_the_compressed_exports_hold_none_either(self):
        blobs = {
            blob: path
            for path, blob in sorted(self.files.items(), reverse=True)
            if path.endswith(".gz")
        }
        self.assertGreaterEqual(len(blobs), 3)
        keep = max(len(n) for n in NEEDLES) - 1
        for path in sorted(blobs.values()):
            tail, size, found = b"", 0, set()
            with gzip.GzipFile(fixtures.ROOT / path) as f:
                while chunk := f.read(1 << 24):
                    size += len(chunk)
                    found |= {n.decode() for n in NEEDLES if n in tail + chunk}
                    tail = chunk[-keep:]
            with self.subTest(path=path):
                self.assertGreater(size, 1 << 20, "an export this small was not read")
                self.assertEqual(found, set())

    def test_the_only_tracked_pictures_and_video_are_the_two_checked_by_eye(self):
        """A new picture or video is not covered by anything here until someone looks at it and lists it."""
        self.assertEqual(
            sorted(p for p in self.files if p.endswith(UNREAD)),
            ["runs/demo-100b/stop_resume.mov", "runs/full/run_full_screenshot.png"],
        )

    def test_the_screenshot_is_not_the_copy_that_showed_the_machine_name(self):
        digest = hashlib.sha256(
            (fixtures.ROOT / "runs/full/run_full_screenshot.png").read_bytes()
        ).hexdigest()
        self.assertNotEqual(digest, SCREENSHOT_THAT_SHOWED_THE_NAME)


if __name__ == "__main__":
    unittest.main()
