"""Point d'entrée de 822 DV."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        from app.selftest import run
        sys.exit(run(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "--uitest":
        from app.uitest import run
        sys.exit(run(sys.argv[2:]))
    from app.ui import run_gui
    run_gui()
