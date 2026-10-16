import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree
from . import broll, skills
from .config import LOCAL, ROOT, settings, write_json, native_path
from .jobs import Jobs, processing_lock
from .media import adapt_cuts, crop_for_face, probe, run, valid_words, write_captions
from .rpc import ConcatApi
from .timeline import create_project


def identity(video, config):
    file = video.stat()
    recipe = {
        key: config[key]
        for key in (
            "profile",
            "language",
            "model",
            "pause_padding",
            "maximum_pause",
            "similarity",
            "transition_seconds",
            "max_insertions",
        )
    }
    return hashlib.sha256(
        json.dumps(
            [
                str(video),
                file.st_size,
                file.st_mtime_ns,
                recipe,
                (ROOT / "skills.lock.json").read_text(),
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:24]


def process(video, words_file=None, force=False):
    with processing_lock():
        return process_locked(video, words_file, force)


def process_locked(video, words_file=None, force=False):
    config = settings()
    video = Path(video).expanduser().resolve(strict=True)
    job_id = identity(video, config)
    jobs = Jobs()
    previous = jobs.find(job_id)
    if (
        previous
        and previous["state"] in ("ready", "ready_with_pending_images")
        and not force
    ):
        print("Já processado: " + previous["output"])
        return previous["output"]
    output = LOCAL / "jobs" / job_id
    output.mkdir(parents=True, exist_ok=True)

    def stage(text):
        jobs.update(job_id, video, "running", text, output)

    try:
        skills.verify()
        info = probe(video)
        if not info["has_audio"]:
            raise ValueError("Não há áudio para aplicar as skills de fala.")
        analysis = output / "analise"
        analysis.mkdir(exist_ok=True)
        if words_file:
            # Real external transcripts may be reused; their timestamps are
            # validated against this recording, never invented to pass a test.
            document = json.loads(Path(words_file).read_text())
            raw_words = (
                document
                if isinstance(document, list)
                else document.get("palavras", document.get("words", []))
            )
            words = [
                {
                    "w": w.get("w", w.get("text")),
                    "ini": w.get("ini", w.get("start")),
                    "fim": w.get("fim", w.get("end")),
                }
                for w in raw_words
            ]
            valid_words(words, info["duration"])
            stat = video.stat()
            key = hashlib.md5(
                f"{video}|{stat.st_size}|{int(stat.st_mtime)}|{config['language']}".encode()
            ).hexdigest()
            write_json(
                analysis / "palavras.json",
                {
                    "chave": key,
                    "motor": "transcrição importada validada",
                    "palavras": words,
                },
            )
        stage("Reconhecendo fala e analisando pausas e repetições")
        env = dict(os.environ)
        from .config import runtime_environment

        env.update(runtime_environment())
        env["WHISPER_MODELO"] = config["model"]
        env["CUDA_VISIBLE_DEVICES"] = "-1"
        run(
            [
                sys.executable,
                skills.script("corte-de-pausas", "corta_pausas.py"),
                "--video",
                video,
                "--saida",
                analysis,
                "--idioma",
                config["language"],
                "--folga",
                config["pause_padding"],
                "--pausa-max",
                config["maximum_pause"],
                "--sim",
                config["similarity"],
            ],
            output / "cortes.log",
            env=env,
        )
        raw = json.loads((analysis / "cortes.json").read_text())
        shutil.copy2(analysis / "cortes.json", analysis / "cortes-original.json")
        cuts = adapt_cuts(
            raw,
            info["duration"],
            config["pause_padding"],
            info["rateNum"] / info["rateDen"],
        )
        write_json(analysis / "cortes.json", cuts)
        stage("Gerando legendas sincronizadas a partir da mesma transcrição")
        run(
            [
                sys.executable,
                skills.script("legenda-no-tempo", "legenda.py"),
                "--video",
                video,
                "--cortes",
                analysis / "cortes.json",
                "--saida",
                output,
            ],
            output / "legendas.log",
        )
        phrases = skills.load("legenda-no-tempo", "frases.py")
        retained = [
            word
            for i, word in enumerate(cuts["palavras"])
            if i not in set(cuts["fora"])
        ]
        captions = phrases.frases(retained, cuts["manter"])
        for index, cue in enumerate(captions):
            cue["fim"] = min(
                cue["fim"],
                captions[index + 1]["ini"]
                if index + 1 < len(captions)
                else cuts["duracao_final"],
            )
        captions = [cue for cue in captions if cue["fim"] > cue["ini"]]
        write_captions(captions, output / "legendas.srt")
        stage("Analisando enquadramento vertical")
        vertical = skills.load("video-vertical", "vertical.py")
        crop, crop_reason = crop_for_face(video, info, vertical)
        run(
            [
                sys.executable,
                skills.script("video-vertical", "vertical.py"),
                "--video",
                video,
                "--saida",
                output / "vertical",
                "--quadro",
            ],
            output / "vertical.log",
        )
        stage("Preparando projeto editável para Premiere")
        run(
            [
                sys.executable,
                skills.script("projeto-premiere", "projeto_premiere.py"),
                "--cortes",
                analysis / "cortes.json",
                "--saida",
                output / "premiere",
                "--nome",
                "Aula-vertical",
            ],
            output / "premiere.log",
        )
        write_captions(captions, output / "premiere/Aula-vertical.srt")
        xml_path = output / "premiere/Aula-vertical.xml"
        if config.get("runtime") == "windows":
            tree = ElementTree.parse(xml_path)
            for node in tree.iter("pathurl"):
                node.text = PureWindowsPath(native_path(video)).as_uri()
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        stage("Selecionando ilustrações por frase")
        try:
            insertions, image_status = broll.create(
                captions, output / "imagens", config["max_insertions"]
            )
        except (Exception, SystemExit) as error:
            insertions, image_status = [], "Pendente: " + str(error)
        stage("Montando as três timelines no Concat")
        safe_name = re.sub(r"[^\w -]", "", video.stem)[:55].strip() or "Aula"
        name = f"{safe_name} - auto-{job_id[:6]}" + (
            f"-{int(time.time())}" if force else ""
        )
        destination = Path(config["projects_directory"]) / name
        if destination.exists():
            # A failed attempt or a user-edited earlier result is preserved.
            destination = destination.with_name(name + "-" + str(int(time.time())))
        with ConcatApi() as api:
            create_project(
                api, video, info, cuts, captions, destination, crop, insertions
            )
        report = {
            "source": str(video),
            "source_info": info,
            "project": str(destination),
            "source_duration": info["duration"],
            "edited_duration": cuts["duracao_final"],
            "segments": len(cuts["manter"]),
            "captions": len(captions),
            "speech_suggestions_for_review": cuts["revisar"],
            "vertical": {"crop": crop, "note": crop_reason},
            "images": {"status": image_status, "insertions": insertions},
            "premiere": str(xml_path),
            "subtitles": str(output / "legendas.srt"),
            "original_media_reencoded": False,
        }
        write_json(output / "resultado.json", report)
        write_json(destination / "personal-result.json", report)
        state = (
            "ready_with_pending_images"
            if image_status.startswith("Pendente")
            else "ready"
        )
        jobs.update(
            job_id, video, state, "Projeto pronto. " + image_status, destination
        )
        return str(destination)
    except (Exception, SystemExit) as error:
        jobs.update(
            job_id,
            video,
            "failed",
            "Não concluído; o original foi preservado",
            output,
            str(error),
        )
        raise
