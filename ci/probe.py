"""Vérifie que le moteur (VapourSynth + plugins + havsfunc/QTGMC) fonctionne sur la vidéo de test."""
import sys
import traceback

import vapoursynth as vs

core = vs.core
print("VapourSynth :", core.version().splitlines()[0])
print("PLUGINS :", sorted(p.namespace for p in core.plugins()))

src = sys.argv[1]
clip = None
for ns, fn in (("bs", "VideoSource"), ("ffms2", "Source"), ("lsmas", "LWLibavSource")):
    if hasattr(core, ns):
        try:
            clip = getattr(getattr(core, ns), fn)(src)
            print("LECTURE OK avec", ns, clip)
            break
        except Exception as e:  # noqa: BLE001
            print("LECTURE ÉCHEC", ns, e)
if clip is None:
    print("AUCUN LECTEUR")
    sys.exit(1)

try:
    import havsfunc as haf
    print("havsfunc importé :", haf.__file__)
except Exception:  # noqa: BLE001
    traceback.print_exc()
    sys.exit(2)

clip = core.std.SetFieldBased(clip, 1)  # 1 = BFF
try:
    out = haf.QTGMC(clip, Preset="Slower", TFF=False, FPSDivisor=1, TR2=1, Sharpness=1.0)
    for i in range(min(12, out.num_frames)):
        out.get_frame(i)
    print(f"QTGMC OK : {clip.num_frames} images entrée -> {out.num_frames} images sortie, {out.fps} i/s")
except Exception:  # noqa: BLE001
    traceback.print_exc()
    sys.exit(3)
