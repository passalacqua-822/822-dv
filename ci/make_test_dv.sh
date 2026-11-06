#!/bin/bash
# Génère une vidéo DV PAL de test aux mêmes caractéristiques que les fichiers de Lucas :
# 720x576, 25 i/s entrelacé, champ inférieur en premier (BFF), 4:3, audio PCM stéréo.
set -euo pipefail
OUT="${1:-test.dv}"
SECONDS_LEN="${2:-4}"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=720x576:rate=50,format=yuv420p" \
  -f lavfi -i "sine=frequency=440:sample_rate=48000" \
  -t "$SECONDS_LEN" \
  -vf "interlace=scan=bff:lowpass=0" \
  -c:v dvvideo -flags +ilme+ildct -top 0 -aspect 4:3 \
  -ac 2 -ar 48000 -c:a pcm_s16le \
  -f dv "$OUT"
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate,field_order -of default=nw=1 "$OUT"
