"""Correctif 822.DV : fmtconv (plugin fmtc) donne des résultats faux sur puce Apple quand on lui passe
une vidéo 8 bits (image noire pour fmtc.resample bicubique, arrondis différents pour le gaussien).
Les deux fonctions de havsfunc qui l'utilisent dans QTGMC (Bob et Resize) reçoivent donc la vidéo en 16 bits
(conversion exacte, x256) puis la rendent dans la profondeur d'origine. Sur Intel, le résultat est identique au bit près.
usage : patch_havsfunc.py <havsfunc.py>
"""
import sys

path = sys.argv[1]
s = open(path, encoding="utf-8").read()

old_bob = """    bits_per_sample = clip.format.bits_per_sample
    clip = clip.std.SeparateFields(tff=tff).fmtc.resample(scalev=2, kernel='bicubic', a1=b, a2=c, interlaced=1, interlacedd=0)
"""
new_bob = """    bits_per_sample = clip.format.bits_per_sample
    if clip.format.sample_type == vs.INTEGER and bits_per_sample == 8:  # 822.DV : fmtconv en 16 bits (bug Apple Silicon)
        clip = core.resize.Point(clip, format=clip.format.replace(bits_per_sample=16).id)
    clip = clip.std.SeparateFields(tff=tff).fmtc.resample(scalev=2, kernel='bicubic', a1=b, a2=c, interlaced=1, interlacedd=0)
"""
assert s.count(old_bob) == 1, "Bob introuvable"
s = s.replace(old_bob, new_bob)

old_rs = """    if bits is None:
        bits = src.format.bits_per_sample

    sr_h = w / src.width
"""
new_rs = """    if bits is None:
        bits = src.format.bits_per_sample
    if src.format.sample_type == vs.INTEGER and src.format.bits_per_sample == 8:  # 822.DV : fmtconv en 16 bits (bug Apple Silicon)
        src = core.resize.Point(src, format=src.format.replace(bits_per_sample=16).id)

    sr_h = w / src.width
"""
assert s.count(old_rs) == 1, "Resize introuvable"
s = s.replace(old_rs, new_rs)
open(path, "w", encoding="utf-8").write(s)
print("havsfunc : correctif fmtconv 16 bits appliqué (Bob, Resize)")
