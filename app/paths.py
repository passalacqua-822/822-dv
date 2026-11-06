"""Emplacement des outils : intégrés à l'application, ou installés (mode développement)."""
import os
import shutil
import sys

SEARCH = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]


def base_dir():
    if getattr(sys, "frozen", False):
        return sys._MEIPASS  # dossier interne de l'application
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def engine_dir():
    if not getattr(sys, "frozen", False) and os.environ.get("ENGINE_DIR"):
        return os.path.abspath(os.environ["ENGINE_DIR"])  # mode développement / tests
    return os.path.join(base_dir(), "engine")


def tool(name):
    bundled = os.path.join(engine_dir(), "bin", name)
    if os.path.isfile(bundled):
        return bundled
    found = shutil.which(name, path=os.pathsep.join(SEARCH + os.environ.get("PATH", "").split(os.pathsep)))
    if not found:
        raise RuntimeError(f"Outil introuvable : {name}")
    return found


def plugin_dir():
    return os.path.join(engine_dir(), "vs-plugins")


def setup_python_path():
    """Rend havsfunc/mvsfunc importables."""
    p = os.path.join(engine_dir(), "pyscripts")
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)


def icon_path():
    for p in (os.path.join(base_dir(), "assets", "icon_1024.png"),):
        if os.path.isfile(p):
            return p
    return None
