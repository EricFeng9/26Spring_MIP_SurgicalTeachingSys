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
                             QScrollArea, QCheckBox, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen

# =========================================================
# 理论物理模型与校准引擎 (百分位赋分制 - 解耦版)
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

        # 替换为图片公式中给定的固定阈值
        self.tau_0 = 2.989  # 等级1与等级2的分界
        self.tau_1 = 4.820  # 等级2与等级3的分界
        self.tau_2 = 7.026  # 等级3与等级4的分界

        # 初始化渲染所需的全局最大最小值（仅用于计算视觉表现的energy_n）
        self._initialize_z_bounds()

    def _compute_raw_z(self, P, S, T, lam):
        if S <= 0 or P <= 0 or T <= 0: return -999.0
        
        # 1. 确定波长系数 k_color 
        # (依据原脚本逻辑：532为基准，577作用更强，672作用较弱)
        if lam == 532.0: 
            k_color = 1.0     # 绿光
        elif lam == 577.0: 
            k_color = 1.2     # 黄光
        elif lam == 672.0: 
            k_color = 0.8     # 红光
        else: 
            k_color = 1.0

        # 2. 核心代入图片中的真实拟合公式
        # z = ln(t/87.8) + 5.600 * k_color * (P/160.8) * (136.5/d)^0.548 * (1 - e^(-(t/1000)/0.0492))
        
        term_time_log = math.log(T / 87.8)
        term_power_spot = 5.600 * k_color * (P / 160.8) * ((136.5 / S) ** 0.548)
        term_time_exp = 1.0 - math.exp(-(T / 1000.0) / 0.0492)
        
        z = term_time_log + (term_power_spot * term_time_exp)
        
        return z

    def _initialize_z_bounds(self):
        # 遍历参数空间，仅计算最小值和90分位数，用于后续视觉渲染效果的归一化映射
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
        
        # 按照公式图片左下角的精确阈值条件划分等级
        if z < self.tau_0: 
            grade = 1
        elif self.tau_0 <= z < self.tau_1: 
            grade = 2
        elif self.tau_1 <= z < self.tau_2: 
            grade = 3
        else: 
            grade = 4
            
        return z, grade

    def get_normalized_intensity(self, z):
        # 将 z 值映射到渲染引擎所需的倍率
        if self.z_clinical_max <= self.z_min_global: return 0.5
        vis = (z - self.z_min_global) / (self.z_clinical_max - self.z_min_global)
        return float(np.clip(vis, 0.0, 2.5))
# =========================================================
# 渲染核心：光凝斑绘制引擎 (写实底纹融合版)
# =========================================================

def get_camera_render_gain(camera_type: str) -> float:
    camera_type = (camera_type or "UNKNOWN").upper()
    return {
        "CLARUS": 1.15,
        "OPTOS": 1.35,
        "UNKNOWN": 1.22,
    }.get(camera_type, 1.22)

def get_grade_render_gain(grade: int) -> float:
    return {
        1: 0.95,
        2: 1.08,
        3: 1.22,
        4: 1.35,
    }.get(int(grade), 1.08)

def render_laser_spot_v2(
    img, center_x, center_y, power_mw, duration_ms, spot_size_um, wavelength_nm,
    pixel_to_um, model: LaserPhysicalModel, camera_type="UNKNOWN", extra_render_gain=1.0
):
    # 此时算出的 energy_n 和 grade 已经与 spot_size_um 无关了
    z_val, grade = model.compute_z_and_grade(power_mw, spot_size_um, duration_ms, wavelength_nm)
    energy_n = model.get_normalized_intensity(z_val)

    # 波长特异性视觉配置
    if wavelength_nm == 577.0: # 黄光
        edge_sharpness = 4.0     
        edema_spread_base = 1.15 
        color_base = np.array([175, 232, 245], dtype=np.float32) 
    elif wavelength_nm == 672.0: # 红光
        edge_sharpness = 2.0     
        edema_spread_base = 1.50 
        color_base = np.array([195, 205, 228], dtype=np.float32) 
    else:                        # 绿光 (默认)
        edge_sharpness = 2.5     
        edema_spread_base = 1.25
        color_base = np.array([170, 236, 246], dtype=np.float32) 

    # 【这里保留光斑大小对渲染尺寸的物理影响】
    lens_factor = 1.08
    retinal_beam_um = spot_size_um * lens_factor
    beam_radius_um = retinal_beam_um / 2.0

    # 热扩散系数现在只会被时间和综合能量放大
    base_k = 0.5 + (80.0 / max(beam_radius_um, 10.0)) + (0.001 * duration_ms)
    k_diffusion = 1.0 + (base_k - 1.0) * float(np.clip(energy_n * 1.2, 0.0, 2.0))

    # 可见病灶尺寸增益：相机机型 + 光斑等级 + 手动微调
    camera_gain = get_camera_render_gain(camera_type)
    grade_gain = get_grade_render_gain(grade)
    visible_gain = camera_gain * grade_gain * max(0.2, float(extra_render_gain))

    final_lesion_um = retinal_beam_um * k_diffusion * visible_gain
    effective_radius = max(1.0, (final_lesion_um / 2.0) / max(pixel_to_um, 1e-6))

    grid_half = int(max(8, effective_radius * (3.0 + max(0, energy_n - 1.0)))) 
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half + 1)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half + 1)
    if x_min >= x_max or y_min >= y_max: return img, grade

    y_coords, x_coords = np.ogrid[y_min - center_y:y_max - center_y, x_min - center_x:x_max - center_x]
    dist = np.sqrt(x_coords.astype(np.float32)**2 + y_coords.astype(np.float32)**2)
    r = dist / max(1e-6, effective_radius)

    overdrive = max(0.0, energy_n - 1.0) 

    core_mask = np.exp(-((r / 0.85) ** edge_sharpness)) 
    
    current_edema_radius = edema_spread_base + (0.6 * overdrive)
    edema_mask = np.clip(np.exp(-((r / current_edema_radius) ** 2)) - core_mask, 0, 1)

    burn_hole_mask = 0
    if overdrive > 0.5:
        burn_hole_mask = np.exp(-((r / 0.3) ** 6)) * min(1.0, overdrive - 0.4)

    burn_intensity = min(1.0, 0.3 + 0.7 * energy_n) 
    
    roi = img[y_min:y_max, x_min:x_max].copy()
    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    H, S, V = cv2.split(roi_hsv)

    s_drop = core_mask * burn_intensity * 0.85 + edema_mask * 0.2
    S_new = S * (1.0 - np.clip(s_drop + burn_hole_mask * 1.5, 0, 1))
    
    v_boost = (core_mask * burn_intensity * (255.0 - V) * 0.52) + (edema_mask * burn_intensity * 12.0)
    V_new = V + v_boost
    
    if overdrive > 0.5:
        V_new -= burn_hole_mask * 150.0 

    roi_hsv_new = cv2.merge([H, np.clip(S_new, 0, 255), np.clip(V_new, 0, 255)]).astype(np.uint8)
    blended_roi = cv2.cvtColor(roi_hsv_new, cv2.COLOR_HSV2BGR).astype(np.float32)

    roi_norm = blended_roi / 255.0
    color_norm = color_base / 255.0
    
    opacity = np.expand_dims(np.clip(core_mask * burn_intensity * 0.72 + edema_mask * burn_intensity * 0.20, 0, 1), axis=-1) 
    screen_blend = 1.0 - (1.0 - roi_norm) * (1.0 - color_norm * opacity)
    
    img[y_min:y_max, x_min:x_max] = np.clip(screen_blend * 255.0, 0.0, 255.0).astype(np.uint8)
    
    return img, grade

# =========================================================
# 交互组件与UI构建
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
                if dist > 10: self.calibration_done.emit(dist)
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
            pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
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
        
        self.setWindowTitle(f"视网膜光凝仿真编辑器 (解耦控制版) | 任务: {self.task_id}")
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
        except Exception as e:
            QMessageBox.critical(None, "提示", f"配置加载异常，将使用默认参数。详细信息:\n{e}")
            self.task_id = "Default_Task"
            self.physics_model = LaserPhysicalModel({}) 

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QHBoxLayout(main_widget)
        
        panel = QWidget(); panel.setFixedWidth(320)
        panel_layout = QVBoxLayout(panel)
        
        params_group = QGroupBox("激光物理参数")
        form = QFormLayout()
        
        self.slider_power = QSlider(Qt.Orientation.Horizontal); self.slider_power.setRange(50, 600); self.slider_power.setValue(200)
        self.lbl_power = QLabel("200 mW"); self.slider_power.valueChanged.connect(lambda v: self.lbl_power.setText(f"{v} mW"))
        
        self.slider_spot = QSlider(Qt.Orientation.Horizontal); self.slider_spot.setRange(50, 500); self.slider_spot.setValue(200)
        self.lbl_spot = QLabel("200 μm"); self.slider_spot.valueChanged.connect(self._on_spot_ui_changed)
        
        self.slider_duration = QSlider(Qt.Orientation.Horizontal); self.slider_duration.setRange(10, 500); self.slider_duration.setValue(100)
        self.lbl_duration = QLabel("100 ms"); self.slider_duration.valueChanged.connect(lambda v: self.lbl_duration.setText(f"{v} ms"))
        
        self.combo_wave = QComboBox(); self.combo_wave.addItems(["532 (Green)", "577 (Yellow)", "672 (Red)"])

        self.combo_camera = QComboBox(); self.combo_camera.addItems(["CLARUS", "OPTOS", "UNKNOWN"])
        self.combo_camera.setCurrentText("CLARUS")
        self.combo_camera.currentIndexChanged.connect(lambda _: self.update_aiming())

        self.slider_render_gain = QSlider(Qt.Orientation.Horizontal); self.slider_render_gain.setRange(5, 20); self.slider_render_gain.setValue(8)
        self.lbl_render_gain = QLabel("0.8 ×")
        self.slider_render_gain.valueChanged.connect(self._on_render_gain_changed)

        form.addRow("功率 (mW):", self.slider_power); form.addRow("", self.lbl_power)
        form.addRow("光斑 (μm):", self.slider_spot); form.addRow("", self.lbl_spot)
        form.addRow("时间 (ms):", self.slider_duration); form.addRow("", self.lbl_duration)
        form.addRow("发射波长:", self.combo_wave)
        form.addRow("相机类型:", self.combo_camera)
        form.addRow("额外尺寸增益:", self.slider_render_gain); form.addRow("", self.lbl_render_gain)
        params_group.setLayout(form)
        
        ctrl_group = QGroupBox("控制与统计")
        ctrl_layout = QVBoxLayout()
        self.lbl_info = QLabel("已绘制: 0 点 | 默认尺寸已收缩，颜色偏黄白")
        self.chk_trial = QCheckBox("标记为试打点")
        btn_calib = QPushButton("视盘标定 (参考1500μm)"); btn_calib.clicked.connect(self.enable_calib)
        btn_reset = QPushButton("重置图像"); btn_reset.clicked.connect(self.reset_image)
        btn_export = QPushButton("导出 JSON 结果"); btn_export.clicked.connect(self.export_all)
        
        ctrl_layout.addWidget(self.lbl_info)
        ctrl_layout.addWidget(self.chk_trial)
        ctrl_layout.addWidget(btn_calib)
        ctrl_layout.addWidget(btn_reset)
        ctrl_layout.addStretch()
        ctrl_layout.addWidget(btn_export)
        ctrl_group.setLayout(ctrl_layout)
        
        panel_layout.addWidget(params_group)
        panel_layout.addWidget(ctrl_group)
        
        self.scroll = QScrollArea(); self.scroll.setStyleSheet("background: #121212")
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

    def _on_render_gain_changed(self, v):
        self.lbl_render_gain.setText(f"{v / 10.0:.1f} ×")
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
            self.lbl_info.setText("已绘制: 0 点 | 默认尺寸已收缩，颜色偏黄白")
            self.update_display()

    def enable_calib(self):
        self.canvas.mode = "calibrate"
        QMessageBox.information(self, "标定模式", "请按住左键拖动，在视盘上画出垂直直径。")

    def on_calibrated(self, px):
        px_original = px / max(self.scale_factor, 1e-6)
        self.pixel_to_um = 1500.0 / max(px_original, 1e-6)
        self.update_aiming()
        QMessageBox.information(
            self,
            "标定完成",
            f"物理映射更新: 1像素 = {self.pixel_to_um:.2f} μm\n"
            f"(已自动换算当前缩放倍数 {self.scale_factor:.2f}×)"
        )

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

        p = float(self.slider_power.value())
        t = float(self.slider_duration.value())
        s = float(self.slider_spot.value())
        w = [532.0, 577.0, 672.0][self.combo_wave.currentIndex()]
        _, grade = self.physics_model.compute_z_and_grade(p, s, t, w)

        camera_gain = get_camera_render_gain(self.combo_camera.currentText())
        grade_gain = get_grade_render_gain(grade)
        extra_gain = self.slider_render_gain.value() / 10.0

        visible_radius_um = (s * 1.08 / 2.0) * camera_gain * grade_gain * extra_gain
        r_px = visible_radius_um / max(self.pixel_to_um, 1e-6) * self.scale_factor

        self.canvas.aiming_pos = self.last_mouse
        self.canvas.aiming_radius_px = r_px
        self.canvas.update()

    def on_shoot(self, x, y):
        if self.current_image is None: return
        offset_x = max(0, (self.canvas.width() - self.canvas.pixmap().width()) // 2)
        offset_y = max(0, (self.canvas.height() - self.canvas.pixmap().height()) // 2)
        rx, ry = int((x - offset_x) / self.scale_factor), int((y - offset_y) / self.scale_factor)
        
        if rx < 0 or rx >= self.current_image.shape[1] or ry < 0 or ry >= self.current_image.shape[0]: return

        p = float(self.slider_power.value())
        t = float(self.slider_duration.value())
        s = float(self.slider_spot.value())
        w = [532.0, 577.0, 672.0][self.combo_wave.currentIndex()]

        camera_type = self.combo_camera.currentText()
        extra_render_gain = self.slider_render_gain.value() / 10.0

        self.current_image, grade = render_laser_spot_v2(
            self.current_image, rx, ry, p, t, s, w, self.pixel_to_um, self.physics_model,
            camera_type=camera_type, extra_render_gain=extra_render_gain
        )
        
        self.action_stream.append({
            "pos": [rx, ry], 
            "grade": grade, 
            "params": {
                "power": p, "duration": t, "spot_size": s, "wavelength": w,
                "camera_type": camera_type, "extra_render_gain": extra_render_gain
            },
            "is_trial": self.chk_trial.isChecked()
        })
        
        # 为了展示危险提示，我们需要单独算一下 energy_n
        z_val, _ = self.physics_model.compute_z_and_grade(p, s, t, w)
        alert_text = " (⚠️ 危险：发生组织碳化！)" if grade == 4 and self.physics_model.get_normalized_intensity(z_val) > 1.5 else ""
        self.lbl_info.setText(f"已绘制: {len(self.action_stream)} 点 | 最新等级: {grade} | 相机: {camera_type} | 额外增益: {extra_render_gain:.1f}×{alert_text}")
        self.update_display()

    def update_display(self):
        if self.current_image is None: return
        rgb = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        qimg = QImage(rgb.data, w, h, w*c, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        if self.scale_factor != 1.0:
            pix = pix.scaled(int(w*self.scale_factor), int(h*self.scale_factor), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.canvas.setPixmap(pix)
        self.canvas.setFixedSize(pix.size())

    def export_all(self):
        if not self.action_stream: return
        path, _ = QFileDialog.getSaveFileName(self, "保存结果", f"{self.task_id}_result.json", "JSON (*.json)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"task_id": self.task_id, "shots": self.action_stream}, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "击发数据已导出。")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    TEST_IMG_PATH = os.path.join(os.path.dirname(__file__), "770298-3_before_single_R_reg.png")
    TEST_JSON_PATH = "task.json"
    
    if not os.path.exists(TEST_IMG_PATH):
        print(f"警告: 未找到 {TEST_IMG_PATH}，将生成测试黑色画布。")
        test_bg = np.zeros((800, 1000, 3), dtype=np.uint8)
        cv2.imwrite("test_retina.jpg", test_bg)
        TEST_IMG_PATH = "test_retina.jpg"
        
    if not os.path.exists(TEST_JSON_PATH):
        with open(TEST_JSON_PATH, "w") as f:
            json.dump({"task_id": "TEST_001"}, f)

    win = LaserSimulatorApp(TEST_IMG_PATH, TEST_JSON_PATH)
    win.show()
    sys.exit(app.exec())