import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from .config import (
    LOCAL,
    ROOT,
    local_path,
    native_path,
    read_json,
    settings,
    write_json,
)
from .jobs import Jobs
from .pipeline import identity, process
from .rpc import ConcatApi
from . import skills


def start():
    config = settings()
    try:
        with ConcatApi():
            return
    except (Exception, SystemExit):
        pass
    executable = Path(config["executable"])
    if not executable.is_file():
        raise ValueError("O Concat não foi instalado. Consulte personal/README.md.")
    portable = Path(config["native_config"])
    preferences = read_json(portable / "settings.json", {})
    preferences["locale"] = "pt-BR"
    preferences["server"] = {
        "enabled": True,
        "listen": "127.0.0.1:" + str(config["api_port"]),
        "token": read_json(LOCAL / "credentials.json")["apiToken"],
    }
    write_json(portable / "settings.json", preferences)
    if config.get("runtime") == "windows":
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                native_path(ROOT / "windows-launch.ps1"),
                native_path(executable),
            ],
            check=True,
            timeout=30,
        )
    else:
        subprocess.Popen(
            [str(executable)],
            stdout=(LOCAL / "concat.log").open("a"),
            stderr=subprocess.STDOUT,
        )
    for _ in range(30):
        try:
            with ConcatApi():
                return
        except Exception:
            time.sleep(1)
    raise ValueError(
        "O Concat não disponibilizou a API. Confira os logs na pasta portable/logs."
    )


def remember_projects(recents, destination=None):
    """Keep watching source projects even after they leave the recent list."""
    destination = destination or LOCAL / "watched-projects.json"
    saved = read_json(destination, [])
    folders = dict.fromkeys(saved)
    for entry in recents:
        folder = local_path(entry["path"])
        if not (folder / "personal-automation.json").exists():
            folders[str(folder)] = None
    write_json(destination, list(folders))
    return [{"path": folder} for folder in folders]


def imported_media(recents):
    result = []
    for entry in recents:
        folder = local_path(entry["path"])
        if (folder / "personal-automation.json").exists():
            continue
        manifest = folder / "concat.json"
        if not manifest.exists():
            manifest = folder / "wolfcut.json"
        try:
            document = read_json(manifest, {})
        except (ValueError, OSError):
            continue  # Autosave is atomic, but removable drives may disappear.
        for media in document.get("media", []):
            if media.get("kind") == "video" and media.get("hasAudio"):
                video = local_path(media["path"])
                if video.is_file() and video not in result:
                    result.append(video)
    return result


def watch(once=False):
    import fcntl

    LOCAL.mkdir(exist_ok=True)
    lock = (LOCAL / "watch.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError("A automação já está acompanhando as importações.")
    jobs = Jobs()
    print(
        "Automação ativa. Importe um vídeo no Concat; os projetos gerados aparecem em Recentes.",
        flush=True,
    )
    while True:
        try:
            with ConcatApi() as api:
                recents = api.call("project.list")
            for video in imported_media(remember_projects(recents)):
                job = jobs.find(identity(video.resolve(), settings()))
                if job and job["state"] not in ("interrupted", "queued", "running"):
                    continue
                try:
                    process(video)
                except (Exception, SystemExit) as error:
                    print("Automação não concluída:", str(error), flush=True)
        except (Exception, SystemExit) as error:
            print("Aguardando Concat:", str(error), flush=True)
        if once:
            return
        time.sleep(settings()["poll_seconds"])


def main():
    parser = argparse.ArgumentParser(
        description="Concat pessoal: automações sem modificar o editor original."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("start", help="Abre o editor e acompanha importações.")
    watcher = commands.add_parser("watch")
    watcher.add_argument("--once", action="store_true")
    install = commands.add_parser("install-skills")
    install.add_argument("directory")
    run = commands.add_parser("process")
    run.add_argument("video")
    run.add_argument("--words")
    run.add_argument("--force", action="store_true")
    commands.add_parser("status")
    commands.add_parser("doctor")
    args = parser.parse_args()
    if args.command == "install-skills":
        skills.install(args.directory)
        print("Cinco pacotes instalados; arquivos originais conferidos por SHA-256.")
    elif args.command == "process":
        process(args.video, args.words, args.force)
    elif args.command == "status":
        print(json.dumps(Jobs().all(), ensure_ascii=False, indent=2))
    elif args.command == "doctor":
        skills.verify()
        with ConcatApi() as api:
            print(
                json.dumps(
                    {
                        "runtime": settings().get("runtime"),
                        "api": api.version,
                        "skills": "originais conferidos",
                        "pixabay": bool(os.environ.get("PIXABAY_API_KEY"))
                        or (Path.home() / ".pixabay_key").is_file(),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
    else:
        if args.command == "start":
            start()
        watch(getattr(args, "once", False))
