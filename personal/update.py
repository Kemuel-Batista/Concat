#!/usr/bin/env python3
"""Fetch and validate upstream without overwriting personal or original files."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PERSONAL = Path(__file__).resolve().parent
ROOT = PERSONAL.parent
sys.path.insert(0, str(PERSONAL))
from concat_automation.config import read_json, write_json  # noqa: E402 -- local CLI package bootstrap


def git(*arguments):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), *arguments], text=True
    ).strip()


def validate_source(source):
    message = (source / "src/crates/concat-api/src/message.rs").read_text()
    commands = (source / "src/crates/concat-project/src/commands/mod.rs").read_text()
    methods = [
        "project.create",
        "project.close",
        "project.list",
        "project.document",
        "project.save",
        "media.import",
        "edit.apply",
    ]
    operations = [
        "AddClip",
        "TrimClip",
        "MoveClips",
        "UpdateClip",
        "AddTextClip",
        "AddTimeline",
        "SelectTimeline",
        "SetTimelineVideo",
    ]
    if (
        'API_VERSION: &str = "0.2"' not in message
        or any(f'"{name}"' not in message for name in methods)
        or any(name not in commands for name in operations)
    ):
        raise ValueError(
            "O contrato utilizado pela automação mudou; precisa de adaptação antes da atualização."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["check", "validate", "apply"])
    parser.add_argument(
        "--native",
        action="store_true",
        help="Compila e testa o código Rust candidato; requer a toolchain do upstream.",
    )
    args = parser.parse_args()
    subprocess.run(
        ["git", "-C", str(ROOT), "fetch", "upstream", "main", "--tags"], check=True
    )
    lock = read_json(PERSONAL / "upstream.lock.json")
    candidate = git("rev-parse", "upstream/main")
    commits = git("log", "--oneline", lock["commit"] + ".." + candidate)
    print(commits or "Nenhum commit novo desde a base registrada.")
    if args.action == "check":
        return
    if git("status", "--porcelain"):
        raise ValueError(
            "Salve suas alterações em um commit antes de validar a atualização."
        )
    target = (
        PERSONAL
        / ".local/candidates"
        / (candidate[:12] + "-" + git("rev-parse", "--short", "HEAD"))
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "worktree",
                "add",
                "--detach",
                str(target),
                "HEAD",
            ],
            check=True,
        )
    report = {
        "upstream": candidate,
        "personal_head": git("rev-parse", "HEAD"),
        "contract_valid": False,
        "adapter_tests": False,
        "native_validated": False,
    }
    try:
        subprocess.run(
            ["git", "-C", str(target), "merge", "--no-edit", candidate],
            check=True,
            capture_output=True,
        )
        validate_source(target)
        report["contract_valid"] = True
        subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(PERSONAL / "tests"),
                "-v",
            ],
            cwd=ROOT,
            check=True,
        )
        report["adapter_tests"] = True
        if args.native:
            if not shutil.which("cargo"):
                raise ValueError(
                    "Instale Rust e as bibliotecas de desenvolvimento indicadas pelo Concat para validar o binário novo."
                )
            for command in [
                ["cargo", "check", "-p", "concat"],
                ["cargo", "test", "-p", "concat-project", "-p", "concat-api"],
                ["cargo", "fmt", "--check"],
            ]:
                subprocess.run(command, cwd=target / "src", check=True)
            report["native_validated"] = True
        write_json(PERSONAL / ".local/update-validation.json", report)
        print(json.dumps(report, indent=2))
        if args.action == "apply":
            if not report["native_validated"]:
                raise ValueError(
                    "A atualização permanece separada: use --native para validar o novo editor antes de aplicar."
                )
            validated_commit = subprocess.check_output(
                ["git", "-C", str(target), "rev-parse", "HEAD"], text=True
            ).strip()
            subprocess.run(
                ["git", "-C", str(ROOT), "merge", "--ff-only", validated_commit],
                check=True,
            )
            lock["commit"] = candidate
            write_json(PERSONAL / "upstream.lock.json", lock)
        elif not report["native_validated"]:
            print(
                "Contrato e automações validados. Compilação e comportamento do novo editor ainda precisam de validação nativa (--native)."
            )
    except Exception:
        write_json(PERSONAL / ".local/update-validation.json", report)
        raise


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as error:
        if isinstance(error, SystemExit):
            raise
        raise SystemExit(str(error)) from error
