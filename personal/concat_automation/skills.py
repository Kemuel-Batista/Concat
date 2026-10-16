import hashlib
import importlib.util
import sys
import zipfile
from pathlib import Path
from .config import LOCAL, ROOT, SKILL_NAMES, read_json, write_json


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def install(directory):
    records = {}
    for name in SKILL_NAMES:
        archive = Path(directory) / (name + ".zip")
        root = (LOCAL / "skills").resolve()
        with zipfile.ZipFile(archive) as package:
            files = {}
            for entry in package.infolist():
                target = (root / entry.filename).resolve()
                if (
                    not target.is_relative_to(root)
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("Caminho inválido no pacote de skills.")
                if entry.is_dir():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                data = package.read(entry)
                target.write_bytes(data)
                files[entry.filename] = hashlib.sha256(data).hexdigest()
            records[name] = {"archive_sha256": digest(archive), "files": files}
    write_json(ROOT / "skills.lock.json", records)
    verify()


def verify():
    for record in read_json(ROOT / "skills.lock.json", {}).values():
        for name, expected in record["files"].items():
            if digest(LOCAL / "skills" / name) != expected:
                raise ValueError("Script original alterado: " + name)


def script(skill, filename):
    path = LOCAL / "skills" / skill / "scripts" / filename
    if not path.is_file():
        raise ValueError("Instale os cinco pacotes antes de processar.")
    return path


def load(skill, filename):
    path = script(skill, filename)
    directory = str(path.parent)
    sys.path.insert(0, directory)
    # Original scripts use sibling imports. Remove an earlier skill's sibling
    # so the adapter does not accidentally mix similarly named modules.
    for name in ("frases", "transcreve"):
        sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(
            "personal_" + skill.replace("-", "_"), path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(directory)
