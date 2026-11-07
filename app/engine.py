"""822 DV - moteur de traitement.

Deux chemins :
- QTGMC (ou aucun déinterlacement) : VapourSynth dans l'application -> ffmpeg (encodage + muxage).
- Bwdif / Yadif : tout dans ffmpeg (plus rapide, qualité moindre).
Le muxage est toujours fait par ffmpeg, directement dans le conteneur final.
"""
import ast
import collections
import json
import os
import re
import shlex
import subprocess
import tempfile
import threading

from . import paths
from .settings import Settings

PRORES = {"Proxy": 0, "LT": 1, "Standard": 2, "HQ": 3, "4444": 4, "4444 XQ": 5}
FF_SCALE_FLAGS = {"Spline36": "spline", "Spline16": "spline", "Spline64": "spline", "Lanczos": "lanczos",
                  "Bicubic": "bicubic", "Bilinear": "bilinear", "Point": "neighbor"}


class Cancelled(Exception):
    pass


# ------------------------------------------------------------------ analyse

def probe(src):
    r = subprocess.run([paths.tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", src],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("Lecture impossible : " + r.stderr.strip()[-300:])
    d = json.loads(r.stdout)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise RuntimeError("Aucune piste vidéo dans ce fichier.")
    num, _, den = v.get("r_frame_rate", "25/1").partition("/")
    sar = v.get("sample_aspect_ratio", "1:1")
    if sar in ("0:1", "N/A", ""):
        sar = "1:1"
    return {
        "width": int(v["width"]), "height": int(v["height"]),
        "fps": float(num) / (float(den) if den and float(den) else 1.0),
        "field_order": v.get("field_order", "unknown"), "sar": sar,
        "codec": v.get("codec_name", "?"), "pix_fmt": v.get("pix_fmt", "?"),
        "duration": float(d.get("format", {}).get("duration", 0) or 0),
        "audio_tracks": sum(1 for s in d.get("streams", []) if s.get("codec_type") == "audio"),
    }


def describe(info):
    return (f"{info['codec']} {info['width']}x{info['height']}, {info['fps']:g} i/s, "
            f"PAR {info['sar']}, {info['duration']:.1f} s, {info['audio_tracks']} piste(s) audio")


def detect_scan(src, info, log):
    fo = info["field_order"]
    if fo in ("tt", "tb"):
        return "tff"
    if fo in ("bb", "bt"):
        return "bff"
    if fo == "progressive":
        return "progressive"
    r = subprocess.run([paths.tool("ffmpeg"), "-hide_banner", "-nostdin", "-i", src, "-t", "8", "-an",
                        "-vf", "idet", "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"Multi frame detection: TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)", r.stderr)
    if found:
        tff, bff, prog = map(int, found[-1])
        count, kind = max((tff, "tff"), (bff, "bff"), (prog, "progressive"))
        if count:
            log(f"Ordre des champs détecté : {kind.upper()} (TFF {tff}, BFF {bff}, progressif {prog})")
            return kind
    log("Ordre des champs non détecté : BFF utilisé (standard DV PAL).")
    return "bff"


def auto_crop(src, info, threshold=24):
    """Retourne (gauche, haut, droite, bas) en valeurs paires."""
    dur = info["duration"]
    start = max(0.0, dur / 2 - 30) if dur else 0.0
    r = subprocess.run([paths.tool("ffmpeg"), "-hide_banner", "-nostdin", "-ss", f"{start:.2f}", "-i", src,
                        "-t", "60", "-an", "-vf", f"cropdetect=limit={threshold}:round=2:reset=0",
                        "-f", "null", "-"], capture_output=True, text=True)
    found = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", r.stderr)
    if not found:
        return (0, 0, 0, 0)
    w, h, x, y = map(int, collections.Counter(found).most_common(1)[0][0])
    l, t = x - x % 2, y - y % 2
    return (l, t, info["width"] - l - w - (info["width"] - l - w) % 2, info["height"] - t - h - (info["height"] - t - h) % 2)


# ------------------------------------------------------------------ VapourSynth

_core_ready = False


def vs_core(log=print):
    global _core_ready
    import vapoursynth as vs
    core = vs.core
    if not _core_ready:
        pdir = paths.plugin_dir()
        if os.path.isdir(pdir):
            for f in sorted(os.listdir(pdir)):
                if f.endswith((".dylib", ".so")):
                    try:
                        core.std.LoadPlugin(os.path.join(pdir, f))
                    except vs.Error as e:
                        if "already" not in str(e).lower():
                            log(f"Plugin {f} non chargé : {e}")
        paths.setup_python_path()
        _core_ready = True
    return vs, core


def engine_report():
    lines = []
    try:
        vs, core = vs_core(lines.append)
        lines.append(core.version().splitlines()[0])
        lines.append("Plugins : " + ", ".join(sorted(p.namespace for p in core.plugins())))
        try:
            import havsfunc
            lines.append(f"havsfunc : OK ({os.path.basename(havsfunc.__file__)})")
        except Exception as e:  # noqa: BLE001
            lines.append(f"havsfunc : ERREUR {e}")
    except Exception as e:  # noqa: BLE001
        lines.append(f"VapourSynth : ERREUR {e}")
    for t in ("ffmpeg", "ffprobe"):
        try:
            lines.append(f"{t} : {paths.tool(t)}")
        except RuntimeError as e:
            lines.append(str(e))
    return "\n".join(lines)


def parse_extra(text):
    """'TR0=2, Lossless=1' -> {'TR0': 2, 'Lossless': 1} (valeurs littérales uniquement)."""
    text = text.strip().strip(",")
    if not text:
        return {}
    call = ast.parse(f"f({text})", mode="eval").body
    return {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords}


def output_format(s: Settings):
    """(format VapourSynth, pix_fmt ffmpeg)"""
    if s.video_handling == "ProRes":
        return ("YUV444P10", "yuv444p10le") if s.prores_profile.startswith("4444") else ("YUV422P10", "yuv422p10le")
    if s.video_handling == "x264":
        return "YUV420P8", "yuv420p"
    if s.video_handling == "x265":
        return "YUV420P10", "yuv420p10le"
    return "YUV422P10", "yuv422p10le"


def _source(core, src):
    for ns, fn in (("bs", "VideoSource"), ("ffms2", "Source"), ("lsmas", "LWLibavSource")):
        if hasattr(core, ns):
            return getattr(getattr(core, ns), fn)(src)
    raise RuntimeError("Aucun lecteur vidéo VapourSynth disponible.")


def _mdegrain(core, clip, s):
    r = max(1, min(3, s.mdegrain_radius))
    bs = s.mdegrain_blksize
    sup = core.mv.Super(clip, pel=2, sharp=2)
    vecs = []
    for d in range(1, r + 1):
        vecs.append(core.mv.Analyse(sup, isb=True, delta=d, blksize=bs, overlap=bs // 2))
        vecs.append(core.mv.Analyse(sup, isb=False, delta=d, blksize=bs, overlap=bs // 2))
    fn = {1: core.mv.Degrain1, 2: core.mv.Degrain2, 3: core.mv.Degrain3}[r]
    return fn(clip, sup, *vecs, thsad=s.mdegrain_thsad)


def crop_values(s: Settings):
    """(gauche, droite, haut, bas), valeurs paires ; zéros si le recadrage est désactivé."""
    if not s.crop_enabled:
        return (0, 0, 0, 0)
    return tuple(v - v % 2 for v in (s.crop_left, s.crop_right, s.crop_top, s.crop_bottom))


def _par(info):
    num, _, den = info["sar"].replace("/", ":").partition(":")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 1.0


def target_size(s: Settings, info):
    """Taille de sortie (largeur, hauteur) en pixels carrés, ou None pour garder la taille et le PAR d'origine.

    Un redimensionnement manuel (Picture resize) est prioritaire sur la conversion automatique du PAR.
    """
    if s.resize_enabled:
        return (s.resize_width, s.resize_height)
    if s.par_mode.startswith("keep input"):
        return None
    l, r, t, b = crop_values(s)
    w, h = info["width"] - l - r, info["height"] - t - b
    par = _par(info)
    if abs(par - 1.0) < 1e-3:
        return None
    if "keep height" in s.par_mode:
        w = round(w * par / 2) * 2
    else:
        h = round(h / par / 2) * 2
    return (w, h)


def source_matrix(s: Settings, info):
    if s.color_matrix_source != "auto":
        return s.color_matrix_source.split()[0]
    if info["height"] in (480, 486):
        return "170m"
    return "470bg" if info["height"] <= 576 else "709"


MATRIX_CODES = {"709": 1, "470bg": 5, "170m": 6}


def standard_fps(fps):
    """Fréquence normalisée (num, den) : 25, 29,97, 50… comme le « AssumeFPS » de Hybrid."""
    for num, den in ((24000, 1001), (24, 1), (25, 1), (30000, 1001), (30, 1), (50, 1), (60000, 1001), (60, 1)):
        if abs(fps - num / den) < 0.01:
            return num, den
    return round(fps * 1000), 1000


def build_vs(s: Settings, src, scan, log, info):
    vs, core = vs_core(log)
    clip = _source(core, src)
    # Mêmes préparations que le script généré par Hybrid
    clip = core.std.SetFrameProps(clip, _Matrix=MATRIX_CODES[source_matrix(s, info)], _ColorRange=1)
    fps = standard_fps(info["fps"])
    clip = core.std.AssumeFPS(clip, fpsnum=fps[0], fpsden=fps[1])

    if s.deinterlacer.startswith("QTGMC"):
        if scan == "progressive":
            log("Source progressive : QTGMC ignoré.")
        else:
            import havsfunc as haf
            tff = scan == "tff"
            clip = core.std.SetFieldBased(clip, 2 if tff else 1)
            kw = {"Preset": s.qtgmc_preset, "TFF": tff, "FPSDivisor": 1 if s.qtgmc_bob else 2}
            for key, val in (("TR0", s.qtgmc_tr0), ("TR1", s.qtgmc_tr1), ("TR2", s.qtgmc_tr2)):
                if val >= 0:
                    kw[key] = val
            if s.qtgmc_sharpness >= 0:
                kw["Sharpness"] = s.qtgmc_sharpness
            if s.qtgmc_source_match:
                kw["SourceMatch"] = s.qtgmc_source_match
            if s.qtgmc_lossless:
                kw["Lossless"] = s.qtgmc_lossless
            kw.update(parse_extra(s.qtgmc_extra))
            log("QTGMC(" + ", ".join(f"{k}={v!r}" for k, v in kw.items()) + ")")
            clip = haf.QTGMC(Input=clip, **kw)
            clip = core.std.SetFieldBased(clip, 0)

    if s.color_matrix_to_709:
        # Conversion faite comme Hybrid : étape séparée, dans le format d'origine.
        # (Ne pas la fusionner avec le passage en 4:2:2 : la couleur « déteint » alors sur le détail.)
        clip = core.resize.Bicubic(clip, matrix_in_s=source_matrix(s, info), matrix_s="709", range_in=0, range=0)

    if s.denoise_enabled and s.denoiser.startswith("MDegrain"):
        log(f"Débruitage MDegrain (radius {s.mdegrain_radius}, thSAD {s.mdegrain_thsad})")
        clip = _mdegrain(core, clip, s)
    elif s.denoise_enabled and s.denoiser == "DFTTest":
        if not hasattr(core, "dfttest"):
            raise RuntimeError("DFTTest n'est pas disponible dans cette version de 822.DV.")
        clip = core.dfttest.DFTTest(clip, sigma=s.dfttest_sigma)

    if s.finedehalo_enabled:
        import havsfunc as haf
        fkw = dict(rx=s.fdh_rx, ry=s.fdh_ry, thmi=s.fdh_thmi, thma=s.fdh_thma, thlimi=s.fdh_thlimi,
                   thlima=s.fdh_thlima, darkstr=s.fdh_darkstr, brightstr=s.fdh_brightstr,
                   showmask=int(s.fdh_showmask[0]) if s.fdh_showmask[0].isdigit() else 0,
                   contra=s.fdh_contra, excl=s.fdh_excl, edgeproc=s.fdh_edgeproc)
        log("FineDehalo(" + ", ".join(f"{k}={v!r}" for k, v in fkw.items()) + ")")
        clip = haf.FineDehalo(clip, **fkw)

    c = crop_values(s)
    if any(c):
        clip = core.std.Crop(clip, left=c[0], right=c[1], top=c[2], bottom=c[3])

    dims = target_size(s, info)
    if dims and (dims[0], dims[1]) != (clip.width, clip.height):
        kw = {"width": dims[0], "height": dims[1]}
        if s.resizer == "Bicubic":
            kw.update(filter_param_a=s.bicubic_b, filter_param_b=s.bicubic_c)
        elif s.resizer == "Lanczos":
            kw.update(filter_param_a=3)
        clip = getattr(core.resize, s.resizer)(clip, **kw)

    # Format de sortie, comme Hybrid : Bicubic, plage limitée
    vs_fmt, _ = output_format(s)
    clip = core.resize.Bicubic(clip, format=getattr(vs, vs_fmt), range_s="limited")

    if s.vs_custom_code.strip():
        ns = {"vs": vs, "core": core, "clip": clip}
        exec(s.vs_custom_code, ns)  # code saisi par l'utilisateur dans l'onglet Custom
        clip = ns["clip"]
    return clip


# ------------------------------------------------------------------ ffmpeg

def video_args(s: Settings, pass_no=None, passlog=None):
    _, pix = output_format(s)
    vh = s.video_handling
    tags = []  # comme Hybrid : pas d'étiquette de couleur dans le fichier
    if vh == "ProRes":
        if s.prores_encoder.startswith("VideoToolbox"):
            vt = {"Proxy": "proxy", "LT": "lt", "Standard": "standard", "HQ": "hq", "4444": "4444", "4444 XQ": "xq"}
            return ["-c:v", "prores_videotoolbox", "-profile:v", vt[s.prores_profile]] + tags
        enc = "prores_aw" if s.prores_encoder.startswith("Anatoliy") else "prores_ks"
        return ["-c:v", enc, "-profile:v", str(PRORES[s.prores_profile]), "-vendor", "apl0", "-pix_fmt", pix] + tags
    if vh in ("x264", "x265"):
        a = ["-c:v", "libx264" if vh == "x264" else "libx265", "-preset", s.x26x_preset, "-pix_fmt", pix]
        if s.x26x_tune != "none":
            a += ["-tune", s.x26x_tune]
        if s.x26x_rate_control == "CRF":
            a += ["-crf", f"{s.x26x_crf:g}"]
        else:
            a += ["-b:v", f"{s.x26x_bitrate}k"]
            if pass_no:
                a += (["-pass", str(pass_no), "-passlogfile", passlog] if vh == "x264"
                      else ["-x265-params", f"pass={pass_no}:stats={passlog}.log"])
        if vh == "x265":
            a += ["-tag:v", "hvc1"]
        if s.x26x_extra.strip():
            a += shlex.split(s.x26x_extra)
        return a + tags
    return ["-c:v", "ffv1", "-level", str(s.ffv1_level), "-pix_fmt", pix] + tags


def audio_args(s: Settings, info, input_index, log):
    mode = s.audio_handling
    if mode == "none" or info["audio_tracks"] == 0:
        return ["-an"]
    maps = ["-map", f"{input_index}:a?"] if mode == "passthrough (all tracks)" else ["-map", f"{input_index}:a:0"]
    aac = ["-c:a", "aac", "-b:a", f"{s.audio_bitrate}k"]
    if mode.startswith("passthrough") or mode == "PCM 16-bit":
        if s.container == "mp4":
            log("Le MP4 n'accepte pas l'audio PCM du DV : conversion en AAC.")
            codec = aac
        else:
            codec = ["-c:a", "copy"] if mode.startswith("passthrough") else ["-c:a", "pcm_s16le"]
    else:
        codec = aac
    if s.audio_samplerate != "keep" and codec[1] != "copy":
        codec += ["-ar", s.audio_samplerate]
    return maps + codec


def container_args(s: Settings):
    if s.container == "mp4":
        return ["-movflags", "+faststart+write_colr", "-write_tmcd", "0"]
    return ["-movflags", "+write_colr", "-write_tmcd", "0"] if s.container == "mov" else []


def _reader(stream, sink):
    for raw in iter(stream.readline, b""):
        sink(raw.decode("utf-8", "replace").rstrip())


def _run_vs(clip, cmd, on_progress, cancel, offset, span):
    import vapoursynth as vs
    err = collections.deque(maxlen=40)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t = threading.Thread(target=_reader, args=(proc.stderr, err.append), daemon=True)
    t.start()

    def progress(cur, total):
        if cancel.is_set():
            raise Cancelled()
        on_progress(offset + span * cur / max(1, total))

    try:
        clip.output(proc.stdin, y4m=True, progress_update=progress)
    except Cancelled:
        proc.kill()
        raise
    except (BrokenPipeError, OSError, vs.Error) as e:
        proc.kill()
        proc.wait()
        if cancel.is_set():
            raise Cancelled() from None
        raise RuntimeError(f"Traitement interrompu : {e}\n" + "\n".join(err)) from None
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
    proc.wait()
    t.join(timeout=5)
    if proc.returncode:
        raise RuntimeError("FFmpeg a échoué :\n" + "\n".join(err))


def _run_ff(cmd, duration, on_progress, cancel, offset, span):
    err = collections.deque(maxlen=40)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t = threading.Thread(target=_reader, args=(proc.stderr, err.append), daemon=True)
    t.start()
    for raw in iter(proc.stdout.readline, b""):
        if cancel.is_set():
            proc.kill()
            raise Cancelled()
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("out_time_us=") and duration > 0:
            try:
                on_progress(offset + span * min(1.0, int(line.split("=")[1]) / 1e6 / duration))
            except ValueError:
                pass
    proc.wait()
    t.join(timeout=5)
    if cancel.is_set():
        raise Cancelled()
    if proc.returncode:
        raise RuntimeError("FFmpeg a échoué :\n" + "\n".join(err))


def ffmpeg_filters(s: Settings, scan, log, info):
    f = []
    if scan != "progressive" and s.deinterlacer != "none":
        name = "bwdif" if s.deinterlacer.startswith("Bwdif") else "yadif"
        mode = "send_field" if s.qtgmc_bob else "send_frame"
        f.append(f"{name}=mode={mode}:parity={scan}:deint=all")
    if s.denoise_enabled:
        log("Avec Bwdif/Yadif, le débruitage utilise le filtre hqdn3d de FFmpeg.")
        f.append("hqdn3d")
    if s.finedehalo_enabled:
        log("FineDehalo n'existe qu'avec QTGMC (Vapoursynth) : ignoré avec Bwdif/Yadif.")
    l, r, t, b = crop_values(s)
    if any((l, r, t, b)):
        f.append(f"crop=iw-{l + r}:ih-{t + b}:{l}:{t}")
    matrix = ""
    if s.color_matrix_to_709:
        src_m = "bt709" if source_matrix(s, info) == "709" else "bt601"
        matrix = f":in_color_matrix={src_m}:out_color_matrix=bt709"
    dims = target_size(s, info)
    if dims:
        f.append(f"scale={dims[0]}:{dims[1]}:flags={FF_SCALE_FLAGS[s.resizer]}{matrix}")
    elif matrix:
        f.append("scale=iw:ih" + matrix)
    return f


# ------------------------------------------------------------------ tâche complète

def output_path(s: Settings, src):
    base = re.sub(r"\s+", "_", os.path.splitext(os.path.basename(src))[0])
    return os.path.join(os.path.expanduser(s.output_dir), f"{base}{s.output_suffix}.{s.container}")


def run_job(src, s: Settings, log=print, on_progress=lambda p: None, cancel=None):
    cancel = cancel or threading.Event()
    out = output_path(s, src)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out) and not s.overwrite:
        raise RuntimeError(f"Le fichier existe déjà : {out}")
    info = probe(src)
    log(f"Source : {describe(info)}")
    scan = s.scan_type if s.scan_type != "auto" else detect_scan(src, info, log)
    ff = paths.tool("ffmpeg")
    sar = "1" if target_size(s, info) else info["sar"].replace(":", "/")
    two_pass = s.video_handling in ("x264", "x265") and s.x26x_rate_control == "Bitrate (2-pass)"
    passlog = os.path.join(tempfile.gettempdir(), f"822dv_pass_{os.getpid()}")

    if s.deinterlacer.startswith(("Bwdif", "Yadif")):
        filters = ffmpeg_filters(s, scan, log, info) + [f"setsar={sar}"]
        base = [ff, "-hide_banner", "-nostdin", "-y", "-nostats", "-progress", "pipe:1", "-i", src,
                "-map", "0:v:0", "-vf", ",".join(filters)]
        log("Filtres FFmpeg : " + ",".join(filters))
        tail = audio_args(s, info, 0, log) + container_args(s) + [out]
        if two_pass:
            _run_ff(base + video_args(s, 1, passlog) + ["-an", "-f", "null", "-"], info["duration"], on_progress, cancel, 0, 50)
            _run_ff(base + video_args(s, 2, passlog) + tail, info["duration"], on_progress, cancel, 50, 50)
        else:
            _run_ff(base + video_args(s) + tail, info["duration"], on_progress, cancel, 0, 100)
    else:
        clip = build_vs(s, src, scan, log, info)
        log(f"Sortie : {clip.width}x{clip.height}, {float(clip.fps):g} i/s, {clip.num_frames} images")
        tail = audio_args(s, info, 1, log) + container_args(s) + [out]
        base = [ff, "-hide_banner", "-nostdin", "-y", "-f", "yuv4mpegpipe", "-i", "pipe:0", "-i", src,
                "-map", "0:v:0", "-vf", f"setsar={sar}"]
        if two_pass:
            _run_vs(clip, base + video_args(s, 1, passlog) + ["-an", "-f", "null", "-"], on_progress, cancel, 0, 50)
            _run_vs(clip, base + video_args(s, 2, passlog) + tail, on_progress, cancel, 50, 50)
        else:
            _run_vs(clip, base + video_args(s) + tail, on_progress, cancel, 0, 100)

    on_progress(100)
    log(f"Terminé : {out}")
    return out
