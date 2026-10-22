"""Real filesystem/process checks use only fresh temporary course directories."""

import os
import sys

import pytest

from src.course_files.sandbox import FileTools


@pytest.fixture
def tools(tmp_path):
    root = tmp_path / "course"
    root.mkdir(mode=0o700)
    with FileTools(root) as instance:
        yield instance


def test_write_edit_diff_read_truncation_and_filtered_discovery(tools):
    assert tools.write_file("sample_a.py", "one\ntwo\nthree\n")["success"]
    assert tools.write_file("sample_b.py", "DEBUG = True\n")["success"]
    assert tools.write_file("notes.txt", "DEBUG excluded by file_pattern\n")["success"]
    read = tools.read_file("sample_a.py", max_lines=2)["data"]
    assert read["content"] == "one\ntwo\n" and read["truncated"]
    edited = tools.edit_file("sample_a.py", "two", "TWO")["data"]
    assert "-two" in edited["diff"] and "+TWO" in edited["diff"]
    assert tools.read_file("sample_a.py")["data"]["content"] == "one\nTWO\nthree\n"
    assert tools.glob_files("*.py")["data"]["files"] == ["sample_a.py", "sample_b.py"]
    matches = tools.search_in_files("DEBUG", file_pattern="*.py")["data"]["matches"]
    assert [(m["path"], m["line"]) for m in matches] == [("sample_b.py", 1)]
    assert not tools.edit_file("sample_a.py", "absent", "x")["success"]


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", "nested/../../outside"])
def test_traversal_and_absolute_paths_never_reach_filesystem(tools, path):
    assert not tools.read_file(path)["success"]
    assert not tools.write_file(path, "no")["success"]
    assert not tools.edit_file(path, "x", "y")["success"]
    assert not tools.glob_files(path)["success"]


def test_symlink_and_hardlink_escape_are_rejected_before_read_or_write(tools, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("harmless outside marker")
    (tools.root / "link.txt").symlink_to(outside)
    os.link(outside, tools.root / "hard.txt")
    for path in ("link.txt", "hard.txt"):
        assert not tools.read_file(path)["success"]
        assert not tools.write_file(path, "changed")["success"]
    assert outside.read_text() == "harmless outside marker"
    assert not tools.search_in_files("marker", file_pattern="*")["success"]


def test_symlink_parent_is_never_followed(tools, tmp_path):
    outside = tmp_path / "outside-dir"
    outside.mkdir()
    (tools.root / "escape").symlink_to(outside, target_is_directory=True)
    assert not tools.write_file("escape/new.txt", "no")["success"]
    assert not (outside / "new.txt").exists()


def test_actual_safe_commands_and_blocked_commands_not_executed(tools, monkeypatch):
    tools.write_file("sample_a.py", "DEBUG = True\n")
    for command in (
        "pwd",
        "ls",
        "python --version",
        "head -n 5 sample_a.py",
        "rg DEBUG --glob '*.py' .",
    ):
        result = tools.bash(command, auto_approve=True)
        assert result["success"] and result["data"]["returncode"] == 0
        assert result["data"]["executed"]
        output = result["data"]["stdout"]
        if command == "pwd":
            assert os.path.realpath(output.strip()) == str(tools.root)
        elif command == "ls":
            assert output.splitlines() == ["sample_a.py"]
        elif command.startswith("head"):
            assert output == "DEBUG = True\n"
        elif command.startswith("rg"):
            assert output == "sample_a.py:1:DEBUG = True\n"

    def forbidden(*args, **kwargs):
        raise AssertionError("Blocked command reached a process launcher")

    monkeypatch.setattr(tools, "_process", forbidden)
    result = tools.bash("rm -rf ./scratch", auto_approve=True)
    assert not result["success"] and not result["data"]["executed"]


def test_process_time_and_output_bounds_use_only_harmless_producers(tools):
    output = tools._process([sys.executable, "-c", "print('x'*100000)"], timeout=2, limit=100)
    assert output["truncated"] and len(output["stdout"].encode()) <= 100
    timed = tools._process([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.05)
    assert timed["timed_out"]


def test_edit_reports_character_truncation(tmp_path):
    root = tmp_path / "course"
    root.mkdir()
    with FileTools(root) as tools:
        assert tools.write_file("long.txt", "a" * 5000)["success"]
        result = tools.edit_file("long.txt", "a" * 5000, "b" * 5000)
    assert result["success"]
    assert result["data"]["diff_truncated"]
    assert len(result["data"]["diff"]) == 4000


def test_failed_write_preserves_existing_bytes(tools, monkeypatch):
    assert tools.write_file("existing.txt", "original\n")["success"]

    def disk_full(*args, **kwargs):
        raise OSError("controlled storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", disk_full)
        assert not tools.edit_file("existing.txt", "original", "changed")["success"]
    assert tools.read_file("existing.txt")["data"]["content"] == "original\n"
    assert tools.glob_files("*")["data"]["files"] == ["existing.txt"]


@pytest.mark.parametrize("count,allowed", [(100, True), (101, False)])
def test_scan_file_count_boundary(tools, count, allowed):
    for index in range(count):
        (tools.root / f"{index}.py").write_text("x\n")
    assert tools.glob_files("*.py")["success"] is allowed
    assert tools.search_in_files("x", "*.py")["success"] is allowed


@pytest.mark.parametrize("depth,allowed", [(8, True), (9, False)])
def test_scan_depth_boundary(tools, depth, allowed):
    path = tools.root
    for _ in range(depth):
        path = path / "nested"
        path.mkdir()
    (path / "deep.py").write_text("x\n")
    assert tools.glob_files("*.py")["success"] is allowed
    assert tools.search_in_files("x", "*.py")["success"] is allowed


def test_scan_clock_deadline_is_enforced(tools):
    ticks = iter([0, 4])
    tools.clock = lambda: next(ticks)
    result = tools.glob_files("*.py")
    assert not result["success"] and "time limit" in result["error"]
    ticks = iter([0, 0, 4])
    tools.clock = lambda: next(ticks)
    result = tools.search_in_files("x", "*.py")
    assert not result["success"] and "time limit" in result["error"]


def test_exact_edit_rejects_duplicate_text(tools):
    tools.write_file("duplicate.txt", "old old\n")
    assert not tools.edit_file("duplicate.txt", "old", "new")["success"]
    assert tools.read_file("duplicate.txt")["data"]["content"] == "old old\n"


def test_prepared_edit_preserves_a_detected_concurrent_change(tools, monkeypatch):
    tools.write_file("existing.txt", "original\n")
    actual_write = os.write

    def concurrent_change(fd, data):
        written = actual_write(fd, data)
        (tools.root / "existing.txt").write_text("intervening change\n")
        return written

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", concurrent_change)
        result = tools.edit_file("existing.txt", "original", "changed")
    assert not result["success"] and "File changed" in result["error"]
    assert tools.read_file("existing.txt")["data"]["content"] == "intervening change\n"
    assert tools.glob_files("*")["data"]["files"] == ["existing.txt"]


def test_zero_progress_write_stops_and_preserves_existing_bytes(tools, monkeypatch):
    tools.write_file("existing.txt", "original\n")
    with monkeypatch.context() as patch:
        patch.setattr(os, "write", lambda *args: 0)
        assert not tools.write_file("existing.txt", "changed")["success"]
    assert tools.read_file("existing.txt")["data"]["content"] == "original\n"
