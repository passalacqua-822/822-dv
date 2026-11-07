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

# QTGMC « classique » (celui de Hybrid) : havsfunc r33. Les versions suivantes ne contiennent plus QTGMC.
HAVSFUNC_REF="${HAVSFUNC_REF:-r33}"
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

# havsfunc r33 écrit _lambda= / _global= (ancienne convention de VapourSynth pour les mots réservés
# de Python). VapourSynth récent ne les reconnaît plus : on passe les vrais noms via **{'lambda': ...}.
python3 - "$ENGINE/pyscripts/havsfunc.py" <<'EOF'
import re, sys
p = sys.argv[1]
src = open(p, encoding="utf-8").read()
new, n = re.subn(r"\b_(lambda|global)=([A-Za-z_][A-Za-z0-9_]*)", r"**{'\1': \2}", src)
assert n == 6, f"attendu 6 remplacements, obtenu {n}"
compile(new, p, "exec")
open(p, "w", encoding="utf-8").write(new)
print(f"havsfunc corrigé : {n} arguments _lambda/_global")
EOF
