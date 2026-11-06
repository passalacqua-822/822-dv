# 822 DV

Interface Mac (Apple Silicon, sans Rosetta) pour déinterlacer et convertir des vidéos DV, organisée comme Hybrid :
Base, Crop/Resize, Filtering (QTGMC, débruitage, couleur), ProRes, x264/x265, FFV1, Audio, Jobs, Config, Logs.

- Moteur intégré : VapourSynth + QTGMC (havsfunc) + MVTools + BestSource, encodage et muxage par FFmpeg.
- Déinterlaceurs : QTGMC, Bwdif et Yadif (FFmpeg).
- Sorties : ProRes (Proxy à 4444 XQ), H.264, H.265, FFV1 en .mov, .mp4 ou .mkv.
- Profils, file d'attente, import des réglages Hybrid.

**Télécharger :** onglet [Releases](../../releases), fichier `822-DV-mac.zip`.

L'application est construite et testée automatiquement sur les Mac de GitHub (`.github/workflows/build.yml`).
Les outils intégrés sont des logiciels libres (VapourSynth : LGPL, FFmpeg/x264/x265 : GPL, havsfunc/mvsfunc/MVTools : GPL).
