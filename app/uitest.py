"""Test de l'interface sans écran : 822dv --uitest <dossier_captures>

Ouvre la fenêtre, parcourt chaque onglet et enregistre une capture PNG par onglet.
"""
import os
import sys


def run(args):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from .ui import MainWindow

    outdir = args[0] if args else "."
    os.makedirs(outdir, exist_ok=True)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(1100, 760)
    w.show()
    app.processEvents()
    for i in range(w.tabs.count()):
        w.tabs.setCurrentIndex(i)
        app.processEvents()
        name = w.tabs.tabText(i).replace("/", "-").replace(" ", "_")
        path = os.path.join(outdir, f"{i:02d}_{name}.png")
        w.grab().save(path)
        print("capture :", path)
    # Sous-onglets Vapoursynth (Color, DeNoise, DeHalo…)
    w.tabs.setCurrentIndex(next(i for i in range(w.tabs.count()) if w.tabs.tabText(i) == "Filtering"))
    w.filter_tabs.setCurrentIndex(1)
    for j in range(w.vs_tabs.count()):
        w.vs_tabs.setCurrentIndex(j)
        app.processEvents()
        path = os.path.join(outdir, f"20_Vapoursynth_{w.vs_tabs.tabText(j)}.png")
        w.grab().save(path)
        print("capture :", path)
    w.close()
    print("UITEST OK")
    return 0
