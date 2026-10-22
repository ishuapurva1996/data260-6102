"""Deterministic string-only gate proofs; destructive commands never execute."""

import json
from pathlib import Path

import pytest

from src.course_files import gate

CASES = json.loads(
    (Path(__file__).parents[1] / "reports/hw07/cases/safety_commands.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_frozen_matrix(case):
    result = gate.confirm_bash(case["command"], auto_approve=True)
    assert result["allowed"] is (case["expected"] == "allow")
    assert result["reason"]


@pytest.mark.parametrize(
    "command",
    [
        "rm -r ./scratch",
        "/bin/rm -Rf ./scratch",
        "rm --recursive ./scratch",
        "sudo id",
        "su root",
        "doas id",
        "chmod 777 sample_a.py",
        "chown root sample_a.py",
        "chgrp root sample_a.py",
        "dd if=sample_a.py of=/dev/disk0",
        "cat sample_a.py > /dev/disk0",
        "mkfs.ext4 /dev/course_test",
        "newfs /dev/course_test",
        "printf x > /etc/course_test",
        "echo x >> '/etc/course_test'",
    ],
)
def test_each_destructive_category_is_independent(command):
    assert gate.is_destructive(command) is True
    assert gate.confirm_bash(command, auto_approve=True)["allowed"] is False


@pytest.mark.parametrize(
    "command",
    [
        "python --version -c 'print(1)'",
        "python -c 'print(1)'",
        "pwd; ls",
        "ls | head",
        "pwd\nls",
        "ls $(pwd)",
        "ls `pwd`",
        "head -n 5 ../outside.py",
        "head -n 5 /etc/passwd",
        "rg DEBUG --glob '*.py' /",
        "ls > result.txt",
        "PWD=/ pwd",
        "head -n 999999 sample_a.py",
        "pwd && rm -rf ./scratch",
    ],
)
def test_unsupported_or_ambiguous_grammar_blocks(command):
    assert not gate.confirm_bash(command, auto_approve=True)["allowed"]


def test_safe_prefix_never_overrides_destruction_or_full_argument_validation(monkeypatch):
    monkeypatch.setattr(gate, "SAFE_PREFIXES", (*gate.SAFE_PREFIXES, "rm", "sudo", "python"))
    assert not gate.confirm_bash("rm -rf ./scratch", auto_approve=True)["allowed"]
    assert not gate.confirm_bash("sudo id", auto_approve=True)["allowed"]
    assert not gate.confirm_bash("python -c 'print(1)'", auto_approve=True)["allowed"]


def test_confirmation_is_exact_and_never_inferred_from_auto_approval():
    command = "rm -rf ./scratch"
    assert not gate.confirm_bash(command, auto_approve=True)["allowed"]
    assert not gate.confirm_bash(command, confirmed_command="rm -rf ./other")["allowed"]
    approved = gate.confirm_bash(command, confirmed_command=command)
    assert approved["allowed"] and approved["destructive"]
    # This tests a pure decision only. No executor receives the destructive string.


@pytest.mark.parametrize("query", ["sudo", "chmod", "mkfs.ext4"])
def test_literal_search_data_is_not_a_destructive_operation(query):
    command = f"rg {query} --glob '*.py' ."
    assert not gate.is_destructive(command)
    assert gate.confirm_bash(command, auto_approve=True)["allowed"]
