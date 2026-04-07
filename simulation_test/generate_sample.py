import sys
import os
import cv2
import numpy as np
import json
import math
from datetime import datetime
from statistics import NormalDist

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QSlider, QComboBox, 
                             QPushButton, QGroupBox, QFormLayout, QMessageBox,
                             QScrollArea, QRadioButton, QButtonGroup)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen

# =========================================================
# 理论物理模型引擎 (精简版：移除可见度计算)
# =========================================================

class LaserPhysicalModel:
    def __init__(self, gt_params=None):
        if gt_params is None:
            gt_params = {}
        self.gt_P = gt_params.get("power", 200.0)
        self.gt_S = gt_params.get("spot_size", 200.0)
        self.gt_T = gt_params.get("exposure_time", 100.0)
        self.gt_lam = gt_params.get("wavelength", 532.0)
        
        self.beta_E = 1.2
        self.beta_T = 0.5
        
        self.power_range = (50.0, 400.0)
        self.spot_range = (50.0, 400.0)
        self.duration_range = (10.0, 500.0)
        self.wavelengths = (532.0, 577.0, 672.0)

        self.tau_0, self.tau_1, self.tau_2 = 0.0, 0.0, 0.0
        self._initialize_thresholds_from_normal()

    def _estimate_raw_z_distribution(self):
        p_values = np.linspace(self.power_range[0], self.power_range[1], 25)
        s_values = np.linspace(self.spot_range[0], self.spot_range[1], 25)
        t_values = np.linspace(self.duration_range[0], self.duration_range[1], 25)

        raw_values = []
        for p in p_values:
            for s in s_values:
                for t in t_values:
                    for lam in self.wavelengths:
                        raw_values.append(self._compute_raw_z(float(p), float(s), float(t), float(lam)))

        raw_arr = np.asarray(raw_values, dtype=np.float64)
        return float(np.mean(raw_arr)), float(np.std(raw_arr))

    def _initialize_thresholds_from_normal(self):
        mu, sigma = self._estimate_raw_z_distribution()
        if sigma <= 1e-8:
            self.tau_0, self.tau_1, self.tau_2 = mu - 0.1, mu, mu + 0.1
        else:
            dist = NormalDist(mu=mu, sigma=sigma)
            self.tau_0 = dist.inv_cdf(0.25)
            self.tau_1 = dist.inv_cdf(0.50)
            self.tau_2 = dist.inv_cdf(0.75)

    def _get_lambda_factor(self, wavelength):
        if wavelength == 532.0: return 0.0
        elif wavelength == 577.0: return 0.18
        elif wavelength == 672.0: return -0.35
        return 0.0
        
    def _compute_raw_z(self, P, S, T, lam):
        if S <= 0 or P <= 0 or T <= 0: return -999
        energy_term = self.beta_E * math.log((P * T) / (S ** 2))
        density_term = self.beta_T * math.log(P / (S ** 2))
        return energy_term + density_term + self._get_lambda_factor(lam)
        
    def compute_z_and_grade(self, P, S, T, lam):
        z = self._compute_raw_z(P, S, T, lam)
        if z < self.tau_0: return z, 1 
        elif z < self.tau_1: return z, 2 
        elif z < self.tau_2: return z, 3 
        else: return z, 4 

# =========================================================
# 渲染核心 (纯净物理高斯分布 + Alpha限制)
# =========================================================

def render_laser_spot_v2(img, center_x, center_y, power_mw, duration_ms, spot_size_um, wavelength_nm, pixel_to_um, model: LaserPhysicalModel):
    # 设定接触镜放大率，默认 1.0 即无额外放大
    lens_magnification = 1.0 
    actual_spot_um = spot_size_um * lens_magnification
    radius_um = actual_spot_um / 2.0
    radius_px = max(1.0, radius_um / max(pixel_to_um, 1e-6))

    _, grade = model.compute_z_and_grade(power_mw, spot_size_um, duration_ms, wavelength_nm)

    p_min, p_max = model.power_range
    t_min, t_max = model.duration_range
    p_n = float(np.clip((power_mw - p_min) / max(1e-6, p_max - p_min), 0.0, 1.0))
    t_n = float(np.clip((duration_ms - t_min) / max(1e-6, t_max - t_min), 0.0, 1.0))
    energy_n = float(np.clip(0.56 * p_n + 0.44 * t_n, 0.0, 1.0))

    grid_half = int(max(8, radius_px * 2.5))
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half + 1)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half + 1)
    if x_min >= x_max or y_min >= y_max:
        return img, 0

    y_coords, x_coords = np.ogrid[y_min - center_y:y_max - center_y, x_min - center_x:x_max - center_x]
    dist = np.sqrt(x_coords.astype(np.float32) ** 2 + y_coords.astype(np.float32) ** 2)
    r = dist / max(1e-6, radius_px)

    # 1. 物理形态模拟 (高斯光束)
    core_mask = np.exp(-((r / 0.45) ** 2))  
    halo_mask = np.exp(-((r / 0.85) ** 2))  

    # 2. 色彩映射 (中心灰白，边缘暗水肿)
    center_color = np.array([240, 245, 245], dtype=np.float32)  
    edge_color = np.array([170, 185, 195], dtype=np.float32)    
    color_map = edge_color * (1.0 - core_mask[..., np.newaxis]) + center_color * core_mask[..., np.newaxis]

    # 3. 严格限制最大不透明度，确保底层血管透出
    max_opacity = 0.35 + 0.45 * energy_n  
    alpha_map = (core_mask * 0.7 + halo_mask * 0.3) * max_opacity
    alpha_map = np.where(r > 1.2, 0.0, alpha_map)
    alpha_3d = alpha_map[..., np.newaxis]

    # 4. 标准 Alpha 混合
    roi = img[y_min:y_max, x_min:x_max].astype(np.float32)
    blended_roi = roi * (1.0 - alpha_3d) + color_map * alpha_3d
    img[y_min:y_max, x_min:x_max] = np.clip(blended_roi, 0.0, 255.0).astype(np.uint8)
    
    return img, grade

# =========================================================
# 交互式图像控件 (精简版：仅保留瞄准和拖拽)
# =========================================================

class ClickableImageLabel(QLabel):
    clicked = pyqtSignal(int, int)
    calibration_done = pyqtSignal(float) 
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

# =========================================================
# 主程序窗口 (关卡编辑器模式)
# =========================================================

class LaserEditorApp(QMainWindow):
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        self.physics_model = LaserPhysicalModel()
        
        self.setWindowTitle("视网膜光凝 - 题目构建与算法验证器")
        self.setFixedSize(1400, 900)
        
        self.original_image = None
        self.current_image = None
        self.scale_factor = 1.0 
        self.pixel_to_um = 2.0 
        self.action_stream = []
        
        self.init_ui()
        self.load_image(image_path)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        control_panel = QWidget()
        control_panel.setFixedWidth(350)
        control_layout = QVBoxLayout(control_panel)
        
        # --- 数据导出模式选择 ---
        export_group = QGroupBox("导出模式")
        export_layout = QVBoxLayout()
        self.radio_task_mode = QRadioButton("构建题目 JSON (设当前参数为正确答案)")
        self.radio_player_mode = QRadioButton("输出玩家测试 JSON (常规流水记录)")
        self.radio_task_mode.setChecked(True) # 默认题目模式
        self.export_mode_group = QButtonGroup()
        self.export_mode_group.addButton(self.radio_task_mode)
        self.export_mode_group.addButton(self.radio_player_mode)
        export_layout.addWidget(self.radio_task_mode)
        export_layout.addWidget(self.radio_player_mode)
        export_group.setLayout(export_layout)
        control_layout.addWidget(export_group)

        # --- 信息面板 ---
        info_group = QGroupBox("统计")
        info_layout = QVBoxLayout()
        self.lbl_spot_count = QLabel("<b>已击发:</b> 0 点")
        info_layout.addWidget(self.lbl_spot_count)
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)
        
        # --- 激光参数 ---
        params_group = QGroupBox("激光参数")
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
        
        params_group.setLayout(form_layout)
        control_layout.addWidget(params_group)
        
        # --- 标定 ---
        calib_group = QGroupBox("系统标定")
        calib_layout = QVBoxLayout()
        self.lbl_scale = QLabel(f"当前比例: 1 px = {self.pixel_to_um:.2f} μm")
        self.btn_calibrate = QPushButton("视盘尺寸标定 (绘制1500μm直径)")
        self.btn_calibrate.clicked.connect(self.enable_calibration_mode)
        calib_layout.addWidget(self.lbl_scale)
        calib_layout.addWidget(self.btn_calibrate)
        calib_group.setLayout(calib_layout)
        control_layout.addWidget(calib_group)
        
        self.btn_clear = QPushButton("清空重置")
        self.btn_clear.clicked.connect(self.reset_image)
        control_layout.addWidget(self.btn_clear)
        control_layout.addStretch() 
        
        # --- 核心导出按钮 ---
        self.btn_export = QPushButton("导出 JSON 与 渲染图像")
        self.btn_export.setMinimumHeight(50)
        self.btn_export.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_data)
        control_layout.addWidget(self.btn_export)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #2c2c2c;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        self.image_label = ClickableImageLabel()
        self.image_label.setStyleSheet("background-color: black;")
        
        self.image_label.clicked.connect(self.on_canvas_click)
        self.image_label.calibration_done.connect(self.process_calibration)
        self.image_label.hovered.connect(self.handle_hover)
        self.image_label.pan_requested.connect(self.handle_pan)
        
        self.scroll_area.setWidget(self.image_label)
        
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
            self.refresh_display()
        else:
            QMessageBox.critical(self, "错误", f"无法读取图像: {image_path}")
            sys.exit()

    def reset_image(self):
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
            self.action_stream = [] 
            self.lbl_spot_count.setText("<b>已击发:</b> 0 点")
            self.refresh_display()

    def enable_calibration_mode(self):
        self.image_label.mode = "calibrate"
        QMessageBox.information(self, "标定", "请在图像中拖拽鼠标，画出视盘的直径。")

    def process_calibration(self, pixel_distance):
        # 仅计算 1px 等于多少 μm (基于原图运算)
        self.pixel_to_um = 1500.0 / pixel_distance
        
        # 强制锁定缩放比例为 1.0，保持 1:1 绝对分辨率
        self.scale_factor = 1.0 
        
        self.lbl_scale.setText(f"已标定: 1 px = {self.pixel_to_um:.2f} μm")
        
        self.refresh_display()
        self.update_aiming_ring()
        QMessageBox.information(self, "标定完成", "标定成功！图像将保持原始分辨率，以便精确提取出题坐标。")

    def handle_pan(self, dx, dy):
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() - dx)
        v_bar.setValue(v_bar.value() - dy)

    def handle_hover(self, lbl_x, lbl_y):
        self.last_hover_x = lbl_x
        self.last_hover_y = lbl_y
        self.update_aiming_ring()

    def update_aiming_ring(self):
        if not hasattr(self, 'last_hover_x'): return
        base_spot = float(self.slider_spot.value())
        radius_px = (base_spot / 2.0) / self.pixel_to_um * self.scale_factor
        self.image_label.aiming_pos = (self.last_hover_x, self.last_hover_y)
        self.image_label.aiming_radius_px = radius_px
        self.image_label.update()

    def on_canvas_click(self, click_x, click_y):
        if self.current_image is None or self.image_label.mode == "calibrate": return

        displayed_pixmap = self.image_label.pixmap()
        if not displayed_pixmap: return
        
        # 坐标换算 (UI层坐标 -> 真实图片坐标)
        disp_w, disp_h = displayed_pixmap.width(), displayed_pixmap.height()
        lbl_w, lbl_h = self.image_label.width(), self.image_label.height()
        offset_x = max(0, (lbl_w - disp_w) // 2)
        offset_y = max(0, (lbl_h - disp_h) // 2)
        
        rel_x, rel_y = click_x - offset_x, click_y - offset_y
        if rel_x < 0 or rel_x >= disp_w or rel_y < 0 or rel_y >= disp_h: return
            
        real_x, real_y = int(rel_x / self.scale_factor), int(rel_y / self.scale_factor)
        
        # 获取面板参数
        power = float(self.slider_power.value())
        duration = float(self.slider_duration.value())
        spot_set = float(self.slider_spot.value())
        wave_str = self.combo_wave.currentText()
        wave = float(wave_str.split()[0])
        
        # 核心渲染
        self.current_image, spot_grade = render_laser_spot_v2(
            self.current_image, real_x, real_y, power, duration, spot_set, wave, 
            self.pixel_to_um, self.physics_model
        )
        
        self.refresh_display()
        
        # 记录数据
        shot_record = {
            "id": len(self.action_stream) + 1,
            "pos": [float(real_x), float(real_y)], 
            "spot_grade": spot_grade, 
            "params": {
                "power": power,
                "spot_size": spot_set,
                "exposure_time": duration,
                "wavelength": wave
            }
        }
        self.action_stream.append(shot_record)
        self.lbl_spot_count.setText(f"<b>已击发:</b> {len(self.action_stream)} 点")

    def refresh_display(self):
        if self.current_image is None: return
        
        rgb_image = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        qt_img = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        
        if self.scale_factor != 1.0:
            pixmap = pixmap.scaled(int(w * self.scale_factor), int(h * self.scale_factor), 
                                   Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(pixmap.size())

    def export_data(self):
        if not self.action_stream:
            QMessageBox.warning(self, "提示", "您尚未进行任何操作。")
            return
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"export_{timestamp}"
        
        # 1. 保存处理后的眼底图像
        img_path = f"{base_filename}_rendered.png"
        cv2.imwrite(img_path, self.current_image)
        
        # 2. 根据所选模式生成 JSON 结构
        json_path = f"{base_filename}.json"
        
        if self.radio_task_mode.isChecked():
            # 【题目模式】将当前UI设定的参数作为该关卡的“正确/标准参数”，所有的点击作为目标区域点
            output_data = {
                "type": "TaskDefinition",
                "task_id": f"TASK_{timestamp}",
                "base_image": "image_filename.png", # 占位，可手动替换
                "pixel_to_um_calibration": self.pixel_to_um,
                "ground_truth_parameters": {
                    "power": float(self.slider_power.value()),
                    "spot_size": float(self.slider_spot.value()),
                    "exposure_time": float(self.slider_duration.value()),
                    "wavelength": float(self.combo_wave.currentText().split()[0])
                },
                "target_coordinates": [shot["pos"] for shot in self.action_stream]
            }
        else:
            # 【玩家模式】正常的序列输出
            output_data = {
                "type": "PlayerSession",
                "session_id": f"SESS_{timestamp}",
                "actions": self.action_stream
            }
            
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        QMessageBox.information(self, "导出成功", f"文件已保存至当前目录：\n\n图像: {img_path}\n数据: {json_path}")


def main():
    app = QApplication(sys.argv)
    
    # 替换为你实际的本地图片路径
    IMAGE_PATH = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\before.png" 
    
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: 找不到图像文件 {IMAGE_PATH}")
        sys.exit(1)
        
    window = LaserEditorApp(IMAGE_PATH)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()