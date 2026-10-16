from pathlib import Path
from .config import native_path, settings, write_json


def active(view):
    project = view["project"]
    return next(
        t for t in project["timelines"] if t["id"] == project["activeTimelineId"]
    )


def add_segment(
    api,
    project,
    media,
    track,
    source_start,
    source_end,
    output_start,
    crop=None,
    transition=0,
    audio_fades=True,
):
    view = api.edit(
        project, {"op": "addClip", "mediaId": media["id"], "trackId": track, "start": 0}
    )
    clip_id = view["createdId"]
    commands = [
        {
            "op": "trimClip",
            "clipId": clip_id,
            "edge": "end",
            "delta": source_end - media["duration"],
        },
        {"op": "trimClip", "clipId": clip_id, "edge": "start", "delta": source_start},
        {
            "op": "moveClips",
            "moves": [{"clipId": clip_id, "start": output_start, "trackId": track}],
        },
    ]
    fade = min(0.015, (source_end - source_start) / 8) if audio_fades else 0
    patch = {"fadeIn": fade, "fadeOut": fade}
    if crop:
        patch["crop"] = crop
    if transition:
        patch["transitionIn"] = {"id": "concat.dissolve", "duration": transition}
    commands.append({"op": "updateClip", "clipId": clip_id, "patch": patch})
    return api.edit(project, {"op": "batch", "commands": commands})


def create_project(api, video, info, cuts, captions, destination, crop, insertions):
    location = Path(settings()["projects_directory"])
    location.mkdir(parents=True, exist_ok=True)
    native_location = native_path(location)
    view = api.call(
        "project.create",
        {
            "location": native_location,
            "name": destination.name,
            "video": {
                key: info[key] for key in ("width", "height", "rateNum", "rateDen")
            },
        },
    )
    project = native_path(destination)
    write_json(
        destination / "personal-automation.json",
        {"source": str(video), "generated": True, "state": "building"},
    )
    try:
        view = api.call("media.import", {"path": project, "file": native_path(video)})
        media = next(
            m for m in view["project"]["media"] if m["path"] == native_path(video)
        )
        timeline = active(view)
        original_id = timeline["id"]
        api.edit(
            project,
            {
                "op": "renameTimeline",
                "timelineId": original_id,
                "name": "01 · Original",
            },
        )
        add_segment(
            api,
            project,
            media,
            timeline["tracks"][0]["id"],
            0,
            info["duration"],
            0,
            audio_fades=False,
        )
        for name, vertical in [("02 · Aula editada", False), ("03 · Vertical", True)]:
            view = api.edit(project, {"op": "addTimeline"})
            timeline = active(view)
            timeline_id = timeline["id"]
            api.edit(
                project,
                {"op": "renameTimeline", "timelineId": timeline_id, "name": name},
            )
            if vertical:
                api.edit(
                    project,
                    {
                        "op": "setTimelineVideo",
                        "timelineId": timeline_id,
                        "video": {
                            "width": 1080,
                            "height": 1920,
                            "rateNum": info["rateNum"],
                            "rateDen": info["rateDen"],
                        },
                    },
                )
            position = 0.0
            for index, (start, end) in enumerate(cuts["manter"]):
                add_segment(
                    api,
                    project,
                    media,
                    timeline["tracks"][0]["id"],
                    start,
                    end,
                    position,
                    crop if vertical else None,
                    min(settings()["transition_seconds"], (end - start) / 4)
                    if index
                    else 0,
                )
                position += end - start
            commands = []
            for cue in captions:
                commands.append(
                    {
                        "op": "addTextClip",
                        "trackId": timeline["tracks"][-1]["id"],
                        "above": True,
                        "start": cue["ini"],
                        "duration": cue["fim"] - cue["ini"],
                        "offsetY": 0.36,
                        "style": {
                            "content": cue["texto"],
                            "fontSize": 0.035,
                            "color": "#ffffff",
                            "strokeColor": "#000000",
                            "strokeWidth": 0.002,
                            "fontWeight": 600,
                            "maxWidth": 0.85,
                        },
                    }
                )
            for offset in range(0, len(commands), 100):
                api.edit(
                    project,
                    {"op": "batch", "commands": commands[offset : offset + 100]},
                )
            for insertion in insertions:
                imported = api.call(
                    "media.import",
                    {"path": project, "file": native_path(insertion["file"])},
                )
                asset = next(
                    item
                    for item in imported["project"]["media"]
                    if item["path"] == native_path(insertion["file"])
                )
                added = api.edit(
                    project,
                    {
                        "op": "addClip",
                        "mediaId": asset["id"],
                        "trackId": timeline["tracks"][-2]["id"],
                        "start": insertion["start"],
                    },
                )
                duration = min(
                    insertion["end"] - insertion["start"], asset["duration"] or 5
                )
                api.edit(
                    project,
                    {
                        "op": "batch",
                        "commands": [
                            {
                                "op": "trimClip",
                                "clipId": added["createdId"],
                                "edge": "end",
                                "delta": duration - (asset["duration"] or 5),
                            },
                            {
                                "op": "updateClip",
                                "clipId": added["createdId"],
                                "patch": {"muted": True, "fadeIn": 0.1, "fadeOut": 0.1},
                            },
                        ],
                    },
                )
        api.edit(
            project,
            {
                "op": "selectTimeline",
                "timelineId": view["project"]["timelines"][-2]["id"],
            },
        )
        api.call("project.save", {"path": project})
        document = api.call("project.document", {"path": project})
        write_json(
            destination / "personal-automation.json",
            {
                "source": str(video),
                "originalTimeline": original_id,
                "nativeDocumentVersion": document.get("version"),
                "generated": True,
            },
        )
        return destination
    finally:
        api.call("project.close", {"path": project, "save": True})
