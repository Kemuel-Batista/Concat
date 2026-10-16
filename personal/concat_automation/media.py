import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from .config import runtime_environment


def run(arguments, log=None, timeout=7200, env=None):
    result = subprocess.run(
        [str(value) for value in arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env or runtime_environment(),
        timeout=timeout,
    )
    if log:
        Path(log).write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(
            "O processamento não concluiu. Consulte "
            + str(log or "o terminal")
            + ". "
            + result.stderr[-500:]
        )
    return result.stdout


def probe(video):
    data = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                video,
            ]
        )
    )
    streams = data.get("streams", [])
    picture = next(
        (stream for stream in streams if stream["codec_type"] == "video"), None
    )
    if not picture:
        raise ValueError("O arquivo não contém vídeo.")
    rate = Fraction(picture.get("avg_frame_rate") or picture["r_frame_rate"])
    if not rate:
        rate = Fraction(30)
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duração inválida.")
    rotation = next(
        (
            float(x["rotation"])
            for x in picture.get("side_data_list", [])
            if "rotation" in x
        ),
        float(picture.get("tags", {}).get("rotate", 0)),
    )
    width, height = picture["width"], picture["height"]
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return {
        "width": width,
        "height": height,
        "rateNum": rate.numerator,
        "rateDen": rate.denominator,
        "duration": duration,
        "has_audio": any(x["codec_type"] == "audio" for x in streams),
    }


def valid_words(words, duration):
    previous = 0.0
    for word in words:
        start, end = float(word["ini"]), float(word["fim"])
        if (
            not word["w"].strip()
            or not all(map(math.isfinite, (start, end)))
            or start < previous - 0.05
            or start < 0
            or end <= start
            or end > duration + 0.15
        ):
            raise ValueError(
                "A transcrição contém tempos inválidos; o original foi preservado."
            )
        previous = start
    if not words:
        raise ValueError(
            "Não foi reconhecida fala suficiente para automatizar o corte."
        )


def adapt_cuts(raw, duration, padding, fps):
    """Keep the original script's report; apply conservative overrides separately."""
    words = raw["palavras"]
    valid_words(words, duration)
    removed = set(raw.get("fora", []))
    accepted = set()
    review = []
    for decision in raw.get("removidos", []):
        indices = {
            i
            for i, word in enumerate(words)
            if decision["ini"] <= (word["ini"] + word["fim"]) / 2 <= decision["fim"]
        }
        reason = decision["motivo"]
        reliable = (
            reason == "palavra travada"
            and all(words[i]["w"].endswith("-") for i in indices)
        ) or (reason.startswith("frase repetida") and len(indices) >= 4)
        if reliable:
            accepted.update(indices & removed)
        else:
            review.append(decision)
    # Extend every retained word into a kept range. This also restores partial
    # words or meaningful short prefixes the raw heuristic might have removed.
    intervals = [list(interval) for interval in raw["manter"]]
    for i, word in enumerate(words):
        if i not in accepted:
            intervals.append(
                [max(0, word["ini"] - padding), min(duration, word["fim"] + padding)]
            )
    intervals.sort()
    merged = []
    for start, end in intervals:
        start = max(0, round(start * fps) / fps)
        end = min(duration, round(end * fps) / fps)
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 1 / fps:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    if not merged:
        raise ValueError(
            "Nenhum intervalo válido. A automação não criou um vídeo vazio."
        )
    return {
        **raw,
        "manter": merged,
        "fora": sorted(accepted),
        "revisar": review,
        "duracao_final": sum(b - a for a, b in merged),
    }


def crop_for_face(video, info, skill):
    width, height = info["width"], info["height"]
    ratio = 9 / 16
    crop_width = min(width, int(height * ratio / 2) * 2)
    if width / height <= ratio:
        return {
            "left": 0,
            "right": 0,
            "top": 0,
            "bottom": 0,
        }, "Fonte já vertical; preservar enquadramento."
    face, reason = skill.rosto_x(str(video), info["duration"])
    if (
        face is None
        or "variação " in reason
        and float(reason.split("variação ")[-1]) > 0.2
    ):
        return (
            None,
            "Reenquadramento pendente: rosto ausente ou deslocamento grande. " + reason,
        )
    left_pixels = min(max(round(face * width - crop_width / 2), 0), width - crop_width)
    return {
        "left": left_pixels / width,
        "right": (width - left_pixels - crop_width) / width,
        "top": 0,
        "bottom": 0,
    }, reason


def write_captions(captions, destination):
    def timestamp(seconds):
        milliseconds = round(max(0, seconds) * 1000)
        hours, milliseconds = divmod(milliseconds, 3600000)
        minutes, milliseconds = divmod(milliseconds, 60000)
        seconds, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    text = "".join(
        f"{i}\n{timestamp(cue['ini'])} --> {timestamp(cue['fim'])}\n{cue['texto']}\n\n"
        for i, cue in enumerate(captions, 1)
    )
    Path(destination).write_text(text, encoding="utf-8")
