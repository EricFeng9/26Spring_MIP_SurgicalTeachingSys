import sys
import os
import cv2
import numpy as np
import json
import math

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QLabel, QSlider, QComboBox,
    QPushButton, QGroupBox, QFormLayout, QMessageBox,
    QScrollArea, QCheckBox, QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen


# =========================================================
# 理论物理模型
# =========================================================

class LaserPhysicalModel:
    def __init__(self, gt_params):
        self.gt_P = gt_params.get("power", 200.0)
        self.gt_S = gt_params.get("spot_size", 200.0)
        self.gt_T = gt_params.get("exposure_time", 100.0)
        self.gt_lam = gt_params.get("wavelength", 532.0)

        self.power_range = (50.0, 600.0)
        self.spot_range = (50.0, 500.0)
        self.duration_range = (10.0, 500.0)
        self.wavelengths = (532.0, 577.0, 672.0)

        self.tau_0 = 2.989
        self.tau_1 = 4.820
        self.tau_2 = 7.026
        self._initialize_z_bounds()

    def _compute_raw_z(self, P, S, T, lam):
        if S <= 0 or P <= 0 or T <= 0:
            return -999.0

        if lam == 532.0:
            k_color = 1.0
        elif lam == 577.0:
            k_color = 1.2
        elif lam == 672.0:
            k_color = 0.8
        else:
            k_color = 1.0

        term_time_log = math.log(T / 87.8)
        term_power_spot = 5.600 * k_color * (P / 160.8) * ((136.5 / S) ** 0.548)
        term_time_exp = 1.0 - math.exp(-(T / 1000.0) / 0.0492)
        return term_time_log + (term_power_spot * term_time_exp)

    def _initialize_z_bounds(self):
        p_vals = np.linspace(self.power_range[0], self.power_range[1], 20)
        s_vals = np.linspace(self.spot_range[0], self.spot_range[1], 20)
        t_vals = np.linspace(self.duration_range[0], self.duration_range[1], 20)

        raw_values = []
        for p in p_vals:
            for s in s_vals:
                for t in t_vals:
                    for lam in self.wavelengths:
                        raw_values.append(self._compute_raw_z(p, s, t, lam))

        raw_arr = np.array(raw_values)
        self.z_min_global = float(np.min(raw_arr))
        self.z_clinical_max = float(np.percentile(raw_arr, 90))

    def compute_z_and_grade(self, P, S, T, lam):
        z = self._compute_raw_z(P, S, T, lam)
        if z < self.tau_0:
            grade = 1
        elif z < self.tau_1:
            grade = 2
        elif z < self.tau_2:
            grade = 3
        else:
            grade = 4
        return z, grade

    def get_normalized_intensity(self, z):
        if self.z_clinical_max <= self.z_min_global:
            return 0.5
        vis = (z - self.z_min_global) / (self.z_clinical_max - self.z_min_global)
        return float(np.clip(vis, 0.0, 2.5))


# =========================================================
# 渲染工具
# =========================================================

FIXED_SIZE_GAIN = 1.75
CAMERA_BASE_HEX = {
    "ZEISS CLARUS": "#E7E984",
    "OPTOS 200": "#DBBF0D",
}


def _hex_to_bgr(hex_color: str) -> np.ndarray:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return np.array([b, g, r], dtype=np.float32)


def _color_to_lab_targets(bgr_color: np.ndarray):
    patch = np.uint8([[bgr_color]])
    lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    return float(lab[1]), float(lab[2])


def _smooth_noise(shape, sigma=3.0, seed=0):
    rng = np.random.default_rng(seed)
    n = rng.normal(0.0, 1.0, shape).astype(np.float32)
    k = int(max(3, sigma * 4) // 2 * 2 + 1)
    return cv2.GaussianBlur(n, (k, k), sigmaX=sigma, sigmaY=sigma)


def _grade_style(grade: int):
    table = {
        1: dict(core_gain=0.62, halo_gain=0.11, edge=3.1, hole=0.00, blur=1.4, sat_drop=0.22, v_lift=22, irregular=0.03),
        2: dict(core_gain=0.90, halo_gain=0.18, edge=3.8, hole=0.00, blur=1.3, sat_drop=0.30, v_lift=33, irregular=0.04),
        3: dict(core_gain=1.05, halo_gain=0.24, edge=4.3, hole=0.05, blur=1.2, sat_drop=0.36, v_lift=41, irregular=0.06),
        4: dict(core_gain=1.12, halo_gain=0.22, edge=4.7, hole=0.18, blur=1.0, sat_drop=0.40, v_lift=46, irregular=0.08),
    }
    return table.get(int(grade), table[2])


def render_laser_spot_test(
    img,
    center_x,
    center_y,
    power_mw,
    duration_ms,
    spot_size_um,
    wavelength_nm,
    pixel_to_um,
    model: LaserPhysicalModel,
    camera_type: str,
    opacity_gain: float,
    brightness_gain: float,
    irregular_gain: float,
    diffusion_blur_gain: float,
):
    z_val, grade = model.compute_z_and_grade(power_mw, spot_size_um, duration_ms, wavelength_nm)
    energy_n = model.get_normalized_intensity(z_val)

    if grade == 1:
        lo, hi = -999.0, model.tau_0
    elif grade == 2:
        lo, hi = model.tau_0, model.tau_1
    elif grade == 3:
        lo, hi = model.tau_1, model.tau_2
    else:
        lo, hi = model.tau_2, model.tau_2 + 3.0
    prog = float(np.clip((z_val - lo) / max(1e-6, hi - lo), 0.0, 1.0))

    style = _grade_style(grade)
    brightness_gain = max(0.5, float(brightness_gain))
    base_bgr = _hex_to_bgr(CAMERA_BASE_HEX.get(camera_type, CAMERA_BASE_HEX["ZEISS CLARUS"]))
    highlight_bgr = np.clip(base_bgr * 0.78 + np.array([255, 255, 255], dtype=np.float32) * 0.22, 0, 255)
    A_target, B_target = _color_to_lab_targets(base_bgr)

    lens_factor = 1.05
    retinal_beam_um = spot_size_um * lens_factor
    grade_gain = {1: 1.00, 2: 1.08, 3: 1.15, 4: 1.22}[grade]
    diff_gain = 1.0 + (0.08 + 0.12 * prog + 0.10 * max(0.0, energy_n - 0.8))
    final_lesion_um = retinal_beam_um * diff_gain * grade_gain * FIXED_SIZE_GAIN
    effective_radius = max(1.2, (final_lesion_um / 2.0) / max(pixel_to_um, 1e-6))

    grid_half = int(max(8, effective_radius * 2.9))
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half + 1)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half + 1)
    if x_min >= x_max or y_min >= y_max:
        return img, grade

    roi = img[y_min:y_max, x_min:x_max].copy().astype(np.float32)
    roi0 = roi.copy()
    hh, ww = roi.shape[:2]

    yy, xx = np.mgrid[y_min:y_max, x_min:x_max]
    dx = xx.astype(np.float32) - float(center_x)
    dy = yy.astype(np.float32) - float(center_y)
    theta = np.arctan2(dy, dx)
    rr = np.sqrt(dx * dx + dy * dy)

    shot_seed = int(np.random.default_rng().integers(0, 2**32 - 1, dtype=np.uint32))
    seed = (int(center_x * 73856093 ^ center_y * 19349663) ^ shot_seed) & 0xFFFFFFFF
    noise = _smooth_noise((hh, ww), sigma=max(1.1, effective_radius * 0.18), seed=seed)
    irr = max(0.0, float(irregular_gain))
    phase1 = float(np.random.default_rng(shot_seed ^ 0xA5A5A5A5).uniform(0.0, 2.0 * np.pi))
    phase2 = float(np.random.default_rng(shot_seed ^ 0x5A5A5A5A).uniform(0.0, 2.0 * np.pi))
    angular = irr * (0.028 * np.sin(3 * theta + phase1) + 0.018 * np.sin(5 * theta + phase2))
    radius_field = effective_radius * (1.0 + style["irregular"] * irr * noise + angular)
    r = rr / np.maximum(1e-6, radius_field)

    # 核心 + 热扩散晕环
    halo_width = max(0.55, float(diffusion_blur_gain))
    core = np.exp(-np.power(np.clip(r / 0.90, 0, None), style["edge"]))
    halo_outer = 1.28 + 0.26 * halo_width
    halo_inner = 0.94 + 0.05 * halo_width
    halo = np.exp(-np.power(np.clip(r / halo_outer, 0, None), 2.0)) - np.exp(-np.power(np.clip(r / halo_inner, 0, None), 2.0))
    halo = np.clip(halo, 0.0, 1.0)

    gray = cv2.cvtColor(roi0.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    vessel_dark = np.clip((0.45 - gray) / 0.45, 0.0, 1.0)
    vessel_dark = cv2.GaussianBlur(vessel_dark, (0, 0), sigmaX=1.2)
    vessel_atten = 1.0 - 0.45 * vessel_dark

    roi_lab = cv2.cvtColor(roi0.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = cv2.split(roi_lab)

    core_amp = style["core_gain"] * (0.74 + 0.34 * prog)
    halo_amp = style["halo_gain"] * (0.80 + 0.28 * prog)
    lift = ((style["v_lift"] * core_amp) * core * vessel_atten + (12.0 * halo_amp) * halo) * brightness_gain
    L_new = L + lift

    lesion_mask = np.clip(core * (0.86 + 0.14 * prog) + 0.38 * halo, 0.0, 1.0) * vessel_atten
    mix = np.clip(style["sat_drop"] * lesion_mask * opacity_gain, 0.0, 0.80)
    A_new = A * (1.0 - mix) + A_target * mix
    B_new = B * (1.0 - mix) + B_target * mix

    if grade >= 4:
        hole = np.exp(-np.power(np.clip(r / 0.28, 0, None), 6.0)) * (0.4 + 0.6 * prog)
        L_new -= 22.0 * style["hole"] * hole
        A_new += 3.0 * hole
        B_new -= 3.0 * hole

    lab_new = cv2.merge([
        np.clip(L_new, 0, 255),
        np.clip(A_new, 0, 255),
        np.clip(B_new, 0, 255),
    ]).astype(np.uint8)
    roi_lab_bgr = cv2.cvtColor(lab_new, cv2.COLOR_LAB2BGR).astype(np.float32)

    base_norm = roi_lab_bgr / 255.0
    lesion_norm = base_bgr / 255.0
    highlight_norm = highlight_bgr / 255.0

    tint_alpha = np.expand_dims(np.clip((0.22 * core + 0.07 * halo) * opacity_gain, 0.0, 0.42), axis=-1)
    tinted = base_norm * (1.0 - tint_alpha) + lesion_norm * tint_alpha

    lesion_mix = np.expand_dims(np.clip((0.84 * core + 0.26 * halo) * opacity_gain, 0.0, 1.0), axis=-1)
    out = (roi0 / 255.0) * (1.0 - lesion_mix) + tinted * lesion_mix

    highlight_boost = np.expand_dims(np.clip(0.13 * core * (0.82 + 0.18 * prog) * opacity_gain, 0.0, 0.22), axis=-1)
    highlight_boost = np.clip(highlight_boost * (0.82 + 0.36 * (brightness_gain - 1.0)), 0.0, 0.32)
    out = out * (1.0 - highlight_boost) + highlight_norm * highlight_boost

    out8 = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    if brightness_gain != 1.0:
        out8 = np.clip(out8.astype(np.float32) * brightness_gain, 0, 255).astype(np.uint8)
    blur_sigma = max(0.0, style["blur"] * (0.85 + 0.35 * max(0.0, diffusion_blur_gain - 1.0)))
    if blur_sigma > 0:
        out8_blur = cv2.GaussianBlur(out8, (0, 0), sigmaX=blur_sigma, sigmaY=blur_sigma)
        blur_region = np.exp(-np.power(np.clip(r / (1.05 + 0.18 * halo_width), 0, None), 2.0))
        alpha8 = np.expand_dims(np.clip((core + 0.26 * halo) * blur_region, 0, 1), -1)
        out8 = np.clip(out8_blur.astype(np.float32) * alpha8 + roi0 * (1.0 - alpha8), 0, 255).astype(np.uint8)

    img[y_min:y_max, x_min:x_max] = out8
    return img, grade


# =========================================================
# UI
# =========================================================

class ClickableImageLabel(QLabel):
    clicked = pyqtSignal(int, int)
    calibration_done = pyqtSignal(float)
    zoomed = pyqtSignal(int)
    hovered = pyqtSignal(int, int)
    pan_requested = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.mode = "fire"
        self.panning = False
        self.start_pos = None
        self.end_pos = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.aiming_pos = None
        self.aiming_radius_px = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = True
            self.last_pan_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "fire":
                self.clicked.emit(int(event.position().x()), int(event.position().y()))
            elif self.mode == "calibrate":
                self.start_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.panning:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.last_pan_pos
            self.pan_requested.emit(delta.x(), delta.y())
            self.last_pan_pos = current_pos
        elif self.mode == "calibrate" and self.start_pos:
            self.end_pos = event.position().toPoint()
            self.update()
        elif self.mode == "fire":
            self.hovered.emit(int(event.position().x()), int(event.position().y()))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.mode == "calibrate":
            self.end_pos = event.position().toPoint()
            if self.start_pos and self.end_pos:
                dist = math.hypot(self.end_pos.x() - self.start_pos.x(), self.end_pos.y() - self.start_pos.y())
                if dist > 10:
                    self.calibration_done.emit(dist)
            self.mode = "fire"
            self.start_pos = self.end_pos = None
            self.update()

    def wheelEvent(self, event):
        self.zoomed.emit(event.angleDelta().y())

    def leaveEvent(self, event):
        self.aiming_pos = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if self.mode == "calibrate" and self.start_pos and self.end_pos:
            painter.setPen(QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine))
            painter.drawLine(self.start_pos, self.end_pos)
        elif self.mode == "fire" and self.aiming_pos and self.aiming_radius_px > 0:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(Qt.GlobalColor.green, 1))
            cx, cy = int(self.aiming_pos[0]), int(self.aiming_pos[1])
            r = int(self.aiming_radius_px)
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            painter.drawLine(cx - 5, cy, cx + 5, cy)
            painter.drawLine(cx, cy - 5, cx, cy + 5)


class LaserSimulatorApp(QMainWindow):
    def __init__(self, image_path, task_json_path):
        super().__init__()
        self.image_path = image_path
        self.task_json_path = task_json_path
        self._load_task_config()

        self.setWindowTitle(f"渲染测试脚本 | 任务: {self.task_id}")
        self.setFixedSize(1450, 900)

        self.original_image = None
        self.current_image = None
        self.scale_factor = 1.0
        self.pixel_to_um = 2.0
        self.action_stream = []

        self.init_ui()
        self.load_image(image_path)

    def _load_task_config(self):
        try:
            with open(self.task_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.task_id = data.get("task_id", "TEST")
            self.physics_model = LaserPhysicalModel(data.get("gt_parameters", {}))
        except Exception:
            self.task_id = "Default_Task"
            self.physics_model = LaserPhysicalModel({})

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)

        panel = QWidget()
        panel.setFixedWidth(330)
        panel_layout = QVBoxLayout(panel)

        params_group = QGroupBox("渲染测试参数")
        form = QFormLayout()

        self.slider_power = QSlider(Qt.Orientation.Horizontal)
        self.slider_power.setRange(50, 600)
        self.slider_power.setValue(200)
        self.lbl_power = QLabel("200 mW")
        self.slider_power.valueChanged.connect(lambda v: self.lbl_power.setText(f"{v} mW"))

        self.slider_spot = QSlider(Qt.Orientation.Horizontal)
        self.slider_spot.setRange(50, 500)
        self.slider_spot.setValue(200)
        self.lbl_spot = QLabel("200 μm")
        self.slider_spot.valueChanged.connect(self._on_spot_ui_changed)

        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(10, 500)
        self.slider_duration.setValue(100)
        self.lbl_duration = QLabel("100 ms")
        self.slider_duration.valueChanged.connect(lambda v: self.lbl_duration.setText(f"{v} ms"))

        self.combo_wave = QComboBox()
        self.combo_wave.addItems(["532 (Green)", "577 (Yellow)", "672 (Red)"])

        self.combo_camera = QComboBox()
        self.combo_camera.addItems(["ZEISS CLARUS", "OPTOS 200"])

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(30, 180)
        self.slider_opacity.setValue(95)
        self.lbl_opacity = QLabel("0.95 ×")
        self.slider_opacity.valueChanged.connect(lambda v: self.lbl_opacity.setText(f"{v / 100.0:.2f} ×"))

        self.slider_brightness = QSlider(Qt.Orientation.Horizontal)
        self.slider_brightness.setRange(80, 220)
        self.slider_brightness.setValue(125)
        self.lbl_brightness = QLabel("1.25 ×")
        self.slider_brightness.valueChanged.connect(lambda v: self.lbl_brightness.setText(f"{v / 100.0:.2f} ×"))

        self.slider_irregular = QSlider(Qt.Orientation.Horizontal)
        self.slider_irregular.setRange(20, 200)
        self.slider_irregular.setValue(90)
        self.lbl_irregular = QLabel("0.90 ×")
        self.slider_irregular.valueChanged.connect(lambda v: self.lbl_irregular.setText(f"{v / 100.0:.2f} ×"))

        self.slider_diffusion_blur = QSlider(Qt.Orientation.Horizontal)
        self.slider_diffusion_blur.setRange(50, 220)
        self.slider_diffusion_blur.setValue(100)
        self.lbl_diffusion_blur = QLabel("1.00 ×")
        self.slider_diffusion_blur.valueChanged.connect(lambda v: self.lbl_diffusion_blur.setText(f"{v / 100.0:.2f} ×"))

        form.addRow("功率 (mW):", self.slider_power)
        form.addRow("", self.lbl_power)
        form.addRow("光斑 (μm):", self.slider_spot)
        form.addRow("", self.lbl_spot)
        form.addRow("时间 (ms):", self.slider_duration)
        form.addRow("", self.lbl_duration)
        form.addRow("发射波长:", self.combo_wave)
        form.addRow("相机基准色:", self.combo_camera)
        form.addRow("固定大小缩放:", QLabel(f"{FIXED_SIZE_GAIN:.2f} ×"))
        form.addRow("透明度:", self.slider_opacity)
        form.addRow("", self.lbl_opacity)
        form.addRow("亮度增强:", self.slider_brightness)
        form.addRow("", self.lbl_brightness)
        form.addRow("边缘不规则:", self.slider_irregular)
        form.addRow("", self.lbl_irregular)
        form.addRow("热扩散虚化:", self.slider_diffusion_blur)
        form.addRow("", self.lbl_diffusion_blur)
        params_group.setLayout(form)

        ctrl_group = QGroupBox("控制与统计")
        ctrl_layout = QVBoxLayout()
        self.lbl_info = QLabel("已绘制: 0 点")
        self.chk_trial = QCheckBox("标记为试打点")
        btn_calib = QPushButton("视盘标定 (参考1500μm)")
        btn_calib.clicked.connect(self.enable_calib)
        btn_reset = QPushButton("重置图像")
        btn_reset.clicked.connect(self.reset_image)
        btn_export = QPushButton("导出 JSON 结果")
        btn_export.clicked.connect(self.export_all)

        ctrl_layout.addWidget(self.lbl_info)
        ctrl_layout.addWidget(self.chk_trial)
        ctrl_layout.addWidget(btn_calib)
        ctrl_layout.addWidget(btn_reset)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(btn_export)
        ctrl_group.setLayout(ctrl_layout)

        panel_layout.addWidget(params_group)
        panel_layout.addWidget(ctrl_group)

        self.scroll = QScrollArea()
        self.scroll.setStyleSheet("background: #121212")
        self.canvas = ClickableImageLabel()
        self.canvas.clicked.connect(self.on_shoot)
        self.canvas.calibration_done.connect(self.on_calibrated)
        self.canvas.zoomed.connect(self.on_zoom)
        self.canvas.hovered.connect(self.on_hover)
        self.canvas.pan_requested.connect(self.on_pan)
        self.scroll.setWidget(self.canvas)

        layout.addWidget(panel)
        layout.addWidget(self.scroll, stretch=1)

    def _on_spot_ui_changed(self, v):
        self.lbl_spot.setText(f"{v} μm")
        self.update_aiming()

    def load_image(self, path):
        img = cv2.imread(path)
        if img is not None:
            self.original_image = img
            self.current_image = img.copy()
            self.update_display()
        else:
            QMessageBox.critical(self, "错误", f"无法加载图像: {path}")

    def reset_image(self):
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
            self.action_stream = []
            self.lbl_info.setText("已绘制: 0 点")
            self.update_display()

    def enable_calib(self):
        self.canvas.mode = "calibrate"
        QMessageBox.information(self, "标定模式", "请按住左键拖动，在视盘上画出垂直直径。")

    def on_calibrated(self, px):
        px_original = px / self.scale_factor
        self.pixel_to_um = 1500.0 / px_original
        self.update_aiming()
        QMessageBox.information(self, "标定完成", f"物理映射更新: 1像素 = {self.pixel_to_um:.2f} μm")

    def on_zoom(self, delta):
        self.scale_factor *= (1.1 if delta > 0 else 0.9)
        self.scale_factor = max(0.2, min(self.scale_factor, 15.0))
        self.update_display()
        self.update_aiming()

    def on_pan(self, dx, dy):
        self.scroll.horizontalScrollBar().setValue(self.scroll.horizontalScrollBar().value() - dx)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value() - dy)

    def on_hover(self, x, y):
        self.last_mouse = (x, y)
        self.update_aiming()

    def update_aiming(self):
        if not hasattr(self, 'last_mouse'):
            return
        r_px = (self.slider_spot.value() * 1.08 / 2.0) * FIXED_SIZE_GAIN / max(self.pixel_to_um, 1e-6) * self.scale_factor
        self.canvas.aiming_pos = self.last_mouse
        self.canvas.aiming_radius_px = r_px
        self.canvas.update()

    def on_shoot(self, x, y):
        if self.current_image is None:
            return
        offset_x = max(0, (self.canvas.width() - self.canvas.pixmap().width()) // 2)
        offset_y = max(0, (self.canvas.height() - self.canvas.pixmap().height()) // 2)
        rx = int((x - offset_x) / self.scale_factor)
        ry = int((y - offset_y) / self.scale_factor)
        if rx < 0 or rx >= self.current_image.shape[1] or ry < 0 or ry >= self.current_image.shape[0]:
            return

        p = float(self.slider_power.value())
        t = float(self.slider_duration.value())
        s = float(self.slider_spot.value())
        w = [532.0, 577.0, 672.0][self.combo_wave.currentIndex()]
        camera_type = self.combo_camera.currentText()
        opacity_gain = self.slider_opacity.value() / 100.0
        brightness_gain = self.slider_brightness.value() / 100.0
        irregular_gain = self.slider_irregular.value() / 100.0
        diffusion_blur_gain = self.slider_diffusion_blur.value() / 100.0

        self.current_image, grade = render_laser_spot_test(
            self.current_image,
            rx,
            ry,
            p,
            t,
            s,
            w,
            self.pixel_to_um,
            self.physics_model,
            camera_type=camera_type,
            opacity_gain=opacity_gain,
            brightness_gain=brightness_gain,
            irregular_gain=irregular_gain,
            diffusion_blur_gain=diffusion_blur_gain,
        )

        self.action_stream.append({
            "pos": [rx, ry],
            "grade": grade,
            "params": {
                "power": p,
                "duration": t,
                "spot_size": s,
                "wavelength": w,
                "camera_type": camera_type,
                "fixed_size_gain": FIXED_SIZE_GAIN,
                "opacity_gain": opacity_gain,
                "brightness_gain": brightness_gain,
                "irregular_gain": irregular_gain,
                "diffusion_blur_gain": diffusion_blur_gain,
            },
            "is_trial": self.chk_trial.isChecked(),
        })

        z_val, _ = self.physics_model.compute_z_and_grade(p, s, t, w)
        alert_text = " (⚠️ 危险：发生组织碳化！)" if grade == 4 and self.physics_model.get_normalized_intensity(z_val) > 1.5 else ""
        self.lbl_info.setText(f"已绘制: {len(self.action_stream)} 点 | 最新等级: {grade}{alert_text}")
        self.update_display()

    def update_display(self):
        if self.current_image is None:
            return
        rgb = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, w * c, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        if self.scale_factor != 1.0:
            pix = pix.scaled(
                int(w * self.scale_factor),
                int(h * self.scale_factor),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.canvas.setPixmap(pix)
        self.canvas.setFixedSize(pix.size())

    def export_all(self):
        if not self.action_stream:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", f"{self.task_id}_result.json", "JSON (*.json)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"task_id": self.task_id, "shots": self.action_stream}, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "击发数据已导出。")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    TEST_IMG_PATH = os.path.join(os.path.dirname(__file__), "123.jpg")
    TEST_JSON_PATH = "task.json"

    if not os.path.exists(TEST_IMG_PATH):
        print(f"警告: 未找到 {TEST_IMG_PATH}，将生成测试黑色画布。")
        test_bg = np.zeros((800, 1000, 3), dtype=np.uint8)
        cv2.imwrite("test_retina.jpg", test_bg)
        TEST_IMG_PATH = "test_retina.jpg"

    if not os.path.exists(TEST_JSON_PATH):
        with open(TEST_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"task_id": "TEST_001"}, f, ensure_ascii=False)

    win = LaserSimulatorApp(TEST_IMG_PATH, TEST_JSON_PATH)
    win.show()
    sys.exit(app.exec())
