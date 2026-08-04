"""Tests for kaira.core.detector."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from kaira.core.detector import (
    compute_diff,
    file_exists,
    show_diff,
    write_with_check,
)


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello")
        assert file_exists(f) is True

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "missing.py"
        assert file_exists(f) is False

    def test_directory_is_not_file(self, tmp_path):
        assert file_exists(tmp_path) is False


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_identical_returns_empty(self):
        diff = compute_diff("hello\n", "hello\n")
        assert diff == ""

    def test_added_line(self):
        diff = compute_diff("line1\n", "line1\nline2\n")
        assert "+line2" in diff

    def test_removed_line(self):
        diff = compute_diff("line1\nline2\n", "line1\n")
        assert "-line2" in diff

    def test_filename_in_diff(self):
        diff = compute_diff("old\n", "new\n", filename="model.py")
        assert "model.py" in diff

    def test_unified_diff_header(self):
        diff = compute_diff("a\n", "b\n", filename="test.py")
        assert "---" in diff
        assert "+++" in diff

    def test_empty_existing(self):
        diff = compute_diff("", "new content\n", filename="test.py")
        assert "+new content" in diff


# ---------------------------------------------------------------------------
# write_with_check — new file (no prompt needed)
# ---------------------------------------------------------------------------


class TestWriteWithCheckNewFile:
    def test_writes_new_file(self, tmp_path):
        path = tmp_path / "models" / "user.py"
        result = write_with_check(path, "class User: pass\n", force=False)
        assert result == "written"
        assert path.read_text() == "class User: pass\n"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "c" / "file.py"
        write_with_check(path, "content")
        assert path.exists()


# ---------------------------------------------------------------------------
# write_with_check — existing file, force=True
# ---------------------------------------------------------------------------


class TestWriteWithCheckForce:
    def test_overwrites_with_force(self, tmp_path):
        path = tmp_path / "user.py"
        path.write_text("old content")
        result = write_with_check(path, "new content", force=True)
        assert result == "written"
        assert path.read_text() == "new content"


# ---------------------------------------------------------------------------
# write_with_check — existing file, non_interactive=True
# ---------------------------------------------------------------------------


class TestWriteWithCheckNonInteractive:
    def test_skips_existing_non_interactive(self, tmp_path):
        path = tmp_path / "user.py"
        path.write_text("original")
        result = write_with_check(path, "new content", non_interactive=True)
        assert result == "skipped"
        assert path.read_text() == "original"


# ---------------------------------------------------------------------------
# write_with_check — interactive overwrite
# ---------------------------------------------------------------------------


class TestWriteWithCheckInteractive:
    def test_interactive_overwrite(self, tmp_path):
        path = tmp_path / "user.py"
        path.write_text("old content")

        with patch("kaira.core.detector.prompt_overwrite", return_value="overwrite"):
            result = write_with_check(
                path, "new content", force=False, non_interactive=False
            )

        assert result == "written"
        assert path.read_text() == "new content"

    def test_interactive_skip(self, tmp_path):
        path = tmp_path / "user.py"
        path.write_text("original")

        with patch("kaira.core.detector.prompt_overwrite", return_value="skip"):
            result = write_with_check(
                path, "new content", force=False, non_interactive=False
            )

        assert result == "skipped"
        assert path.read_text() == "original"

    def test_interactive_diff_then_skip(self, tmp_path):
        """User first chooses diff, then skip on the second prompt."""
        path = tmp_path / "user.py"
        path.write_text("original")

        call_count = {"n": 0}

        def prompt_side_effect(_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "diff"
            return "skip"

        with (
            patch(
                "kaira.core.detector.prompt_overwrite", side_effect=prompt_side_effect
            ),
            patch("kaira.core.detector.show_diff"),
        ):
            result = write_with_check(
                path, "new content", force=False, non_interactive=False
            )

        assert result == "skipped"
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# show_diff (smoke test — just ensure no exceptions)
# ---------------------------------------------------------------------------


class TestShowDiff:
    def test_show_diff_no_exception(self, tmp_path):
        path = tmp_path / "file.py"
        path.write_text("old line\n")
        # Should not raise
        show_diff(path, "new line\n")

    def test_show_diff_identical(self, tmp_path):
        path = tmp_path / "file.py"
        path.write_text("same content\n")
        show_diff(path, "same content\n")

    def test_show_diff_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.py"
        # Should handle gracefully
        show_diff(path, "some content\n")
