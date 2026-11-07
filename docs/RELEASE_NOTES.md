## Installer 822.DV

1. Télécharge **822-DV-mac.zip** ci-dessous et double-clique dessus pour le dézipper.
2. Glisse **822.DV** dans ton dossier **Applications**.
3. Premier lancement : double-clique sur l'app. macOS affiche qu'il ne peut pas vérifier le développeur.
   Va dans **Réglages Système → Confidentialité et sécurité**, descends jusqu'au message sur 822.DV et clique sur **Ouvrir quand même**.
   Cette étape n'est à faire qu'une fois.

Nécessite un Mac Apple Silicon (M1 ou plus récent). Rien d'autre à installer : VapourSynth, QTGMC, MVTools et FFmpeg sont intégrés.

**Mise à jour depuis 822 DV 1.0 :** l'application s'appelle désormais **822.DV**. Supprime l'ancienne « 822 DV » de ton dossier Applications.
Le preset de base « 822 » est appliqué automatiquement au premier lancement (et disponible dans Config → Profiles).

**Nouveau dans la 1.6 :** correction du rendu QTGMC sur Apple Silicon. Le plugin fmtconv renvoyait une image noire sur les vidéos 8 bits
(sources PowerPlay, DV), ce qui faussait la recherche de mouvement et donnait une texture qui « bave » et vibre. Le rendu est maintenant
équivalent à celui de Hybrid sur Intel. Aucun réglage à changer.
