"""822 DV - réglages, profils et import des réglages Hybrid."""
import glob
import json
import os
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, fields

HOME = os.path.expanduser("~")
APP_DIR = os.path.join(HOME, "Library", "Application Support", "822 DV")
PROFILE_DIR = os.path.join(APP_DIR, "profiles")
LAST_FILE = os.path.join(APP_DIR, "last.json")
LOG_DIR = os.path.join(HOME, "Library", "Logs", "822 DV")


SETTINGS_VERSION = 2  # version 2 : preset « 822 » (ProRes 422, PAR auto 1:1, Rec.709, FineDehalo)


@dataclass
class Settings:
    settings_version: int = SETTINGS_VERSION
    # --- Base
    output_dir: str = os.path.join(HOME, "Movies", "822 DV")
    output_suffix: str = "_822dv"
    container: str = "mov"
    video_handling: str = "ProRes"
    audio_handling: str = "passthrough (all tracks)"
    overwrite: bool = True
    # --- Crop / Resize
    crop_enabled: bool = False
    crop_left: int = 0
    crop_top: int = 0
    crop_right: int = 0
    crop_bottom: int = 0
    par_mode: str = "auto to 1:1 (keep width)"
    resize_enabled: bool = False
    resize_width: int = 720
    resize_height: int = 540
    resizer: str = "Spline36"
    bicubic_b: float = 0.0
    bicubic_c: float = 0.5
    # --- Filtering : (De-)Interlace
    deinterlacer: str = "QTGMC (Vapoursynth)"
    scan_type: str = "auto"
    qtgmc_preset: str = "Slower"
    qtgmc_bob: bool = True
    qtgmc_tr0: int = -1
    qtgmc_tr1: int = -1
    qtgmc_tr2: int = 1
    qtgmc_sharpness: float = 1.0
    qtgmc_source_match: int = 0
    qtgmc_lossless: int = 0
    qtgmc_extra: str = ""
    # --- Filtering : Denoise
    denoiser: str = "none"
    mdegrain_radius: int = 2
    mdegrain_thsad: int = 300
    mdegrain_blksize: int = 16
    dfttest_sigma: float = 2.0
    # --- Filtering : Vapoursynth > Color
    color_matrix_to_709: bool = True
    color_matrix_source: str = "auto"
    # --- Filtering : Vapoursynth > DeHalo > FineDehalo (havsfunc)
    finedehalo_enabled: bool = True
    fdh_rx: float = 2.0
    fdh_ry: float = 2.0
    fdh_thmi: int = 80
    fdh_thma: int = 128
    fdh_darkstr: float = 1.5
    fdh_brightstr: float = 1.0
    fdh_thlimi: int = 50
    fdh_thlima: int = 100
    fdh_showmask: str = "none"
    fdh_contra: float = 0.0
    fdh_edgeproc: float = 0.0
    fdh_excl: bool = True
    # --- Encoders
    prores_encoder: str = "Kostya (prores_ks)"
    prores_profile: str = "Standard"
    x26x_rate_control: str = "CRF"
    x26x_crf: float = 18.0
    x26x_bitrate: int = 8000
    x26x_preset: str = "slow"
    x26x_tune: str = "none"
    x26x_extra: str = ""
    ffv1_level: int = 3
    # --- Audio
    audio_bitrate: int = 192
    audio_samplerate: str = "keep"
    # --- Advanced
    vs_custom_code: str = ""


CHOICES = {
    "container": ["mov", "mp4", "mkv"],
    "video_handling": ["ProRes", "x264", "x265", "FFV1"],
    "audio_handling": ["passthrough (first track)", "passthrough (all tracks)",
                       "AAC", "PCM 16-bit", "none"],
    "resizer": ["Spline36", "Spline16", "Spline64", "Lanczos", "Bicubic", "Bilinear", "Point"],
    "par_mode": ["auto to 1:1 (keep width)", "auto to 1:1 (keep height)", "keep input PAR"],
    "color_matrix_source": ["auto", "470bg (Rec.601 PAL)", "170m (Rec.601 NTSC)", "709 (Rec.709)"],
    "fdh_showmask": ["none", "1 - outside", "2 - shrink", "3 - edges", "4 - final"],
    "prores_encoder": ["Kostya (prores_ks)", "Anatoliy (prores_aw)", "VideoToolbox (Apple)"],
    "deinterlacer": ["QTGMC (Vapoursynth)", "Bwdif (FFmpeg)", "Yadif (FFmpeg)", "none"],
    "scan_type": ["auto", "bff", "tff", "progressive"],
    "qtgmc_preset": ["Placebo", "Very Slow", "Slower", "Slow", "Medium", "Fast",
                     "Faster", "Very Fast", "Super Fast", "Ultra Fast", "Draft"],
    "denoiser": ["none", "MDegrain (MVTools)", "DFTTest"],
    "prores_profile": ["Proxy", "LT", "Standard", "HQ", "4444", "4444 XQ"],
    "x26x_rate_control": ["CRF", "Bitrate (1-pass)", "Bitrate (2-pass)"],
    "x26x_preset": ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
                    "slow", "slower", "veryslow", "placebo"],
    "x26x_tune": ["none", "film", "grain", "animation", "fastdecode", "zerolatency"],
    "audio_samplerate": ["keep", "48000", "44100"],
}


def load(path=LAST_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return Settings()
    if path == LAST_FILE and data.get("settings_version", 1) < SETTINGS_VERSION:
        return Settings()  # nouvelle version du preset de base : on repart dessus
    known = {f.name for f in fields(Settings)}
    s = Settings()
    for k, v in data.items():
        if k in known and isinstance(v, type(getattr(s, k))):
            setattr(s, k, v)
    return s


def save(s, path=LAST_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, ensure_ascii=False, indent=2)


def profiles():
    if not os.path.isdir(PROFILE_DIR):
        return []
    return sorted(n[:-5] for n in os.listdir(PROFILE_DIR) if n.endswith(".json"))


def profile_path(name):
    return os.path.join(PROFILE_DIR, f"{name}.json")


def ensure_base_profile():
    """Crée (ou met à jour) le preset de base « 822 » avec les réglages par défaut."""
    p = profile_path("822")
    try:
        with open(p, encoding="utf-8") as f:
            if json.load(f).get("settings_version", 1) >= SETTINGS_VERSION:
                return
    except (OSError, ValueError):
        pass
    save(Settings(), p)


# ---------------------------------------------------------------- import Hybrid

def _hybrid_values(path):
    files = [path] if os.path.isfile(path) else (
        sorted(glob.glob(os.path.join(path, "*ModelDefaults.xml")))
        + sorted(glob.glob(os.path.join(path, "profiles", "global", "*.xml"))))
    vals = {}
    for fp in files:
        try:
            root = ET.parse(fp).getroot()
        except (ET.ParseError, OSError):
            continue
        for d in root.iter("HybridData"):
            if d.get("name") and d.get("value") is not None:
                vals[d.get("name")] = d.get("value")
    return vals


def import_hybrid(path, base: Settings):
    """Reprend les réglages Hybrid connus. Retourne (Settings, nombre de réglages repris)."""
    v = _hybrid_values(path)
    s = Settings(**asdict(base))
    n = 0

    def put(attr, value):
        nonlocal n
        setattr(s, attr, value)
        n += 1

    if v.get("defaultContainer") in CHOICES["container"]:
        put("container", v["defaultContainer"])
    if "QTGMC" in v.get("deinterlacer", ""):
        put("deinterlacer", "QTGMC (Vapoursynth)")
    if v.get("vsQTGMCPreset") in CHOICES["qtgmc_preset"]:
        put("qtgmc_preset", v["vsQTGMCPreset"])
    if v.get("vsQTGMCBob") in ("true", "false"):
        put("qtgmc_bob", v["vsQTGMCBob"] == "true")
    for key, attr, conv in (("vsQTGMCTr2", "qtgmc_tr2", int), ("vsQTGMCSharpness", "qtgmc_sharpness", float)):
        try:
            put(attr, conv(v[key]))
        except (KeyError, ValueError):
            pass
    if v.get("framerateAfterDeinterlacer") in ("25", "50"):
        put("qtgmc_bob", v["framerateAfterDeinterlacer"] == "50")
    try:
        if v.get("resizeWidth") and v.get("resizeHeight"):
            put("resize_width", int(v["resizeWidth"]))
            put("resize_height", int(v["resizeHeight"]))
    except ValueError:
        pass
    video = v.get("videoHandling", "").lower()
    for key, val in (("prores", "ProRes"), ("x264", "x264"), ("x265", "x265"), ("ffv1", "FFV1")):
        if key in video:
            put("video_handling", val)
            break
    if v.get("audioHandling", "").startswith("passthrough"):
        put("audio_handling", "passthrough (first track)")
    return s, n
