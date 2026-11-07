# -*- mode: python ; coding: utf-8 -*-
# Construction de « 822.DV.app » avec PyInstaller (lancé par .github/workflows/build.yml).
import glob
import os

from PyInstaller.utils.hooks import collect_all

ENGINE = os.environ.get("ENGINE_DIR", "build/engine")
VS_SITE = os.environ["VS_SITE"]  # dossier contenant le module Python « vapoursynth »

binaries = [(f, "engine/bin") for f in glob.glob(f"{ENGINE}/bin/*")]
binaries += [(f, "engine/vs-plugins") for f in glob.glob(f"{ENGINE}/vs-plugins/*") if f.endswith((".dylib", ".so"))]
datas = [(f"{ENGINE}/pyscripts", "engine/pyscripts"), ("assets/icon_1024.png", "assets")]
datas += [(f, "engine/vs-plugins") for f in glob.glob(f"{ENGINE}/vs-plugins/*.bin")]  # poids NNEDI3

vs_datas, vs_bins, vs_hidden = collect_all("vapoursynth")
# libvapoursynth charge ses filtres de base (std, resize, text) depuis son propre dossier :
# on place libvapoursynthfilters à côté d'elle (racine de Frameworks).
binaries += [(f, ".") for f in glob.glob(os.path.join(VS_SITE, "vapoursynth", "libvapoursynthfilters*.dylib"))]

a = Analysis(
    ["822dv.py"],
    pathex=[".", VS_SITE, f"{ENGINE}/pyscripts"],
    binaries=binaries + vs_bins,
    datas=datas + vs_datas,
    # Modules importés depuis le module compilé de VapourSynth (invisibles pour l'analyse automatique)
    hiddenimports=vs_hidden + ["vapoursynth", "havsfunc", "mvsfunc", "adjust",
                               "concurrent", "concurrent.futures", "fractions", "ctypes", "inspect",
                               "logging", "tomllib", "weakref", "gc", "traceback", "atexit", "enum",
                               "typing", "types", "threading", "functools", "pathlib", "dataclasses",
                               "asyncio", "json", "argparse", "importlib.metadata", "decimal", "numbers"],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="822.DV", console=False,
          target_arch="arm64", codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, name="822.DV")
app = BUNDLE(
    coll,
    name="822.DV.app",
    icon="build/822dv.icns",
    bundle_identifier="fr.passalacqua.822dv",
    info_plist={
        "CFBundleShortVersionString": "1.2", "CFBundleName": "822.DV", "CFBundleDisplayName": "822.DV",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)
