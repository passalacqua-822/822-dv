"""822.DV - interface (organisation inspirée de Hybrid : Base, Crop/Resize, Filtering, encodeurs, Audio, Jobs, Config, Logs)."""
import datetime
import os
import subprocess
import sys
import threading
import traceback
from dataclasses import asdict, fields

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from . import engine, paths
from . import settings as st

VERSION = "1.5"
VIDEO_FILTER = "Vidéos (*.dv *.DV *.avi *.mov *.mp4 *.mkv *.m2t *.mts *.mpg);;Tous les fichiers (*)"


# ------------------------------------------------------------------ liaison réglages <-> widgets

class Binder:
    def __init__(self):
        self.w = {}

    def combo(self, name):
        w = QComboBox()
        w.addItems(st.CHOICES[name])
        self.w[name] = w
        return w

    def check(self, name, text):
        w = QCheckBox(text)
        self.w[name] = w
        return w

    def spin(self, name, lo, hi, step=1, auto=None):
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        if auto:
            w.setSpecialValueText(auto)
        self.w[name] = w
        return w

    def dspin(self, name, lo, hi, step=0.1, dec=2, auto=None):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(dec)
        if auto:
            w.setSpecialValueText(auto)
        self.w[name] = w
        return w

    def line(self, name, placeholder=""):
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        self.w[name] = w
        return w

    def text(self, name, placeholder=""):
        w = QPlainTextEdit()
        w.setPlaceholderText(placeholder)
        self.w[name] = w
        return w

    def read(self):
        s = st.Settings()
        for name, w in self.w.items():
            if isinstance(w, QComboBox):
                v = w.currentText()
            elif isinstance(w, QCheckBox):
                v = w.isChecked()
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                v = w.value()
            elif isinstance(w, QPlainTextEdit):
                v = w.toPlainText()
            else:
                v = w.text()
            setattr(s, name, type(getattr(s, name))(v))
        return s

    def write(self, s):
        for name, w in self.w.items():
            v = getattr(s, name)
            if isinstance(w, QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setValue(v)
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(v)
            else:
                w.setText(str(v))


# ------------------------------------------------------------------ file d'attente

class QueueWorker(QThread):
    log = Signal(str)
    status = Signal(int, str)
    progress = Signal(int, int)
    done = Signal()

    def __init__(self, jobs):
        super().__init__()
        self.jobs = jobs
        self.cancel = threading.Event()

    def run(self):
        for job in self.jobs:
            if job["status"] != "waiting":
                continue
            if self.cancel.is_set():
                break
            jid = job["id"]
            self.status.emit(jid, "running")
            self.log.emit(f"=== Job {jid} : {os.path.basename(job['src'])}")
            try:
                engine.run_job(job["src"], job["settings"], self.log.emit,
                               lambda p, j=jid: self.progress.emit(j, int(p)), self.cancel)
                self.status.emit(jid, "finished")
            except engine.Cancelled:
                self.status.emit(jid, "aborted")
                self.log.emit("Arrêté par l'utilisateur.")
                break
            except Exception as e:  # noqa: BLE001
                self.status.emit(jid, "error")
                self.log.emit(f"ERREUR : {e}")
                self.log.emit(traceback.format_exc())
        self.done.emit()


# ------------------------------------------------------------------ fenêtre principale

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("822.DV")
        self.resize(1100, 760)
        self.setAcceptDrops(True)
        self.b = Binder()
        self.jobs = []
        self.next_id = 1
        self.worker = None

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_base(), "Base")
        self.tabs.addTab(self._tab_prores(), "ProRes")
        self.tabs.addTab(self._tab_x26x(), "x264/x265")
        self.tabs.addTab(self._tab_ffv1(), "FFV1")
        self.tabs.addTab(self._tab_crop_resize(), "Crop/Resize")
        self.tabs.addTab(self._tab_filtering(), "Filtering")
        self.tabs.addTab(self._tab_audio(), "Audio")
        self.tabs.addTab(self._tab_config(), "Config")
        self.tabs.addTab(self._tab_jobs(), "Jobs")
        self.tabs.addTab(self._tab_logs(), "Logs")

        bottom = QHBoxLayout()
        self.btn_add = QPushButton("Add to queue")
        self.btn_add.clicked.connect(self.add_to_queue)
        self.btn_start = QPushButton("Start queue")
        self.btn_start.clicked.connect(self.start_queue)
        self.btn_stop = QPushButton("Stop queue")
        self.btn_stop.clicked.connect(self.stop_queue)
        self.btn_stop.setEnabled(False)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        for w in (self.btn_add, self.btn_start, self.btn_stop):
            bottom.addWidget(w)
        bottom.addWidget(self.bar, 1)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.tabs, 1)
        lay.addLayout(bottom)
        self.setCentralWidget(central)
        self._menus()
        st.ensure_base_profile()
        self._refresh_profiles()
        self.b.write(st.load())
        self.log(f"822.DV {VERSION} prêt.")

    # ---------------------------------------------------------------- onglets
    def _tab_base(self):
        page = QWidget()
        g = QGridLayout(page)

        box_in = QGroupBox("Input")
        v = QVBoxLayout(box_in)
        self.inputs = QListWidget()
        self.inputs.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.inputs.currentItemChanged.connect(self._show_info)
        v.addWidget(self.inputs)
        row = QHBoxLayout()
        for text, slot in (("Add files…", self.add_files_dialog), ("Remove", self.remove_inputs),
                           ("Clear", self.inputs.clear)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        v.addLayout(row)
        self.info = QLabel("Glisse tes fichiers .dv ici ou clique sur « Add files… ».")
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        g.addWidget(box_in, 0, 0, 1, 2)

        box_out = QGroupBox("Output")
        f = QFormLayout(box_out)
        out_row = QHBoxLayout()
        out_row.addWidget(self.b.line("output_dir"))
        browse = QPushButton("…")
        browse.clicked.connect(self._pick_output_dir)
        out_row.addWidget(browse)
        f.addRow("Output folder", out_row)
        f.addRow("Name suffix", self.b.line("output_suffix"))
        f.addRow("Container", self.b.combo("container"))
        f.addRow("", self.b.check("overwrite", "Overwrite existing files"))
        g.addWidget(box_out, 1, 0)

        box_handling = QGroupBox("Handling")
        f2 = QFormLayout(box_handling)
        f2.addRow("Video", self.b.combo("video_handling"))
        f2.addRow("Audio", self.b.combo("audio_handling"))
        g.addWidget(box_handling, 1, 1)
        return page

    def _tab_crop_resize(self):
        page = QWidget()
        h = QHBoxLayout(page)
        crop = QGroupBox("Crop")
        f = QFormLayout(crop)
        f.addRow(self.b.check("crop_enabled", "Picture crop"))
        f.addRow("Left", self.b.spin("crop_left", 0, 2000, 2))
        f.addRow("Top", self.b.spin("crop_top", 0, 2000, 2))
        f.addRow("Right", self.b.spin("crop_right", 0, 2000, 2))
        f.addRow("Bottom", self.b.spin("crop_bottom", 0, 2000, 2))
        auto = QPushButton("Auto crop (fichier sélectionné)")
        auto.clicked.connect(self._auto_crop)
        f.addRow(auto)
        h.addWidget(crop)

        res = QGroupBox("Resize")
        f = QFormLayout(res)
        f.addRow("Pixel aspect ratio (PAR)", self.b.combo("par_mode"))
        f.addRow(QLabel("« auto to 1:1 » convertit en pixels carrés (DV PAL 4:3 → 720x540 ou 768x576)."))
        f.addRow(self.b.check("resize_enabled", "Picture resize manuel (prioritaire sur le PAR auto)"))
        f.addRow("Width", self.b.spin("resize_width", 16, 7680, 2))
        f.addRow("Height", self.b.spin("resize_height", 16, 4320, 2))
        f.addRow("Resizer", self.b.combo("resizer"))
        f.addRow("Bicubic b", self.b.dspin("bicubic_b", -1, 1, 0.05))
        f.addRow("Bicubic c", self.b.dspin("bicubic_c", -1, 1, 0.05))
        presets = QHBoxLayout()
        for text, wh in (("720x540 (4:3)", (720, 540)), ("768x576 (4:3)", (768, 576)),
                         ("1024x576 (16:9)", (1024, 576)), ("1440x1080 (4:3 HD)", (1440, 1080))):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, wh=wh: (self.b.w["resize_width"].setValue(wh[0]),
                                                       self.b.w["resize_height"].setValue(wh[1])))
            presets.addWidget(btn)
        f.addRow(presets)
        h.addWidget(res)
        return page

    def _tab_filtering(self):
        inner = QTabWidget()
        self.filter_tabs = inner

        dei = QWidget()
        v = QVBoxLayout(dei)
        top = QGroupBox("Deinterlace/Telecine settings")
        f = QFormLayout(top)
        f.addRow("Deinterlacer", self.b.combo("deinterlacer"))
        f.addRow("Overwrite input scan type", self.b.combo("scan_type"))
        f.addRow("", self.b.check("qtgmc_bob", "Bob (25i → 50p, une image par champ)"))
        v.addWidget(top)
        q = QGroupBox("QTGMC")
        f = QFormLayout(q)
        f.addRow("Preset", self.b.combo("qtgmc_preset"))
        f.addRow("TR0", self.b.spin("qtgmc_tr0", -1, 2, auto="auto"))
        f.addRow("TR1", self.b.spin("qtgmc_tr1", -1, 2, auto="auto"))
        f.addRow("TR2", self.b.spin("qtgmc_tr2", -1, 3, auto="auto"))
        f.addRow("Sharpness", self.b.dspin("qtgmc_sharpness", -0.1, 2, 0.1, auto="auto"))
        f.addRow("SourceMatch", self.b.spin("qtgmc_source_match", 0, 3))
        f.addRow("Lossless", self.b.spin("qtgmc_lossless", 0, 2))
        f.addRow("Additional parameters", self.b.line("qtgmc_extra", "ex. EdiMode='NNEDI3', ShutterBlur=1"))
        v.addWidget(q)
        v.addStretch(1)
        inner.addTab(dei, "(De-)Interlace/Telecine")

        vsyn = QTabWidget()
        self.vs_tabs = vsyn
        inner.addTab(vsyn, "Vapoursynth")

        col = QWidget()
        v = QVBoxLayout(col)
        box = QGroupBox("Color")
        f = QFormLayout(box)
        f.addRow(self.b.check("color_matrix_to_709", "Color matrix → Rec.709"))
        f.addRow("Source matrix", self.b.combo("color_matrix_source"))
        f.addRow(QLabel("auto : Rec.601 pour la SD (DV PAL/NTSC), Rec.709 pour la HD."))
        v.addWidget(box)
        v.addStretch(1)
        vsyn.addTab(col, "Color")

        den = QWidget()
        v = QVBoxLayout(den)
        box = QGroupBox("DeNoise")
        f = QFormLayout(box)
        f.addRow(self.b.check("denoise_enabled", "Activer le débruitage"))
        f.addRow("Denoiser", self.b.combo("denoiser"))
        f.addRow("MDegrain radius", self.b.spin("mdegrain_radius", 1, 3))
        f.addRow("MDegrain thSAD", self.b.spin("mdegrain_thsad", 50, 2000, 25))
        f.addRow("MDegrain block size", self.b.spin("mdegrain_blksize", 4, 64, 4))
        f.addRow("DFTTest sigma", self.b.dspin("dfttest_sigma", 0, 64, 0.5))
        v.addWidget(box)
        v.addStretch(1)
        vsyn.addTab(den, "DeNoise")

        deh = QWidget()
        v = QVBoxLayout(deh)
        box = QGroupBox()
        g = QGridLayout(box)
        g.addWidget(self.b.check("finedehalo_enabled", "FineDehalo"), 0, 0, 3, 1)

        def pair(row, col, label, a, b):
            h = QHBoxLayout()
            h.addWidget(a)
            h.addWidget(QLabel("/"))
            h.addWidget(b)
            g.addWidget(QLabel(label), row, col)
            g.addLayout(h, row, col + 1)

        pair(0, 1, "Radius (x/y):", self.b.dspin("fdh_rx", 0, 10, 0.1, 1), self.b.dspin("fdh_ry", 0, 10, 0.1, 1))
        pair(1, 1, "Strength:", self.b.dspin("fdh_darkstr", 0, 10, 0.1, 2), self.b.dspin("fdh_brightstr", 0, 10, 0.1, 2))
        g.addWidget(QLabel("Edge processing:"), 2, 1)
        g.addWidget(self.b.dspin("fdh_edgeproc", 0, 100, 0.1, 2), 2, 2)
        pair(0, 3, "Edge threshold (min/max):", self.b.spin("fdh_thmi", 0, 255), self.b.spin("fdh_thma", 0, 255))
        pair(1, 3, "Limit threshold (min/max):", self.b.spin("fdh_thlimi", 0, 255), self.b.spin("fdh_thlima", 0, 255))
        g.addWidget(self.b.check("fdh_excl", "Exclusion zone"), 2, 4)
        g.addWidget(QLabel("Show mask:"), 0, 5)
        g.addWidget(self.b.combo("fdh_showmask"), 0, 6)
        g.addWidget(QLabel("Contrast sharpening:"), 1, 5)
        g.addWidget(self.b.dspin("fdh_contra", 0, 10, 0.1, 2), 1, 6)
        v.addWidget(box)
        v.addWidget(QLabel("Strength = force sur les halos sombres / clairs (darkstr / brightstr)."))
        v.addStretch(1)
        vsyn.addTab(deh, "DeHalo")

        cus = QWidget()
        v = QVBoxLayout(cus)
        v.addWidget(QLabel("Code VapourSynth exécuté à la fin du filtrage (variables : vs, core, clip)."))
        v.addWidget(self.b.text("vs_custom_code", "clip = core.std.Levels(clip, ...)"))
        vsyn.addTab(cus, "Custom")
        return inner

    def _tab_prores(self):
        page = QWidget()
        f = QFormLayout(page)
        f.addRow("Encoder", self.b.combo("prores_encoder"))
        f.addRow("Profile", self.b.combo("prores_profile"))
        f.addRow(QLabel("Standard = ProRes 422.  Proxy / LT / Standard / HQ : 4:2:2 10 bits.  4444 / 4444 XQ : 4:4:4 10 bits.\n"
                        "VideoToolbox utilise l'encodeur matériel d'Apple (plus rapide)."))
        return page

    def _tab_x26x(self):
        page = QWidget()
        f = QFormLayout(page)
        f.addRow("Rate control", self.b.combo("x26x_rate_control"))
        f.addRow("CRF", self.b.dspin("x26x_crf", 0, 51, 0.5, 1))
        f.addRow("Bitrate (kbit/s)", self.b.spin("x26x_bitrate", 100, 200000, 100))
        f.addRow("Preset", self.b.combo("x26x_preset"))
        f.addRow("Tune", self.b.combo("x26x_tune"))
        f.addRow("Additional FFmpeg options", self.b.line("x26x_extra", "ex. -profile:v high -level 4.1"))
        return page

    def _tab_ffv1(self):
        page = QWidget()
        f = QFormLayout(page)
        f.addRow("Level", self.b.spin("ffv1_level", 1, 3))
        return page

    def _tab_audio(self):
        page = QWidget()
        f = QFormLayout(page)
        f.addRow("Bitrate AAC (kbit/s)", self.b.spin("audio_bitrate", 32, 512, 32))
        f.addRow("Sample rate", self.b.combo("audio_samplerate"))
        f.addRow(QLabel("Le choix passthrough / AAC / PCM se fait dans l'onglet Base.\n"
                        "Les fichiers DV ont souvent une 2e piste muette : « first track » ne garde que la 1re."))
        return page

    def _tab_jobs(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Source", "Output", "Status", "Progress"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.addWidget(self.table)
        row = QHBoxLayout()
        for text, slot in (("Remove selected", self.remove_jobs), ("Clear finished", self.clear_finished),
                           ("Reset selected to waiting", self.reset_jobs), ("Open output folder", self.open_output)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        v.addLayout(row)
        return page

    def _tab_config(self):
        page = QWidget()
        v = QVBoxLayout(page)
        prof = QGroupBox("Profiles")
        h = QHBoxLayout(prof)
        self.profile_box = QComboBox()
        self._refresh_profiles()
        h.addWidget(self.profile_box, 1)
        for text, slot in (("Load", self.load_profile), ("Save as…", self.save_profile),
                           ("Delete", self.delete_profile), ("Reset to defaults", lambda: self.b.write(st.Settings()))):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            h.addWidget(btn)
        v.addWidget(prof)

        imp = QGroupBox("Hybrid")
        h = QHBoxLayout(imp)
        for text, slot in (("Import Hybrid profile (.xml)…", self.import_hybrid_file),
                           ("Import Hybrid settings folder…", self.import_hybrid_folder)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            h.addWidget(btn)
        v.addWidget(imp)

        eng = QGroupBox("Engine")
        h = QHBoxLayout(eng)
        for text, slot in (("Check engine", self.check_engine), ("Open logs folder", self.open_logs)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            h.addWidget(btn)
        v.addWidget(eng)
        v.addStretch(1)
        return page

    def _tab_logs(self):
        page = QWidget()
        v = QVBoxLayout(page)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(20000)
        v.addWidget(self.logbox)
        return page

    def _menus(self):
        m = self.menuBar().addMenu("File")
        for text, slot in (("Add files…", self.add_files_dialog), ("Add to queue", self.add_to_queue),
                           ("Start queue", self.start_queue), ("Quit", self.close)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            m.addAction(a)
        h = self.menuBar().addMenu("Help")
        a = QAction("About 822.DV", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "822.DV", f"822.DV {VERSION}\nInterface pour VapourSynth / QTGMC et FFmpeg.\n"
                            "Outils intégrés : VapourSynth, havsfunc, MVTools, BestSource, FFmpeg (logiciels libres)."))
        h.addAction(a)

    # ---------------------------------------------------------------- utilitaires
    def log(self, msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        for line in str(msg).splitlines() or [""]:
            self.logbox.appendPlainText(f"{stamp}  {line}")
        try:
            os.makedirs(st.LOG_DIR, exist_ok=True)
            with open(os.path.join(st.LOG_DIR, "822dv.log"), "a", encoding="utf-8") as f:
                f.write(f"{stamp}  {msg}\n")
        except OSError:
            pass

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_inputs([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])

    def add_files_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Choisir des vidéos", "", VIDEO_FILTER)
        self.add_inputs(files)

    def add_inputs(self, files):
        for f in files:
            if os.path.isfile(f):
                self.inputs.addItem(f)
        if self.inputs.count() and self.inputs.currentRow() < 0:
            self.inputs.setCurrentRow(0)

    def remove_inputs(self):
        for item in self.inputs.selectedItems():
            self.inputs.takeItem(self.inputs.row(item))

    def _selected_input(self):
        item = self.inputs.currentItem()
        return item.text() if item else None

    def _show_info(self, *_):
        src = self._selected_input()
        if not src:
            return
        try:
            self.info.setText(engine.describe(engine.probe(src)))
        except Exception as e:  # noqa: BLE001
            self.info.setText(f"Impossible d'analyser : {e}")

    def _pick_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Dossier de sortie", self.b.w["output_dir"].text())
        if d:
            self.b.w["output_dir"].setText(d)

    def _auto_crop(self):
        src = self._selected_input()
        if not src:
            QMessageBox.information(self, "Auto crop", "Sélectionne d'abord un fichier dans l'onglet Base.")
            return
        l, t, r, b = engine.auto_crop(src, engine.probe(src))
        for name, val in (("crop_left", l), ("crop_top", t), ("crop_right", r), ("crop_bottom", b)):
            self.b.w[name].setValue(val)
        self.b.w["crop_enabled"].setChecked(any((l, t, r, b)))
        self.log(f"Auto crop : gauche {l}, haut {t}, droite {r}, bas {b}")

    # ---------------------------------------------------------------- file d'attente
    def add_to_queue(self):
        files = [self.inputs.item(i).text() for i in range(self.inputs.count())]
        if not files:
            QMessageBox.information(self, "822.DV", "Ajoute d'abord des fichiers dans l'onglet Base.")
            return
        s = self.b.read()
        st.save(s)
        for src in files:
            job = {"id": self.next_id, "src": src, "settings": st.Settings(**asdict(s)),
                   "out": engine.output_path(s, src), "status": "waiting"}
            self.next_id += 1
            self.jobs.append(job)
        self._refresh_table()
        self.log(f"{len(files)} job(s) ajouté(s) à la file.")
        self.tabs.setCurrentIndex(self.tabs.indexOf(self.table.parentWidget()))

    def _refresh_table(self):
        self.table.setRowCount(len(self.jobs))
        for r, job in enumerate(self.jobs):
            for c, text in enumerate((os.path.basename(job["src"]), os.path.basename(job["out"]),
                                      job["status"], job.get("progress", ""))):
                self.table.setItem(r, c, QTableWidgetItem(str(text)))

    def _row_of(self, jid):
        return next((i for i, j in enumerate(self.jobs) if j["id"] == jid), None)

    def _on_status(self, jid, status):
        r = self._row_of(jid)
        if r is not None:
            self.jobs[r]["status"] = status
            self.table.setItem(r, 2, QTableWidgetItem(status))

    def _on_progress(self, jid, pct):
        r = self._row_of(jid)
        if r is not None:
            self.jobs[r]["progress"] = f"{pct} %"
            self.table.setItem(r, 3, QTableWidgetItem(f"{pct} %"))
        self.bar.setValue(pct)

    def start_queue(self):
        if self.worker and self.worker.isRunning():
            return
        if not any(j["status"] == "waiting" for j in self.jobs):
            QMessageBox.information(self, "822.DV", "Aucun job en attente. Clique d'abord sur « Add to queue ».")
            return
        self.worker = QueueWorker(self.jobs)
        self.worker.log.connect(self.log)
        self.worker.status.connect(self._on_status)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._queue_done)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker.start()

    def stop_queue(self):
        if self.worker:
            self.worker.cancel.set()
            self.log("Arrêt demandé…")

    def _queue_done(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("File terminée.")

    def remove_jobs(self):
        if self.worker and self.worker.isRunning():
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.jobs[r]
        self._refresh_table()

    def clear_finished(self):
        if self.worker and self.worker.isRunning():
            return
        self.jobs = [j for j in self.jobs if j["status"] != "finished"]
        self._refresh_table()

    def reset_jobs(self):
        for r in {i.row() for i in self.table.selectedIndexes()}:
            self.jobs[r]["status"] = "waiting"
            self.jobs[r]["progress"] = ""
        self._refresh_table()

    def open_output(self):
        d = os.path.expanduser(self.b.w["output_dir"].text())
        os.makedirs(d, exist_ok=True)
        subprocess.Popen(["open", d])

    # ---------------------------------------------------------------- profils et config
    def _refresh_profiles(self):
        self.profile_box.clear()
        self.profile_box.addItems(st.profiles())

    def save_profile(self):
        name, ok = QInputDialog.getText(self, "Save profile", "Nom du profil :")
        if ok and name.strip():
            st.save(self.b.read(), st.profile_path(name.strip()))
            self._refresh_profiles()
            self.profile_box.setCurrentText(name.strip())
            self.log(f"Profil enregistré : {name.strip()}")

    def load_profile(self):
        name = self.profile_box.currentText()
        if name:
            self.b.write(st.load(st.profile_path(name)))
            self.log(f"Profil chargé : {name}")

    def delete_profile(self):
        name = self.profile_box.currentText()
        if name and QMessageBox.question(self, "Delete", f"Supprimer le profil « {name} » ?") == QMessageBox.Yes:
            os.remove(st.profile_path(name))
            self._refresh_profiles()

    def _import_hybrid(self, path):
        if not path:
            return
        s, n = st.import_hybrid(path, self.b.read())
        self.b.write(s)
        self.log(f"Import Hybrid : {n} réglage(s) repris depuis {path}")
        QMessageBox.information(self, "Hybrid", f"{n} réglage(s) repris. Vérifie les onglets, puis enregistre un profil.")

    def import_hybrid_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Profil Hybrid", "", "Profils Hybrid (*.xml)")
        self._import_hybrid(f)

    def import_hybrid_folder(self):
        self._import_hybrid(QFileDialog.getExistingDirectory(self, "Dossier de réglages Hybrid"))

    def check_engine(self):
        self.log(engine.engine_report())
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def open_logs(self):
        os.makedirs(st.LOG_DIR, exist_ok=True)
        subprocess.Popen(["open", st.LOG_DIR])

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            if QMessageBox.question(self, "822.DV", "Un traitement est en cours. Quitter quand même ?") != QMessageBox.Yes:
                e.ignore()
                return
            self.worker.cancel.set()
            self.worker.wait(5000)
        try:
            st.save(self.b.read())
        except OSError:
            pass
        super().closeEvent(e)


def run_gui():
    app = QApplication(sys.argv)
    app.setApplicationName("822.DV")
    icon = paths.icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
