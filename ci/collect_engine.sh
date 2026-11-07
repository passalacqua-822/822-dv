#!/bin/bash
# Rassemble le moteur à intégrer dans l'application : ffmpeg/ffprobe, plugins VapourSynth, havsfunc/mvsfunc.
set -euo pipefail
ENGINE="${1:-build/engine}"
rm -rf "$ENGINE"
mkdir -p "$ENGINE/bin" "$ENGINE/vs-plugins" "$ENGINE/pyscripts"
BREW="$(brew --prefix)"

for t in ffmpeg ffprobe; do
  cp "$(realpath "$BREW/bin/$t")" "$ENGINE/bin/$t"
done

for f in vapoursynth-mvtools vapoursynth-bestsource; do
  brew list "$f" | grep -E '\.(dylib|so)$' | while read -r lib; do
    cp "$lib" "$ENGINE/vs-plugins/"
  done
done
bash "$(dirname "$0")/build_plugins.sh" "$ENGINE/vs-plugins"
echo "Plugins intégrés :"; ls -la "$ENGINE/vs-plugins"

# QTGMC « classique » de Hybrid : havsfunc d'octobre 2021 (les versions de 2025 ne contiennent plus QTGMC).
HAVSFUNC_REF="${HAVSFUNC_REF:-3b6a80c}"  # oct. 2021 : la version embarquée par Hybrid 2022
MVSFUNC_REF="${MVSFUNC_REF:-r10}"
for pair in "HomeOfVapourSynthEvolution/havsfunc:$HAVSFUNC_REF:havsfunc.py" \
            "HomeOfVapourSynthEvolution/mvsfunc:$MVSFUNC_REF:mvsfunc.py" \
            "dubhater/vapoursynth-adjust:master:adjust.py"; do
  IFS=: read -r repo ref file <<< "$pair"
  dir="/tmp/$(basename "$repo")"
  rm -rf "$dir"
  git clone -q "https://github.com/$repo" "$dir"
  git -C "$dir" checkout -q "$ref"
  cp "$dir/$file" "$ENGINE/pyscripts/"
  echo "$file <- $repo@$ref"
done
python3 "$(dirname "$0")/patch_havsfunc.py" "$ENGINE/pyscripts/havsfunc.py"


