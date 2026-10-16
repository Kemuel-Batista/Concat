import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
SKILL_NAMES = (
    "corte-de-pausas",
    "imagem-por-frase",
    "legenda-no-tempo",
    "projeto-premiere",
    "video-vertical",
)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def settings():
    config = read_json(ROOT / "config.json")
    config.update(read_json(ROOT / "config.local.json", {}))
    config["projects_directory"] = str(
        Path(config["projects_directory"]).expanduser().resolve()
    )
    return config


def runtime_environment():
    env = dict(os.environ)
    env["PATH"] = str(LOCAL / "tools/bin") + os.pathsep + env.get("PATH", "")
    return env


def native_path(path):
    """The native Windows editor needs Windows paths, not WSL paths."""
    path = str(Path(path).resolve())
    if settings().get("runtime") != "windows":
        return path
    if path.startswith("/mnt/") and len(path) > 7 and path[6] == "/":
        return path[5].upper() + ":\\" + path[7:].replace("/", "\\")
    return "\\\\wsl.localhost\\Ubuntu" + path.replace("/", "\\")


def local_path(path):
    if len(path) > 2 and path[1:3] in (":\\", ":/"):
        return Path("/mnt/" + path[0].lower() + "/" + path[3:].replace("\\", "/"))
    prefix = "\\\\wsl.localhost\\Ubuntu"
    if path.lower().startswith(prefix.lower()):
        return Path(path[len(prefix) :].replace("\\", "/"))
    return Path(path)
