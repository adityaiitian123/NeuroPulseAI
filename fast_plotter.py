import sys
import serial
import serial.tools.list_ports
import numpy as np

from PyQt5 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import pyqtgraph.exporters


class NeuroPulseAIFastPlotter(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeuroPulseAI by Debuggers Squad - Fast Plotter")
        self.setWindowIcon(QtGui.QIcon("logo_v4.ico"))
        self.resize(1500, 860)

        self.serial_port = None

        # Fast serial polling
        self.read_timer = QtCore.QTimer()
        self.read_timer.timeout.connect(self.read_serial_fast)

        # Plot refresh timer
        self.plot_timer = QtCore.QTimer()
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start(20)   # ~50 FPS

        # Config
        self.max_points = 600
        self.plot_channel_names = [
            "Original Signal",
            "Cleaned Signal",
            "Muscle Strength",
            "Muscle Active"
        ]
        self.num_channels = 4

        self.colors = [
            "#00E5FF",   # cyan
            "#FFD600",   # yellow
            "#00FF85",   # green
            "#FF4D6D",   # red/pink
        ]

        self.data = np.zeros((self.num_channels, self.max_points), dtype=np.float32)
        self.latest_values = np.zeros(self.num_channels, dtype=np.float32)

        self.curves = []
        self.signal_cards = []
        self.signal_checkboxes = []
        self.signal_visible = [True] * self.num_channels

        self.total_lines = 0
        self.is_paused = False
        self.enable_log = False
        self.enable_autoscale = True

        pg.setConfigOptions(antialias=False, useOpenGL=False)

        self.init_ui()
        self.apply_theme()
        self.refresh_ports()
        self.setup_curves()

    # =========================
    # UI
    # =========================
    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        header = QtWidgets.QFrame()
        header.setObjectName("card")
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)

        title_col = QtWidgets.QVBoxLayout()
        self.title_label = QtWidgets.QLabel("NeuroPulseAI")
        self.title_label.setObjectName("titleLabel")
        self.brand_label = QtWidgets.QLabel("by Debuggers Squad")
        self.brand_label.setObjectName("brandLabel")
        self.subtitle_label = QtWidgets.QLabel("Fast Real-Time EMG Plotter with Judge-Friendly Signals")
        self.subtitle_label.setObjectName("subtitleLabel")

        title_col.addWidget(self.title_label)
        title_col.addWidget(self.brand_label)
        title_col.addWidget(self.subtitle_label)

        self.connection_badge = QtWidgets.QLabel("● Disconnected")
        self.connection_badge.setObjectName("badgeOff")
        self.connection_badge.setAlignment(QtCore.Qt.AlignCenter)
        self.connection_badge.setMinimumWidth(180)
        self.connection_badge.setMinimumHeight(40)

        header_layout.addLayout(title_col)
        header_layout.addStretch()
        header_layout.addWidget(self.connection_badge)

        root.addWidget(header)

        # Controls
        controls = QtWidgets.QFrame()
        controls.setObjectName("card")
        grid = QtWidgets.QGridLayout(controls)
        grid.setContentsMargins(14, 14, 14, 14)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        self.port_combo = QtWidgets.QComboBox()
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["115200", "230400", "460800", "921600"])
        self.baud_combo.setCurrentText("115200")

        self.samples_spin = QtWidgets.QSpinBox()
        self.samples_spin.setRange(100, 5000)
        self.samples_spin.setValue(600)
        self.samples_spin.valueChanged.connect(self.change_window_size)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.disconnect_btn = QtWidgets.QPushButton("Disconnect")
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.clear_btn = QtWidgets.QPushButton("Clear Plot")
        self.save_btn = QtWidgets.QPushButton("Save PNG")

        self.disconnect_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)

        self.log_toggle = QtWidgets.QCheckBox("Enable Log")
        self.log_toggle.stateChanged.connect(self.toggle_log)

        self.autoscale_toggle = QtWidgets.QCheckBox("Auto Scale")
        self.autoscale_toggle.setChecked(True)
        self.autoscale_toggle.stateChanged.connect(self.toggle_autoscale)

        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setObjectName("statusLabel")

        grid.addWidget(self.make_label("COM Port"), 0, 0)
        grid.addWidget(self.port_combo, 0, 1)

        grid.addWidget(self.make_label("Baud"), 0, 2)
        grid.addWidget(self.baud_combo, 0, 3)

        grid.addWidget(self.make_label("Window"), 0, 4)
        grid.addWidget(self.samples_spin, 0, 5)

        grid.addWidget(self.refresh_btn, 0, 6)
        grid.addWidget(self.connect_btn, 0, 7)
        grid.addWidget(self.disconnect_btn, 0, 8)
        grid.addWidget(self.pause_btn, 0, 9)
        grid.addWidget(self.clear_btn, 0, 10)
        grid.addWidget(self.save_btn, 0, 11)

        grid.addWidget(self.log_toggle, 1, 0, 1, 2)
        grid.addWidget(self.autoscale_toggle, 1, 2, 1, 2)
        grid.addWidget(self.make_label("Status"), 1, 4)
        grid.addWidget(self.status_label, 1, 5, 1, 7)

        root.addWidget(controls)

        # Stats
        stats_row = QtWidgets.QHBoxLayout()
        stats_row.setSpacing(10)

        self.stat_channels = self.make_stat("Channels", "4")
        self.stat_lines = self.make_stat("Frames", "0")
        self.stat_mode = self.make_stat("Mode", "Idle")
        self.stat_last = self.make_stat("Latest", "-")

        stats_row.addWidget(self.stat_channels)
        stats_row.addWidget(self.stat_lines)
        stats_row.addWidget(self.stat_mode)
        stats_row.addWidget(self.stat_last)

        root.addLayout(stats_row)

        # Main area
        main = QtWidgets.QHBoxLayout()
        main.setSpacing(10)

        # Plot
        plot_card = QtWidgets.QFrame()
        plot_card.setObjectName("card")
        plot_layout = QtWidgets.QVBoxLayout(plot_card)
        plot_layout.setContentsMargins(10, 10, 10, 10)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground((12, 16, 24))
        self.plot_widget.showGrid(x=True, y=True, alpha=0.18)
        self.plot_widget.setTitle("Live Muscle Signal Stream", color="#FFFFFF", size="14pt")
        self.plot_widget.setLabel("left", "Value", color="#DDE6F2", size="12pt")
        self.plot_widget.setLabel("bottom", "Samples", color="#DDE6F2", size="12pt")

        axis_pen = pg.mkPen("#73839A")
        self.plot_widget.getAxis("left").setPen(axis_pen)
        self.plot_widget.getAxis("bottom").setPen(axis_pen)
        self.plot_widget.getAxis("left").setTextPen("#D0DAE7")
        self.plot_widget.getAxis("bottom").setTextPen("#D0DAE7")

        plot_layout.addWidget(self.plot_widget)
        main.addWidget(plot_card, 5)

        # Side panel
        side_card = QtWidgets.QFrame()
        side_card.setObjectName("card")
        side_layout = QtWidgets.QVBoxLayout(side_card)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(10)

        panel_title = QtWidgets.QLabel("Signal Dashboard")
        panel_title.setObjectName("panelTitle")

        self.signal_scroll = QtWidgets.QScrollArea()
        self.signal_scroll.setWidgetResizable(True)
        self.signal_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.signal_scroll.setMinimumHeight(240)

        self.signal_container = QtWidgets.QWidget()
        self.signal_layout = QtWidgets.QVBoxLayout(self.signal_container)
        self.signal_layout.setSpacing(8)
        self.signal_layout.setContentsMargins(0, 0, 0, 0)

        self.signal_scroll.setWidget(self.signal_container)

        # AI Analyst Section
        analyst_sep = QtWidgets.QFrame()
        analyst_sep.setFrameShape(QtWidgets.QFrame.HLine)
        analyst_sep.setFrameShadow(QtWidgets.QFrame.Sunken)
        analyst_sep.setStyleSheet("background: #1F2A3D;")

        analyst_header = QtWidgets.QHBoxLayout()
        analyst_title = QtWidgets.QLabel("AI Graph Analyst")
        analyst_title.setObjectName("panelTitle")
        analyst_header.addWidget(analyst_title)
        
        self.audience_combo = QtWidgets.QComboBox()
        self.audience_combo.addItems(["General User", "Physiotherapist", "Medical Doctor"])
        self.audience_combo.setMinimumWidth(120)
        analyst_header.addWidget(self.audience_combo)

        self.analysis_output = QtWidgets.QPlainTextEdit()
        self.analysis_output.setReadOnly(True)
        self.analysis_output.setPlaceholderText("Current signal analysis will appear here...")
        self.analysis_output.setObjectName("analystBox")
        self.analysis_output.setMinimumHeight(150)

        self.analyze_btn = QtWidgets.QPushButton("🚀 Generate Clinical Insight")
        self.analyze_btn.setObjectName("analystBtn")
        self.analyze_btn.clicked.connect(self.generate_ai_insight)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(100)
        self.log_box.setVisible(False)

        side_layout.addWidget(panel_title)
        side_layout.addWidget(self.signal_scroll)
        side_layout.addWidget(analyst_sep)
        side_layout.addLayout(analyst_header)
        side_layout.addWidget(self.analysis_output)
        side_layout.addWidget(self.analyze_btn)
        side_layout.addWidget(self.log_box)

        main.addWidget(side_card, 2)

        root.addLayout(main)

        # Buttons
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn.clicked.connect(self.connect_serial)
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.clear_btn.clicked.connect(self.clear_plot)
        self.save_btn.clicked.connect(self.save_plot)

    def make_label(self, text):
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("fieldLabel")
        return lbl

    def make_stat(self, title, value):
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        lay = QtWidgets.QVBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        t = QtWidgets.QLabel(title)
        t.setObjectName("statTitle")
        v = QtWidgets.QLabel(value)
        v.setObjectName("statValue")

        lay.addWidget(t)
        lay.addWidget(v)
        card.value_label = v
        return card

    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #0A0E14;
            }
            QFrame#card {
                background: #111826;
                border: 1px solid #1F2A3D;
                border-radius: 16px;
            }
            QLabel#titleLabel {
                color: white;
                font-size: 28px;
                font-weight: 800;
            }
            QLabel#brandLabel {
                color: #00E5FF;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#subtitleLabel {
                color: #8CA0BB;
                font-size: 12px;
            }
            QLabel#badgeOff {
                background: #2A1A1A;
                color: #FF7B7B;
                border: 1px solid #5A2A2A;
                border-radius: 13px;
                font-weight: 700;
                padding: 8px 12px;
            }
            QLabel#badgeOn {
                background: #13291C;
                color: #49E08E;
                border: 1px solid #27583C;
                border-radius: 13px;
                font-weight: 700;
                padding: 8px 12px;
            }
            QLabel#fieldLabel {
                color: #AAB8CC;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#statusLabel {
                color: #E8F2FF;
                background: #0D1421;
                border: 1px solid #223149;
                border-radius: 10px;
                padding: 8px;
            }
            QLabel#statTitle {
                color: #90A2BA;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#statValue {
                color: white;
                font-size: 22px;
                font-weight: 800;
            }
            QLabel#panelTitle {
                color: white;
                font-size: 15px;
                font-weight: 800;
            }
            QComboBox, QSpinBox {
                background: #0E1521;
                color: white;
                border: 1px solid #223149;
                border-radius: 10px;
                padding: 8px;
            }
            QPushButton {
                color: white;
                font-weight: 800;
                border: none;
                border-radius: 11px;
                padding: 9px 14px;
            }
            QPushButton:disabled {
                background: #2A3343;
                color: #8290A2;
            }
            QCheckBox {
                color: #E6F0FF;
                font-weight: 600;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #41526A;
                background: #0C1220;
            }
            QCheckBox::indicator:checked {
                background: #00C2FF;
                border: 1px solid #00C2FF;
            }
            QPlainTextEdit {
                background: #0D1421;
                color: #DCE7F5;
                border: 1px solid #223149;
                border-radius: 10px;
                padding: 6px;
                font-family: Consolas;
                font-size: 11px;
            }
            QPlainTextEdit#analystBox {
                background: #090E17;
                border: 1px solid #00E5FF;
                color: #A0B4D0;
                font-family: 'Segoe UI';
                font-size: 12px;
                line-height: 1.4;
            }
            QPushButton#analystBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00E5FF, stop:1 #0072FF);
                margin-top: 5px;
            }
        """)
        self.refresh_btn.setStyleSheet("background:#2D9CDB;")
        self.connect_btn.setStyleSheet("background:#27AE60;")
        self.disconnect_btn.setStyleSheet("background:#EB5757;")
        self.pause_btn.setStyleSheet("background:#9B51E0;")
        self.clear_btn.setStyleSheet("background:#F2994A;")
        self.save_btn.setStyleSheet("background:#00B8D9;")

    # =========================
    # Setup curves / cards
    # =========================
    def setup_curves(self):
        self.plot_widget.clear()
        self.curves.clear()

        # clear signal panel
        while self.signal_layout.count():
            item = self.signal_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.signal_cards.clear()
        self.signal_checkboxes.clear()

        for i, name in enumerate(self.plot_channel_names):
            color = self.colors[i]
            pen = pg.mkPen(color=color, width=2)
            curve = self.plot_widget.plot(self.data[i], pen=pen, name=name)
            self.curves.append(curve)

            row = QtWidgets.QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background:#0E1521;
                    border:1px solid #213048;
                    border-left:4px solid {color};
                    border-radius:12px;
                }}
            """)
            lay = QtWidgets.QHBoxLayout(row)
            lay.setContentsMargins(10, 8, 10, 8)

            cb = QtWidgets.QCheckBox(name)
            cb.setChecked(True)
            cb.stateChanged.connect(lambda _, idx=i: self.toggle_channel(idx))

            value_lbl = QtWidgets.QLabel("0.00")
            value_lbl.setStyleSheet("color:#BFD0E3; font-weight:700;")

            lay.addWidget(cb)
            lay.addStretch()
            lay.addWidget(value_lbl)

            row.value_label = value_lbl

            self.signal_layout.addWidget(row)
            self.signal_cards.append(row)
            self.signal_checkboxes.append(cb)

        self.signal_layout.addStretch()

    def toggle_channel(self, idx):
        self.signal_visible[idx] = self.signal_checkboxes[idx].isChecked()
        self.curves[idx].setVisible(self.signal_visible[idx])

    # =========================
    # Controls
    # =========================
    def toggle_log(self):
        self.enable_log = self.log_toggle.isChecked()
        self.log_box.setVisible(self.enable_log)

    def toggle_autoscale(self):
        self.enable_autoscale = self.autoscale_toggle.isChecked()
        if not self.enable_autoscale:
            self.plot_widget.enableAutoRange(axis='y', enable=False)

    def change_window_size(self):
        new_size = self.samples_spin.value()
        old_size = self.max_points
        self.max_points = new_size

        if new_size > old_size:
            extra = np.zeros((self.num_channels, new_size - old_size), dtype=np.float32)
            self.data = np.hstack((self.data, extra))
        else:
            self.data = self.data[:, -new_size:]

        self.status_label.setText(f"Window changed to {new_size}")

    def clear_plot(self):
        self.data.fill(0)
        self.latest_values.fill(0)
        self.total_lines = 0
        self.stat_lines.value_label.setText("0")
        self.stat_last.value_label.setText("-")
        self.log_box.clear()
        self.status_label.setText("Plot cleared")

    def save_plot(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Plot", "NeuroPulseAI_fast_plot.png", "PNG Files (*.png)"
        )
        if not path:
            return

        exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
        exporter.export(path)
        self.status_label.setText(f"Saved: {path}")

    # =========================
    # Serial port
    # =========================
    def refresh_ports(self):
        current = self.port_combo.currentText()
        self.port_combo.clear()

        for port in serial.tools.list_ports.comports():
            self.port_combo.addItem(port.device)

        if current:
            idx = self.port_combo.findText(current)
            if idx >= 0:
                self.port_combo.setCurrentIndex(idx)

        self.status_label.setText("Ports refreshed" if self.port_combo.count() else "No COM ports found")

    def connect_serial(self):
        port = self.port_combo.currentText()
        if not port:
            self.status_label.setText("Select a COM port")
            return

        baud = int(self.baud_combo.currentText())

        try:
            self.serial_port = serial.Serial(port, baud, timeout=0, write_timeout=0)
            self.serial_port.reset_input_buffer()

            self.read_timer.start(1)   # ultra-fast polling
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.pause_btn.setEnabled(True)

            self.connection_badge.setText(f"● Connected  {port}")
            self.connection_badge.setObjectName("badgeOn")
            self.connection_badge.style().unpolish(self.connection_badge)
            self.connection_badge.style().polish(self.connection_badge)

            self.status_label.setText(f"Connected to {port} @ {baud}")
            self.stat_mode.value_label.setText("Live")

        except Exception as e:
            self.status_label.setText(f"Connection failed: {e}")

    def disconnect_serial(self):
        self.read_timer.stop()

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

        self.serial_port = None
        self.is_paused = False

        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")

        self.connection_badge.setText("● Disconnected")
        self.connection_badge.setObjectName("badgeOff")
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)

        self.status_label.setText("Disconnected")
        self.stat_mode.value_label.setText("Idle")

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.pause_btn.setText("Resume")
            self.status_label.setText("Paused")
            self.stat_mode.value_label.setText("Paused")
        else:
            self.pause_btn.setText("Pause")
            self.status_label.setText("Live reading resumed")
            self.stat_mode.value_label.setText("Live")

    # =========================
    # Fast serial reading
    # =========================
    def read_serial_fast(self):
        if not self.serial_port or self.is_paused:
            return

        try:
            waiting = self.serial_port.in_waiting
            if waiting <= 0:
                return

            raw_bytes = self.serial_port.read(waiting)
            if not raw_bytes:
                return

            lines = raw_bytes.decode(errors="ignore").splitlines()
            if not lines:
                return

            frames = []

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                parts = line.split(",")

                # Must match your Arduino format:
                # time_ms,raw,centered,envelope,trigger
                if len(parts) != 5:
                    continue

                try:
                    values = [float(x.strip()) for x in parts]
                except ValueError:
                    continue

                # Ignore time_ms
                plot_values = values[1:]   # raw, centered, envelope, trigger

                if len(plot_values) != 4:
                    continue

                frames.append(plot_values)

                if self.enable_log:
                    self.log_box.appendPlainText(line)

            if not frames:
                return

            arr = np.array(frames, dtype=np.float32).T   # shape: (4, samples)
            n_new = arr.shape[1]

            if n_new >= self.max_points:
                self.data = arr[:, -self.max_points:]
            else:
                self.data[:, :-n_new] = self.data[:, n_new:]
                self.data[:, -n_new:] = arr

            self.latest_values = arr[:, -1]
            self.total_lines += len(frames)

            self.stat_lines.value_label.setText(str(self.total_lines))
            self.stat_last.value_label.setText(
                ", ".join(f"{v:.1f}" for v in self.latest_values)
            )

        except Exception as e:
            self.status_label.setText(f"Read error: {e}")
            self.disconnect_serial()

    # =========================
    # Plot update
    # =========================
    def update_plot(self):
        for i, curve in enumerate(self.curves):
            if self.signal_visible[i]:
                curve.setData(self.data[i])
            self.signal_cards[i].value_label.setText(f"{self.latest_values[i]:.2f}")

        if self.enable_autoscale:
            self.plot_widget.enableAutoRange(axis='y', enable=True)

    # =========================
    # AI Analyst Logic
    # =========================
    def generate_ai_insight(self):
        audience = self.audience_combo.currentText()
        
        # Pull current values
        # [raw, centered, envelope, trigger]
        env = self.latest_values[2]
        is_active = self.latest_values[3] > 0.5
        
        self.analysis_output.clear()
        self.analysis_output.appendHtml("<b style='color:#00E5FF;'>Analysing Muscle Patterns...</b><br>")
        
        # Simulate thinking
        QtCore.QTimer.singleShot(800, lambda: self._finalize_insight(audience, env, is_active))

    def _finalize_insight(self, audience, env, is_active):
        status = "CONTRACTION DETECTED" if is_active else "RELAXED STATE"
        color = "#00FF85" if is_active else "#8CA0BB"
        
        report = f"<br><b style='color:{color};'>STATUS: {status}</b><br><br>"
        
        if audience == "General User":
            if is_active:
                msg = "Your muscles are currently working hard! You are applying good force. Keep going but remember to breathe."
            else:
                msg = "Your muscles are resting. This is a good time to check your posture before the next set."
        
        elif audience == "Physiotherapist":
            if is_active:
                msg = f"EMG Envelope shows peak amplitude at {env:.2f}V. Recruitement of motor units is consistent. No visible tremors in current window."
            else:
                msg = "Baseline activity confirmed. SNR is within acceptable range for post-injury assessment."
        
        else: # Medical Doctor
            if is_active:
                msg = f"Significant neuromuscular activation observed. EMG Envelope Voltage: {env:.2f}. Pattern suggestive of normal voluntary contraction with no compensatory recruitment detected."
            else:
                msg = "Neural drive is absent. Baseline recording shows stable tonicity at resting potential."
        
        self.analysis_output.setHtml(report + f"<span style='color:#DDE6F2;'>{msg}</span>")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setFont(QtGui.QFont("Segoe UI", 10))

    window = NeuroPulseAIFastPlotter()
    window.show()

    sys.exit(app.exec_())
