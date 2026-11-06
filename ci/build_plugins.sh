#!/bin/bash
# Compile les plugins VapourSynth absents de Homebrew, requis par QTGMC :
#   RemoveGrain/Repair/VerticalCleaner (rgvs) et znedi3 (NNEDI3).
set -euo pipefail
OUT="$(mkdir -p "${1:-build/engine/vs-plugins}" && cd "${1:-build/engine/vs-plugins}" && pwd)"
WORK="${RUNNER_TEMP:-/tmp}/plugins-src"
rm -rf "$WORK" && mkdir -p "$WORK" && cd "$WORK"
brew install meson ninja pkgconf >/dev/null 2>&1 || brew install meson ninja pkg-config

echo "== RemoveGrain (rgvs)"
git clone -q --depth 1 https://github.com/vapoursynth/vs-removegrain rg
(cd rg && meson setup build --buildtype=release >/dev/null && ninja -C build)
cp rg/build/*.dylib "$OUT/"

echo "== znedi3"
git clone -q --depth 1 --recurse-submodules --shallow-submodules https://github.com/sekrit-twc/znedi3 zn
(cd zn && make -j"$(sysctl -n hw.ncpu)" vsznedi3.so)
cp zn/vsznedi3.so zn/nnedi3_weights.bin "$OUT/"

ls -la "$OUT"
