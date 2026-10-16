#!/usr/bin/env python3
"""Exercise the real Concat API against the generated classroom project."""

import json
import sys
from pathlib import Path
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from concat_automation.config import LOCAL, native_path, settings, write_json
from concat_automation.rpc import ConcatApi


def main():
    results = list(
        Path(settings()["projects_directory"]).glob("*/personal-result.json")
    )
    if not results:
        raise SystemExit("Gere primeiro um projeto com personal/run.py process.")
    result = max(results, key=lambda path: path.stat().st_mtime)
    report = json.loads(result.read_text())
    folder = result.parent
    native = native_path(folder)
    before = (folder / "concat.json").read_bytes()
    with ConcatApi() as api:
        api.call("project.open", {"path": native})
        try:
            document = api.call("project.document", {"path": native})
            assert [t["name"] for t in document["timelines"]] == [
                "01 · Original",
                "02 · Aula editada",
                "03 · Vertical",
            ]
            original, edited, vertical = document["timelines"]
            assert len(original["clips"]) == 1
            assert original["clips"][0]["fadeIn"] == 0
            assert original["clips"][0]["fadeOut"] == 0
            assert original["video"]["width"] == report["source_info"]["width"]
            assert (
                vertical["video"]["width"] == 1080
                and vertical["video"]["height"] == 1920
            )
            assert edited["video"]["rateNum"] == report["source_info"]["rateNum"]
            speech = [clip for clip in edited["clips"] if clip["kind"] == "video"]
            captions = [clip for clip in edited["clips"] if clip["kind"] == "text"]
            assert (
                len(speech) == report["segments"]
                and len(captions) == report["captions"]
            )
            track_order = {
                track["id"]: index for index, track in enumerate(edited["tracks"])
            }
            assert min(track_order[clip["trackId"]] for clip in captions) > max(
                track_order[clip["trackId"]] for clip in speech
            ), "Legendas precisam ficar acima da imagem."
            position = 0.0
            for index, clip in enumerate(speech):
                assert abs(clip["start"] - position) < 1 / 60
                assert clip["duration"] > 0 and clip["sourceStart"] >= 0
                assert (
                    clip["sourceStart"] + clip["duration"]
                    <= report["source_duration"] + 0.02
                )
                if index:
                    assert clip["transitionIn"]["id"] == "concat.dissolve"
                position += clip["duration"]
            assert abs(position - report["edited_duration"]) < 1 / 60
            assert all(clip["name"].strip() for clip in captions)
            # Rendering one real frame checks the text painter and media paths,
            # which merely validating JSON or a mock server would not cover.
            api.edit(native, {"op": "selectTimeline", "timelineId": edited["id"]})
            frame = folder / "preview-automation.png"
            api.call(
                "preview.frame",
                {
                    "path": native,
                    "time": min(2, position / 2),
                    "width": 960,
                    "height": 540,
                    "output": native_path(frame),
                },
            )
            assert frame.is_file() and frame.stat().st_size > 1000
            premiere = Path(report["premiere"])
            xml = ElementTree.parse(premiere)
            assert (
                int(
                    xml.find(
                        ".//sequence/media/video/format/samplecharacteristics/width"
                    ).text
                )
                == 1080
            )
            assert xml.find(".//pathurl").text.startswith("file:")
        finally:
            api.call("project.close", {"path": native, "save": False})
    assert (folder / "concat.json").read_bytes() == before
    write_json(
        LOCAL / "validation.json",
        {
            "native_api": "0.2",
            "runtime": "0.2.7 Windows",
            "project": str(folder),
            "source_duration": report["source_duration"],
            "edited_duration": position,
            "timelines": 3,
            "video_segments": len(speech),
            "editable_captions": len(captions),
            "preview_rendered": True,
            "premiere_xml": True,
            "source_manifest_preserved": True,
            "images": report["images"]["status"],
        },
    )
    print(
        json.dumps(
            json.loads((LOCAL / "validation.json").read_text()),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
