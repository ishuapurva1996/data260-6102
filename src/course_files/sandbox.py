import difflib
import fnmatch
import functools
import os
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .gate import confirm_bash, relative_path, tokens

MAX_BYTES = 65_536
MAX_FILES = 100
MAX_OUTPUT = 16_384
MAX_SECONDS = 3.0


def tool(function):
    @functools.wraps(function)
    def wrapped(self, *args, **kwargs):
        try:
            data = function(self, *args, **kwargs)
            return {"success": True, "data": data, "source": "course-sandbox", "ts": self.stamp()}
        except (ValueError, OSError, UnicodeError) as exc:
            error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
            return {
                "success": False,
                "error": error,
                "source": "course-sandbox",
                "ts": self.stamp(),
            }

    return wrapped


class FileTools:
    def __init__(self, root, *, clock=time.monotonic):
        supplied = Path(root)
        if supplied.is_symlink():
            raise ValueError("The explicit course root cannot be a symlink.")
        self.root = supplied.resolve(strict=True)
        if self.root == Path("/") or not self.root.is_dir():
            raise ValueError("Create an explicit temporary course directory first.")
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.clock = clock
        self.executables = {
            "pwd": "/bin/pwd",
            "ls": "/bin/ls",
            "python": sys.executable,
            "head": "/usr/bin/head",
            "rg": shutil.which("rg"),
        }

    @staticmethod
    def stamp():
        return datetime.now(timezone.utc).isoformat()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        os.close(self.fd)

    @contextmanager
    def _parent(self, path, *, create=False):
        relative_path(path)
        parts = [p for p in path.split("/") if p not in ("", ".")]
        if not parts:
            raise ValueError("A file path is required.")
        directory = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=directory)
                    except FileExistsError:
                        pass
                child = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
            yield directory, parts[-1]
        finally:
            os.close(directory)

    @contextmanager
    def _file(self, path):
        with self._parent(path) as (directory, name):
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("Only ordinary, singly linked sandbox files are permitted.")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
                    raise ValueError(
                        "Use a singly linked ordinary UTF-8 file of at most 65536 bytes."
                    )
                yield fd
            finally:
                os.close(fd)

    def _text(self, path):
        with self._file(path) as fd:
            value = os.read(fd, MAX_BYTES + 1)
        if len(value) > MAX_BYTES:
            raise ValueError("File exceeds the bounded read size.")
        return value.decode("utf-8")

    @tool
    def read_file(self, path, max_lines=200):
        if type(max_lines) is not int or not 1 <= max_lines <= 1000:
            raise ValueError("max_lines must be an integer from 1 to 1000.")
        lines = self._text(path).splitlines(keepends=True)
        return {
            "path": path,
            "content": "".join(lines[:max_lines]),
            "lines_shown": min(len(lines), max_lines),
            "truncated": len(lines) > max_lines,
        }

    def _write(self, path, content, *, expected=None):
        if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Write bounded UTF-8 text of at most 65536 bytes.")
        data = content.encode("utf-8")
        with self._parent(path, create=True) as (directory, name):
            try:
                with self._file(path) as existing:
                    if (
                        expected is not None
                        and os.read(existing, MAX_BYTES + 1).decode("utf-8") != expected
                    ):
                        raise ValueError("File changed since the edit read; no edit made.")
            except FileNotFoundError:
                if expected is not None:
                    raise ValueError(
                        "File disappeared since the edit read; no edit made."
                    ) from None
            temporary = ".course-write-" + uuid4().hex
            fd = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                mode=0o600,
                dir_fd=directory,
            )
            try:
                while data:
                    written = os.write(fd, data)
                    if written <= 0:
                        raise OSError("Write made no progress.")
                    data = data[written:]
                os.fsync(fd)
                if expected is not None and self._text(path) != expected:
                    raise ValueError("File changed while preparing the edit; no edit made.")
                os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                os.close(fd)
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        return {"path": path, "bytes_written": len(content.encode("utf-8"))}

    @tool
    def write_file(self, path, content):
        return self._write(path, content)

    @tool
    def edit_file(self, path, old, new):
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ValueError("Provide a nonempty exact old text and replacement text.")
        before = self._text(path)
        if before.count(old) != 1:
            raise ValueError("The old text must occur exactly once; no edit made.")
        after = before.replace(old, new, 1)
        lines = list(
            difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), fromfile=path, tofile=path, n=2
            )
        )
        self._write(path, after, expected=before)
        short_diff = "".join(lines[:30])
        return {
            "path": path,
            "diff": short_diff[:4000],
            "diff_truncated": len(lines) > 30 or len(short_diff) > 4000,
        }

    def _paths(self, pattern):
        relative_path(pattern)
        deadline, paths = self.clock() + MAX_SECONDS, []

        def visit(fd, prefix, depth):
            if depth > 8 or self.clock() >= deadline:
                raise ValueError("Directory depth or traversal time limit reached.")
            with os.scandir(fd) as entries:
                for entry in entries:
                    if self.clock() >= deadline or len(paths) >= MAX_FILES:
                        raise ValueError("Directory file/time limit reached.")
                    info = entry.stat(follow_symlinks=False)
                    name = prefix + entry.name
                    if (
                        stat.S_ISLNK(info.st_mode)
                        or info.st_nlink > 1
                        and stat.S_ISREG(info.st_mode)
                    ):
                        raise ValueError("Symlinks and multiply linked files are not supported.")
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(
                            entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                        )
                        try:
                            visit(child, name + "/", depth + 1)
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(info.st_mode):
                        paths.append(name)
                    else:
                        raise ValueError("Special files are not supported.")

        visit(self.fd, "", 0)
        return [p for p in sorted(paths) if fnmatch.fnmatchcase(p, pattern)]

    @tool
    def glob_files(self, pattern="*.py"):
        return {"pattern": pattern, "files": self._paths(pattern), "truncated": False}

    @tool
    def search_in_files(self, query, file_pattern="*.py"):
        if not isinstance(query, str) or not query or len(query) > 128:
            raise ValueError("Use a nonempty literal search of at most 128 characters.")
        matches, deadline = [], self.clock() + MAX_SECONDS
        for path in self._paths(file_pattern):
            if self.clock() >= deadline:
                raise ValueError("Search time limit reached.")
            for number, text in enumerate(self._text(path).splitlines(), 1):
                if query in text:
                    matches.append({"path": path, "line": number, "text": text[:1000]})
                    if len(matches) == 50:
                        return {"matches": matches, "truncated": True, "file_pattern": file_pattern}
        return {"matches": matches, "truncated": False, "file_pattern": file_pattern}

    def _process(self, arguments, *, stdin=None, timeout=MAX_SECONDS, limit=MAX_OUTPUT):
        if not 0 < timeout <= MAX_SECONDS or not 1 <= limit <= MAX_OUTPUT:
            raise ValueError("Invalid process resource bound.")
        started = self.clock()
        process = subprocess.Popen(
            arguments,
            preexec_fn=lambda: os.fchdir(self.fd),
            pass_fds=(self.fd,),
            stdin=stdin if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
            start_new_session=True,
        )

        def kill():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        output = bytearray()
        timed_out = truncated = False
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = timeout - (self.clock() - started)
                    if remaining <= 0:
                        timed_out = True
                        break
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), min(4096, limit + 1 - len(output)))
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            output.extend(chunk)
                            if len(output) > limit:
                                truncated = True
                                break
                    if truncated:
                        break
            if timed_out or truncated:
                kill()
            process.wait(timeout=max(0.01, timeout - (self.clock() - started)))
        except subprocess.TimeoutExpired:
            timed_out = True
            kill()
            process.wait(timeout=1)
        finally:
            process.stdout.close()
            if process.poll() is None:
                kill()
                process.wait(timeout=1)
        return {
            "stdout": bytes(output[:limit]).decode("utf-8", errors="replace"),
            "returncode": process.returncode,
            "timed_out": timed_out,
            "truncated": truncated,
            "executed": True,
        }

    def bash(self, command, auto_approve=False):
        decision = confirm_bash(command, auto_approve=auto_approve)
        if not decision["allowed"]:
            return {
                "success": False,
                "error": decision["reason"],
                "gate": decision,
                "data": {"executed": False},
                "source": "course-sandbox",
                "ts": self.stamp(),
            }
        try:
            words = tokens(command)
            executable = self.executables[words[0]]
            if not executable:
                raise ValueError("Required read-only executable is unavailable.")
            if words[0] == "head":
                with self._file(words[3]) as fd:
                    result = self._process([executable, "-n", words[2]], stdin=fd)
            elif words[0] == "rg":
                began, output, codes = self.clock(), "", []
                result = {
                    "stdout": "",
                    "returncode": 1,
                    "executed": True,
                    "timed_out": False,
                    "truncated": False,
                }
                for path in self._paths(words[3]):
                    remaining = MAX_SECONDS - (self.clock() - began)
                    if remaining <= 0 or len(output.encode()) >= MAX_OUTPUT:
                        result["timed_out"] = remaining <= 0
                        result["truncated"] = not result["timed_out"]
                        break
                    with self._file(path) as fd:
                        item = self._process(
                            [executable, "--no-config", "-n", "-F", "--", words[1]],
                            stdin=fd,
                            timeout=remaining,
                            limit=max(1, MAX_OUTPUT - len(output.encode())),
                        )
                    codes.append(item["returncode"])
                    output += "".join(
                        path + ":" + line + "\n" for line in item["stdout"].splitlines()
                    )
                    result.update(timed_out=item["timed_out"], truncated=item["truncated"])
                    if item["timed_out"] or item["truncated"]:
                        break
                encoded = output.encode()
                result.update(
                    stdout=encoded[:MAX_OUTPUT].decode(errors="replace"),
                    returncode=0 if 0 in codes else 1,
                    truncated=result["truncated"] or len(encoded) > MAX_OUTPUT,
                )
            else:
                result = self._process([executable, *words[1:]])
            return {
                "success": not (result["timed_out"] or result["truncated"]),
                "data": result,
                "gate": decision,
                "source": "course-sandbox",
                "ts": self.stamp(),
            }
        except (ValueError, OSError) as exc:
            return {
                "success": False,
                "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                "gate": decision,
                "data": {"executed": False},
                "source": "course-sandbox",
                "ts": self.stamp(),
            }
