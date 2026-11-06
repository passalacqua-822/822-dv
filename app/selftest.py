"""Test sans interface : 822dv --selftest <video> <dossier_sortie>

Traite la vidéo avec les réglages par défaut (QTGMC -> ProRes HQ .mov) puis avec Bwdif,
et vérifie les fichiers produits. Code de sortie 0 = tout est bon.
"""
import json
import os
import subprocess
import sys

from . import engine, paths
from .settings import Settings


def _check(path, want_codec, want_frames_min):
    r = subprocess.run([paths.tool("ffprobe"), "-v", "error", "-count_frames", "-show_streams", "-of", "json", path],
                       capture_output=True, text=True)
    streams = json.loads(r.stdout or "{}").get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = [s for s in streams if s.get("codec_type") == "audio"]
    frames = int(v.get("nb_read_frames", 0) or 0)
    ok = v.get("codec_name") == want_codec and frames >= want_frames_min
    print(f"  {os.path.basename(path)} : {v.get('codec_name')} {v.get('width')}x{v.get('height')} "
          f"{v.get('r_frame_rate')} {frames} images, {len(a)} piste(s) audio -> {'OK' if ok else 'ÉCHEC'}")
    return ok


def run(args):
    if len(args) < 2:
        print("usage: --selftest <video> <dossier_sortie>")
        return 2
    src, outdir = args[0], args[1]
    print(engine.engine_report())
    info = engine.probe(src)
    src_frames = round(info["duration"] * info["fps"])
    ok = True

    s = Settings(output_dir=outdir, output_suffix="_qtgmc")
    try:
        out = engine.run_job(src, s)
        ok &= _check(out, "prores", int(src_frames * 2 * 0.95))
    except Exception as e:  # noqa: BLE001
        print("ÉCHEC QTGMC :", e)
        ok = False

    s = Settings(output_dir=outdir, output_suffix="_bwdif", deinterlacer="Bwdif (FFmpeg)",
                 video_handling="x264", container="mp4")
    try:
        out = engine.run_job(src, s)
        ok &= _check(out, "h264", int(src_frames * 2 * 0.95))
    except Exception as e:  # noqa: BLE001
        print("ÉCHEC Bwdif :", e)
        ok = False

    print("SELFTEST", "OK" if ok else "ÉCHEC")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
