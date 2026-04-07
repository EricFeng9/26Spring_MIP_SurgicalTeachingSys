import sys
import os
import cv2
import numpy as np
import json
import math
from datetime import datetime

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QLabel, QSlider, QComboBox,
                             QPushButton, QGroupBox, QFormLayout, QMessageBox,
                             QScrollArea, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen

# =========================================================
# 理论物理模型与校准引擎
# =========================================================

class LaserPhysicalModel:
    """
    使用更接近初版体验的通用强度模型：

    z0 = beta1 * log(PT / A + eps) + beta2 * log(P / A + eps) + log(eta(lambda)) + c

    然后通过单病例偏置 beta_0 把 GT 参数对齐到 III 级中心。
    这样既保留我们讨论过的结构，又尽量维持初版的手感与分级节奏。
    """
    def __init__(self, gt_params):
        self.gt_P = float(gt_params.get("power", 200.0))
        self.gt_S = float(gt_params.get("spot_size", 200.0))
        self.gt_T = float(gt_params.get("exposure_time", 100.0))
        self.gt_lam = float(gt_params.get("wavelength", 532.0))

        # 经验参数：故意设置得更接近初版表现
        # beta_1 主导累计作用强度；beta_2 只做较轻的瞬时修正，避免把初版外观拉得太怪
        self.beta_1 = 1.15
        self.beta_2 = 0.12
        self.eps = 1e-4
        self.c = 0.0

        # 保持与初版一致的 4 档划分位置与目标级中心
        self.tau_0 = 1.0
        self.tau_1 = 2.0
        self.tau_2 = 3.0
        self.z_target = (self.tau_1 + self.tau_2) / 2.0  # 2.5，对应 III 级中间

        raw_z_gt = self._compute_raw_z(self.gt_P, self.gt_S, self.gt_T, self.gt_lam)
        self.beta_0 = self.z_target - raw_z_gt

    @staticmethod
    def _compute_area_um2(spot_size_um: float) -> float:
        radius_um = max(spot_size_um, 1e-6) / 2.0
        return math.pi * radius_um * radius_um

    def _get_lambda_eta(self, wavelength: float) -> float:
        # 532 作为基准；577 黄光略强；672 红光略弱
        eta_map = {
            532.0: 1.00,
            577.0: 1.15,
            672.0: 0.82,
        }
        closest_key = min(eta_map.keys(), key=lambda k: abs(k - wavelength))
        return eta_map[closest_key]

    def _compute_raw_z(self, P, S, T, lam):
        if S <= 0 or P <= 0 or T <= 0:
            return -999.0

        A = self._compute_area_um2(S)
        fluence = (P * T) / A      # 累计作用项
        irradiance = P / A         # 瞬时修正项
        eta = self._get_lambda_eta(lam)

        return (
            self.beta_1 * math.log(fluence + self.eps)
            + self.beta_2 * math.log(irradiance + self.eps)
            + math.log(eta)
            + self.c
        )

    def compute_z_and_grade(self, P, S, T, lam):
        z = self.beta_0 + self._compute_raw_z(P, S, T, lam)
        if z < self.tau_0:
            return z, 1
        elif z < self.tau_1:
            return z, 2
        elif z < self.tau_2:
            return z, 3
        else:
            return z, 4

    def get_grade_progress(self, z, grade):
        # 等级内部位置，用于很轻微地调节透明度与中心增强
        if grade == 1:
            low, high = self.tau_0 - 0.8, self.tau_0
        elif grade == 2:
            low, high = self.tau_0, self.tau_1
        elif grade == 3:
            low, high = self.tau_1, self.tau_2
        else:
            low, high = self.tau_2, self.tau_2 + 0.8
        if high - low <= 1e-6:
            return 0.5
        t = (z - low) / (high - low)
        return max(0.0, min(1.0, t))


# =========================================================
# 渲染核心
# =========================================================

def render_laser_spot_v2(img, center_x, center_y, power_mw, duration_ms, spot_size_um,
                         wavelength_nm, pixel_to_um, model: LaserPhysicalModel):
    """
    保持初版观感为主，只做轻微升级：
    - 强度与分级改为新的 z 模型
    - 渲染仍采用“基础高斯 + 中心增强 + 外圈晕圈”的初版风格
    - 仅增加少量级内差异与对黄光的暖色支持
    """
    if pixel_to_um <= 0:
        return img, 0

    radius_um = spot_size_um / 2.0
    radius_px = max(1.0, radius_um / pixel_to_um)

    z_val, grade = model.compute_z_and_grade(power_mw, spot_size_um, duration_ms, wavelength_nm)
    grade_u = model.get_grade_progress(z_val, grade)

    # 低于可见阈值时不渲染
    if z_val < 0.20:
        return img, 0

    # 尽量维持初版大小，只加入很轻微的参数修正
    duration_scale = 1.0 + 0.04 * np.clip((duration_ms - 100.0) / 100.0, -0.5, 1.5)
    grade_scale = {1: 0.96, 2: 1.00, 3: 1.04, 4: 1.10}[grade]
    effective_radius_px = radius_px * duration_scale * grade_scale

    grid_half = int(max(6, effective_radius_px * 4.0))
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half)
    if x_min >= x_max or y_min >= y_max:
        return img, 0

    y_coords, x_coords = np.ogrid[y_min - center_y:y_max - center_y, x_min - center_x:x_max - center_x]
    dist_sq = x_coords.astype(np.float32) ** 2 + y_coords.astype(np.float32) ** 2

    sigma_sq = max((effective_radius_px / 2.0) ** 2, 1.0)
    gaussian_base = np.exp(-dist_sq / (2.0 * sigma_sq))

    # 初版风格颜色基础：灰白为主
    if abs(wavelength_nm - 577.0) < 5.0:
        # 黄光：略偏暖、略偏黄白（BGR）
        base_color = np.array([198, 214, 224], dtype=np.float32)
        bright_color = np.array([222, 235, 242], dtype=np.float32)
        halo_color = np.array([188, 202, 212], dtype=np.float32)
    elif abs(wavelength_nm - 672.0) < 5.0:
        # 红光：略偏冷、偏灰一些
        base_color = np.array([205, 205, 208], dtype=np.float32)
        bright_color = np.array([230, 230, 232], dtype=np.float32)
        halo_color = np.array([192, 192, 196], dtype=np.float32)
    else:
        # 绿光 / 默认
        base_color = np.array([210, 210, 210], dtype=np.float32)
        bright_color = np.array([232, 232, 232], dtype=np.float32)
        halo_color = np.array([198, 198, 198], dtype=np.float32)

    alpha_map = np.zeros_like(gaussian_base, dtype=np.float32)
    color_map = np.zeros((y_max - y_min, x_max - x_min, 3), dtype=np.float32)
    color_map[:] = base_color

    # 维持初版四档表现，只加入轻微级内连续变化
    if grade == 1:
        alpha_map = gaussian_base * (0.24 + 0.10 * grade_u)
        color_map[:] = base_color * (0.96 + 0.02 * grade_u)

    elif grade == 2:
        alpha_map = gaussian_base * (0.52 + 0.12 * grade_u)
        if abs(wavelength_nm - 577.0) < 5.0:
            color_map[:] = np.array([205, 218, 228], dtype=np.float32)
        else:
            color_map[:] = np.array([214, 214, 214], dtype=np.float32)

    elif grade == 3:
        alpha_map = gaussian_base * (0.72 + 0.10 * grade_u)
        color_map[:] = bright_color

        center_sigma_sq = max((effective_radius_px * 0.42) ** 2, 1.0)
        center_boost = np.exp(-dist_sq / (2.0 * center_sigma_sq)) * (0.12 + 0.08 * grade_u)
        alpha_map = np.clip(alpha_map + center_boost, 0.0, 0.95)

        if abs(wavelength_nm - 577.0) < 5.0:
            center_mask = np.expand_dims(np.clip(center_boost * 2.2, 0.0, 1.0), axis=-1)
            warm_center = np.array([228, 238, 245], dtype=np.float32)
            color_map = color_map * (1.0 - center_mask) + warm_center * center_mask

    else:  # grade == 4
        halo_sigma_sq = max((effective_radius_px * 0.95) ** 2, 1.0)
        halo = np.exp(-dist_sq / (2.0 * halo_sigma_sq)) * (0.32 + 0.10 * grade_u)
        alpha_map = np.clip(gaussian_base * (1.05 + 0.20 * grade_u) + halo, 0.0, 1.0)

        center_sigma_sq = max((effective_radius_px * 0.38) ** 2, 1.0)
        center_mask_2d = np.clip(np.exp(-dist_sq / (2.0 * center_sigma_sq)) * (1.15 + 0.25 * grade_u), 0.0, 1.0)
        center_mask = np.expand_dims(center_mask_2d, axis=-1)

        color_map[:] = halo_color
        if abs(wavelength_nm - 577.0) < 5.0:
            strong_center = np.array([246, 248, 250], dtype=np.float32)
        else:
            strong_center = np.array([255, 255, 255], dtype=np.float32)
        color_map = color_map * (1.0 - center_mask) + strong_center * center_mask

    alpha_3d = np.expand_dims(np.clip(alpha_map, 0.0, 1.0), axis=-1)
    roi = img[y_min:y_max, x_min:x_max].astype(np.float32)
    blended_roi = roi * (1.0 - alpha_3d) + color_map * alpha_3d
    img[y_min:y_max, x_min:x_max] = np.clip(blended_roi, 0, 255).astype(np.uint8)
    return img, grade


# =========================================================
# 交互式图像控件
# =========================================================

class ClickableImageLabel(QLabel):
    clicked = pyqtSignal(int, int)
    calibration_done = pyqtSignal(float)
    zoomed = pyqtSignal(int)
    focused = pyqtSignal(int)
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
                self.clicked.emit(event.pos().x(), event.pos().y())
            elif self.mode == "calibrate":
                self.start_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self.panning:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.last_pan_pos
            self.pan_requested.emit(delta.x(), delta.y())
            self.last_pan_pos = current_pos
        elif self.mode == "calibrate" and self.start_pos:
            self.end_pos = event.pos()
            self.update()
        elif self.mode == "fire":
            self.hovered.emit(event.pos().x(), event.pos().y())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif event.button() == Qt.MouseButton.LeftButton and self.mode == "calibrate":
            self.end_pos = event.pos()
            if self.start_pos and self.end_pos:
                dx = self.end_pos.x() - self.start_pos.x()
                dy = self.end_pos.y() - self.start_pos.y()
                if math.hypot(dx, dy) > 10:
                    self.calibration_done.emit(math.hypot(dx, dy))
            self.mode = "fire"
            self.start_pos = None
            self.end_pos = None
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta != 0:
            if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
                self.zoomed.emit(delta)
            else:
                self.focused.emit(delta)

    def leaveEvent(self, event):
        self.aiming_pos = None
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        if self.mode == "calibrate" and self.start_pos and self.end_pos:
            pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(self.start_pos, self.end_pos)
            painter.setBrush(Qt.GlobalColor.red)
            painter.drawEllipse(self.start_pos, 4, 4)
            painter.drawEllipse(self.end_pos, 4, 4)
        elif self.mode == "fire" and self.aiming_pos and self.aiming_radius_px > 0:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(Qt.GlobalColor.green, 1, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            cx, cy = int(self.aiming_pos[0]), int(self.aiming_pos[1])
            r = int(self.aiming_radius_px)
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            painter.drawLine(cx - 5, cy, cx + 5, cy)
            painter.drawLine(cx, cy - 5, cx, cy + 5)


# =========================================================
# 主程序窗口
# =========================================================

class LaserSimulatorApp(QMainWindow):
    def __init__(self, image_path, task_json_path):
        super().__init__()
        self.image_path = image_path
        self.task_json_path = task_json_path
        self._load_task_config()

        self.setWindowTitle(f"视网膜光凝模拟系统 | 任务ID: {self.task_id}")
        self.setFixedSize(1400, 900)

        self.original_image = None
        self.current_image = None
        self.scale_factor = 1.0
        self.pixel_to_um = 2.0
        self.z_offset = 0.0
        self.current_blur_level = -1
        self.action_stream = []

        self.init_ui()
        self.load_image(image_path)

    def _load_task_config(self):
        try:
            with open(self.task_json_path, 'r', encoding='utf-8') as f:
                self.task_data = json.load(f)
            self.task_id = self.task_data.get("task_id", "Unknown_Task")
            self.physics_model = LaserPhysicalModel(self.task_data.get("gt_parameters", {}))
        except Exception as e:
            QMessageBox.critical(None, "配置加载失败", f"无法读取或解析题目JSON文件:\n{e}")
            sys.exit()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        control_panel = QWidget()
        control_panel.setFixedWidth(350)
        control_layout = QVBoxLayout(control_panel)

        info_group = QGroupBox("当前任务信息")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel(f"<b>任务 ID:</b> {self.task_id}"))
        self.lbl_spot_count = QLabel("<b>已击发:</b> 0 点")
        info_layout.addWidget(self.lbl_spot_count)
        self.chk_trial = QCheckBox("当前为试打模式")
        info_layout.addWidget(self.chk_trial)
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)

        params_group = QGroupBox("激光参数设定")
        form_layout = QFormLayout()

        self.slider_power = QSlider(Qt.Orientation.Horizontal)
        self.slider_power.setRange(50, 400)
        self.slider_power.setValue(200)
        self.lbl_power = QLabel("200 mW")
        self.slider_power.valueChanged.connect(lambda v: self.lbl_power.setText(f"{v} mW"))
        form_layout.addRow("功率 (P):", self.slider_power)
        form_layout.addRow("", self.lbl_power)

        self.slider_spot = QSlider(Qt.Orientation.Horizontal)
        self.slider_spot.setRange(50, 400)
        self.slider_spot.setValue(200)
        self.lbl_spot = QLabel("200 μm")
        self.slider_spot.valueChanged.connect(self._on_spot_size_changed)
        form_layout.addRow("设定光斑 (S):", self.slider_spot)
        form_layout.addRow("", self.lbl_spot)

        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(10, 500)
        self.slider_duration.setValue(100)
        self.lbl_duration = QLabel("100 ms")
        self.slider_duration.valueChanged.connect(lambda v: self.lbl_duration.setText(f"{v} ms"))
        form_layout.addRow("曝光时间 (T):", self.slider_duration)
        form_layout.addRow("", self.lbl_duration)

        self.combo_wave = QComboBox()
        self.combo_wave.addItems(["532 (Green)", "577 (Yellow)", "672 (Red)"])
        form_layout.addRow("波长 (λ):", self.combo_wave)

        self.lbl_focus = QLabel("<b>系统焦段 (Z): 0.0</b><br><b style='color:red'>大幅平移后画面将严重失焦，请滚轮调焦。</b>")
        form_layout.addRow("", self.lbl_focus)

        params_group.setLayout(form_layout)
        control_layout.addWidget(params_group)

        calib_group = QGroupBox("系统标定")
        calib_layout = QVBoxLayout()
        self.lbl_scale = QLabel(f"当前比例: 1 px = {self.pixel_to_um:.2f} μm")
        self.btn_calibrate = QPushButton("视盘尺寸标定")
        self.btn_calibrate.clicked.connect(self.enable_calibration_mode)
        calib_layout.addWidget(self.lbl_scale)
        calib_layout.addWidget(self.btn_calibrate)
        calib_group.setLayout(calib_layout)
        control_layout.addWidget(calib_group)

        self.btn_clear = QPushButton("重置图像")
        self.btn_clear.clicked.connect(self.reset_image)
        control_layout.addWidget(self.btn_clear)
        control_layout.addStretch()

        self.btn_export = QPushButton("导出 JSON 结果并结束")
        self.btn_export.clicked.connect(self.export_json_and_exit)
        control_layout.addWidget(self.btn_export)

        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #2c2c2c;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = ClickableImageLabel()
        self.image_label.setStyleSheet("background-color: black;")

        self.image_label.clicked.connect(self.on_canvas_click)
        self.image_label.calibration_done.connect(self.process_calibration)
        self.image_label.zoomed.connect(self.handle_zoom)
        self.image_label.focused.connect(self.handle_focus)
        self.image_label.hovered.connect(self.handle_hover)
        self.image_label.pan_requested.connect(self.handle_pan)

        self.scroll_area.setWidget(self.image_label)

        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.check_focus_state)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.check_focus_state)

        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.scroll_area, stretch=1)

    def _on_spot_size_changed(self, value):
        self.lbl_spot.setText(f"{value} μm")
        self.update_aiming_ring()

    def load_image(self, image_path):
        img = cv2.imread(image_path)
        if img is not None:
            self.original_image = img
            self.current_image = self.original_image.copy()
            self.scale_factor = 1.0
            self.z_offset = 0.0
            self.check_focus_state(force_update=True)
        else:
            QMessageBox.critical(self, "错误", f"无法读取图像文件: {image_path}")
            sys.exit()

    def reset_image(self):
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
            self.action_stream = []
            self.lbl_spot_count.setText("<b>已击发:</b> 0 点")
            self.z_offset = 0.0
            self.lbl_focus.setText("<b>系统焦段 (Z): 0.0</b><br><b style='color:red'>大幅平移后画面将严重失焦，请滚轮调焦。</b>")
            self.check_focus_state(force_update=True)

    def enable_calibration_mode(self):
        self.image_label.mode = "calibrate"
        QMessageBox.information(self, "标定模式", "请在图像中拖动鼠标绘制视盘垂直直径。")

    def process_calibration(self, pixel_distance):
        self.pixel_to_um = 1500.0 / (pixel_distance / self.scale_factor)
        self.lbl_scale.setText(f"已标定: 1 px = {self.pixel_to_um:.2f} μm")

    def handle_pan(self, dx, dy):
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() - dx)
        v_bar.setValue(v_bar.value() - dy)

    def handle_zoom(self, delta):
        if delta > 0:
            self.scale_factor *= 1.15
        else:
            self.scale_factor /= 1.15
        self.scale_factor = max(0.2, min(self.scale_factor, 5.0))
        self.check_focus_state(force_update=True)

    def handle_focus(self, delta):
        step = 10.0 if delta > 0 else -10.0
        self.z_offset += step
        self.z_offset = max(-1500.0, min(self.z_offset, 1500.0))
        self.lbl_focus.setText(f"<b>系统焦段 (Z): {self.z_offset:.1f}</b><br><b style='color:red'>大幅平移后画面将严重失焦，请滚轮调焦。</b>")
        self.check_focus_state()

    def handle_hover(self, lbl_x, lbl_y):
        self.last_hover_x = lbl_x
        self.last_hover_y = lbl_y
        self.update_aiming_ring()

    def update_aiming_ring(self):
        if not hasattr(self, 'last_hover_x'):
            return
        base_spot = float(self.slider_spot.value())
        radius_px = (base_spot / 2.0) / self.pixel_to_um * self.scale_factor
        self.image_label.aiming_pos = (self.last_hover_x, self.last_hover_y)
        self.image_label.aiming_radius_px = radius_px
        self.image_label.update()

    def get_optimal_z(self):
        if self.original_image is None:
            return 0.0
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        viewport = self.scroll_area.viewport()
        disp_x = h_bar.value() + viewport.width() / 2.0
        disp_y = v_bar.value() + viewport.height() / 2.0
        img_x, img_y = disp_x / self.scale_factor, disp_y / self.scale_factor
        h, w = self.original_image.shape[:2]
        r = math.hypot(img_x - w / 2.0, img_y - h / 2.0)
        return r * 0.45

    def check_focus_state(self, force_update=False):
        optimal_z = self.get_optimal_z()
        focus_diff = abs(self.z_offset - optimal_z)
        new_blur = int(focus_diff / 5.0)
        new_blur = min(new_blur, 30)

        if force_update or new_blur != self.current_blur_level:
            self.current_blur_level = new_blur
            self.update_display_blur()

    def on_canvas_click(self, click_x, click_y):
        if self.current_image is None or self.image_label.mode == "calibrate":
            return
        displayed_pixmap = self.image_label.pixmap()
        if not displayed_pixmap:
            return

        disp_w, disp_h = displayed_pixmap.width(), displayed_pixmap.height()
        lbl_w, lbl_h = self.image_label.width(), self.image_label.height()
        offset_x = max(0, (lbl_w - disp_w) // 2)
        offset_y = max(0, (lbl_h - disp_h) // 2)

        rel_x, rel_y = click_x - offset_x, click_y - offset_y
        if rel_x < 0 or rel_x >= disp_w or rel_y < 0 or rel_y >= disp_h:
            return

        real_x, real_y = int(rel_x / self.scale_factor), int(rel_y / self.scale_factor)

        power = float(self.slider_power.value())
        duration = float(self.slider_duration.value())
        spot_set = float(self.slider_spot.value())
        wave_text = self.combo_wave.currentText()
        if "577" in wave_text:
            wave = 577.0
        elif "672" in wave_text:
            wave = 672.0
        else:
            wave = 532.0

        self.current_image, spot_grade = render_laser_spot_v2(
            self.current_image, real_x, real_y, power, duration, spot_set, wave,
            self.pixel_to_um, self.physics_model
        )
        self.check_focus_state(force_update=True)

        shot_record = {
            "id": len(self.action_stream) + 1,
            "pos": [float(real_x), float(real_y)],
            "is_trial": self.chk_trial.isChecked(),
            "spot_grade": spot_grade,
            "params": {
                "power": power,
                "spot_size_set": spot_set,
                "z_offset": self.z_offset,
                "exposure_time": duration,
                "wavelength": wave
            }
        }
        self.action_stream.append(shot_record)
        self.lbl_spot_count.setText(f"<b>已击发:</b> {len(self.action_stream)} 点")

    def update_display_blur(self):
        if self.current_image is None:
            return

        if self.current_blur_level > 0:
            ksize = self.current_blur_level * 2 + 1
            render_img = cv2.GaussianBlur(self.current_image, (ksize, ksize), 0)
        else:
            render_img = self.current_image

        rgb_image = cv2.cvtColor(render_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        qt_img = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)

        if self.scale_factor != 1.0:
            pixmap = pixmap.scaled(int(w * self.scale_factor), int(h * self.scale_factor),
                                   Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(pixmap.size())

    def export_json_and_exit(self):
        if not self.action_stream:
            QMessageBox.warning(self, "提示", "未记录任何击发数据。")
            self.close()
            return
        session_id = f"SESS_{datetime.now().strftime('%Y%m%d_%H%M%S')}_001"
        output_data = {
            "session_id": session_id,
            "task_id": self.task_id,
            "player_info": {"id": "ST_001", "name": "Operator"},
            "shots": self.action_stream
        }
        with open(f"{session_id}_result.json", 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "成功", f"数据已导出: {session_id}_result.json")
        self.close()


# =========================================================
# 入口点
# =========================================================

def main():
    app = QApplication(sys.argv)
    IMAGE_PATH = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\test.png"
    JSON_PATH = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\题目样本.json"

    if not os.path.exists(IMAGE_PATH) or not os.path.exists(JSON_PATH):
        print("Error: Required files not found.")
        sys.exit(1)

    window = LaserSimulatorApp(IMAGE_PATH, JSON_PATH)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
