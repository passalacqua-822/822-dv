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
echo "Plugins intégrés :"; ls -la "$ENGINE/vs-plugins"

for repo in havsfunc mvsfunc; do
  rm -rf "/tmp/$repo"
  git clone -q "https://github.com/HomeOfVapourSynthEvolution/$repo" "/tmp/$repo"
  ref_var="$(echo "${repo}_REF" | tr '[:lower:]' '[:upper:]')"
  ref="${!ref_var:-$(git -C "/tmp/$repo" tag | sort -V | tail -1)}"
  git -C "/tmp/$repo" checkout -q "$ref"
  cp "$(find "/tmp/$repo" -maxdepth 2 -name "$repo.py" | head -1)" "$ENGINE/pyscripts/"
  echo "$repo -> $ref"
done
