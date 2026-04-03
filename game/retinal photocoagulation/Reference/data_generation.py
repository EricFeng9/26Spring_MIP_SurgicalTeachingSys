import sys
import os
import cv2
import numpy as np
import json
import time
from datetime import datetime
import math

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QSlider, QComboBox, 
                             QPushButton, QGroupBox, QFormLayout, QMessageBox,
                             QScrollArea, QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen

# ---------------------------------------------------------
# CORE RENDERING ENGINE (完全保留原版)
# ---------------------------------------------------------
def render_laser_spot(img, center_x, center_y, power_mw, duration_s, spot_size_um, wavelength, pixel_to_um):
    """
    Highly optimized laser tissue interaction rendering.
    Uses dynamic pixel_to_um ratio for physically accurate sizing based on user calibration.
    """
    radius_um = spot_size_um / 2.0
    
    # Convert physical micrometers to screen pixels
    radius_px = max(1, int(radius_um / pixel_to_um))
    
    # Apply wavelength specific physical properties
    if "Green" in wavelength:
        scatter_multiplier = 1.3
        absorption_efficiency = 1.0
    else: 
        scatter_multiplier = 0.9
        absorption_efficiency = 0.7
        
    effective_radius_px = radius_px * scatter_multiplier
    area = np.pi * (radius_um ** 2)
    
    if area == 0:
        return img
        
    # Calculate energy density and damage index
    energy_density = (power_mw * duration_s) / area
    damage_index = energy_density * absorption_efficiency * 400
    
    # Define ROI boundary to optimize computation speed
    grid_half = int(effective_radius_px * 3) 
    h, w, _ = img.shape
    x_min = max(0, center_x - grid_half)
    x_max = min(w, center_x + grid_half)
    y_min = max(0, center_y - grid_half)
    y_max = min(h, center_y + grid_half)
    
    # Cancel rendering if click is out of bounds
    if x_min >= x_max or y_min >= y_max:
        return img
        
    # Generate mesh grid for gaussian calculation
    y_coords, x_coords = np.ogrid[y_min-center_y:y_max-center_y, x_min-center_x:x_max-center_x]
    dist_sq = x_coords**2 + y_coords**2
    
    sigma_sq = (effective_radius_px / 2.0) ** 2
    if sigma_sq == 0: 
        sigma_sq = 1
        
    # Apply thermal spread formula
    local_damage = np.exp(-dist_sq / (2 * sigma_sq)) * damage_index
    alpha_2d = np.clip(local_damage, 0, 1.0) ** 1.2
    alpha_3d = np.expand_dims(alpha_2d, axis=2) 
    
    # Target color for coagulated retinal tissue
    burn_color = np.array([230, 230, 230], dtype=np.float32)
    
    # Perform alpha blending on the specific ROI
    roi = img[y_min:y_max, x_min:x_max].astype(np.float32)
    blended_roi = roi * (1 - alpha_3d) + burn_color * alpha_3d
    img[y_min:y_max, x_min:x_max] = blended_roi.astype(np.uint8)
    
    return img

# ---------------------------------------------------------
# INTERACTIVE IMAGE LABEL (保留原版标定，增加滚轮缩放事件透传)
# ---------------------------------------------------------
class ClickableImageLabel(QLabel):
    """
    Custom QLabel class to handle mouse interactions.
    Supports firing the laser, calibration, and wheel zooming.
    """
    clicked = pyqtSignal(int, int)
    calibration_done = pyqtSignal(float) 
    zoomed = pyqtSignal(int) # 新增：缩放信号

    def __init__(self):
        super().__init__()
        self.mode = "fire" 
        self.start_pos = None
        self.end_pos = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter) # 确保居中

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "fire":
                self.clicked.emit(event.pos().x(), event.pos().y())
            elif self.mode == "calibrate":
                self.start_pos = event.pos()
                self.end_pos = event.pos()

    def mouseMoveEvent(self, event):
        if self.mode == "calibrate" and self.start_pos:
            self.end_pos = event.pos()
            self.update() 

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode == "calibrate":
            self.end_pos = event.pos()
            if self.start_pos and self.end_pos:
                dx = self.end_pos.x() - self.start_pos.x()
                dy = self.end_pos.y() - self.start_pos.y()
                distance = math.hypot(dx, dy)
                if distance > 10:
                    self.calibration_done.emit(distance)
            self.mode = "fire"
            self.start_pos = None
            self.end_pos = None
            self.update()

    def wheelEvent(self, event):
        """新增：捕获滚轮事件并发出信号"""
        delta = event.angleDelta().y()
        if delta != 0:
            self.zoomed.emit(delta)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.mode == "calibrate" and self.start_pos and self.end_pos:
            painter = QPainter(self)
            pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(self.start_pos, self.end_pos)
            
            painter.setBrush(Qt.GlobalColor.red)
            painter.drawEllipse(self.start_pos, 4, 4)
            painter.drawEllipse(self.end_pos, 4, 4)

# ---------------------------------------------------------
# MAIN APPLICATION WINDOW (增加滚动区域、缩放逻辑、数据录制)
# ---------------------------------------------------------
class LaserSimulatorApp(QMainWindow):
    def __init__(self, student_id, image_path):
        super().__init__()
        self.student_id = student_id
        self.image_path = image_path
        self.case_id = os.path.splitext(os.path.basename(image_path))[0]
        
        self.setWindowTitle(f"视网膜光凝手术模拟器 - 考生: {self.student_id} | 病例: {self.case_id}")
        self.setFixedSize(1400, 900)
        
        # 图像数据
        self.original_image = None
        self.current_image = None
        self.scale_factor = 1.0 # 新增：当前图像缩放比例
        
        # 录制数据
        self.pixel_to_um = 2.0 
        self.action_stream = []
        self.start_time = datetime.now()
        self.start_time_counter = time.time()
        
        self.init_ui()
        self.load_image(image_path)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # ========== 左侧控制面板 ==========
        control_panel = QWidget()
        control_panel.setFixedWidth(350)
        control_layout = QVBoxLayout(control_panel)
        
        # 新增：操作状态面板
        info_group = QGroupBox("当前任务信息")
        info_layout = QVBoxLayout()
        info_layout.addWidget(QLabel(f"<b>操作者:</b> {self.student_id}"))
        info_layout.addWidget(QLabel(f"<b>病例:</b> {self.case_id}"))
        self.lbl_spot_count = QLabel("<b>已击发:</b> 0 点")
        info_layout.addWidget(self.lbl_spot_count)
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)
        
        # Core parameters section
        params_group = QGroupBox("核心可调参数 (Core Parameters)")
        form_layout = QFormLayout()
        
        self.slider_power = QSlider(Qt.Orientation.Horizontal)
        self.slider_power.setRange(50, 300)
        self.slider_power.setValue(100)
        self.lbl_power = QLabel("100 mW")
        self.slider_power.valueChanged.connect(lambda v: self.lbl_power.setText(f"{v} mW"))
        form_layout.addRow("⚡ 功率:", self.slider_power)
        form_layout.addRow("", self.lbl_power)
        
        self.slider_spot = QSlider(Qt.Orientation.Horizontal)
        self.slider_spot.setRange(50, 300)
        self.slider_spot.setValue(100)
        self.lbl_spot = QLabel("100 μm")
        self.slider_spot.valueChanged.connect(lambda v: self.lbl_spot.setText(f"{v} μm"))
        form_layout.addRow("⚫ 光斑:", self.slider_spot)
        form_layout.addRow("", self.lbl_spot)
        
        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(10, 200)
        self.slider_duration.setValue(100)
        self.lbl_duration = QLabel("0.10 s")
        self.slider_duration.valueChanged.connect(lambda v: self.lbl_duration.setText(f"{v/1000:.2f} s"))
        form_layout.addRow("⏱️ 时间:", self.slider_duration)
        form_layout.addRow("", self.lbl_duration)
        
        self.combo_wave = QComboBox()
        self.combo_wave.addItems(["Green 绿色 (532nm)", "Red 红色 (672nm)"])
        form_layout.addRow("🌈 波长:", self.combo_wave)
        
        params_group.setLayout(form_layout)
        control_layout.addWidget(params_group)
        
        # Calibration section
        calib_group = QGroupBox("系统状态与标定 (Calibration)")
        calib_layout = QVBoxLayout()
        self.lbl_scale = QLabel(f"当前比例: 1 像素 = {self.pixel_to_um:.2f} μm")
        self.lbl_scale.setStyleSheet("color: orange; font-weight: bold;")
        self.btn_calibrate = QPushButton("📐 视盘尺寸标定 (绘制测量线)")
        self.btn_calibrate.setStyleSheet("background-color: #2196F3; color: white; padding: 5px;")
        self.btn_calibrate.clicked.connect(self.enable_calibration_mode)
        calib_layout.addWidget(self.lbl_scale)
        calib_layout.addWidget(self.btn_calibrate)
        calib_group.setLayout(calib_layout)
        control_layout.addWidget(calib_group)
        
        # Action buttons section
        self.btn_clear = QPushButton("🗑️ 清除所有光斑")
        self.btn_clear.setStyleSheet("padding: 5px;")
        self.btn_clear.clicked.connect(self.reset_image)
        control_layout.addWidget(self.btn_clear)
        
        control_layout.addStretch() 
        
        # 新增：导出按钮
        self.btn_export = QPushButton("💾 结束手术并导出记录")
        self.btn_export.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_json_and_exit)
        control_layout.addWidget(self.btn_export)
        
        # ========== 右侧画布区 (放入 ScrollArea 支持平移) ==========
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #1e1e1e;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter) # 保证图片居中
        self.scroll_area.setWidgetResizable(True) # 允许 Label 根据图片调整大小
        
        self.image_label = ClickableImageLabel()
        self.image_label.setStyleSheet("background-color: black;")
        
        self.image_label.clicked.connect(self.on_canvas_click)
        self.image_label.calibration_done.connect(self.process_calibration)
        self.image_label.zoomed.connect(self.handle_zoom) # 连接缩放信号
        
        self.scroll_area.setWidget(self.image_label)
        
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.scroll_area, stretch=1)

    def load_image(self, image_path):
        """动态加载用户选择的图片"""
        img = cv2.imread(image_path)
        if img is not None:
            # 去掉了强行调整大小的逻辑，保留图片原生分辨率或初始适配窗口
            self.original_image = img
            self.current_image = self.original_image.copy()
            self.scale_factor = 1.0
            self.update_display()
        else:
            QMessageBox.critical(self, "错误", "无法读取图像文件！")
            sys.exit()

    def reset_image(self):
        if self.original_image is not None:
            self.current_image = self.original_image.copy()
            self.action_stream = [] # 清空记录
            self.lbl_spot_count.setText("<b>已击发:</b> 0 点")
            self.update_display()

    def enable_calibration_mode(self):
        self.image_label.mode = "calibrate"
        QMessageBox.information(self, "标定模式", 
            "标定已开启：\n请在右侧图片中，按住鼠标左键拖动，画出『视盘』的垂直直径。\n系统将以 1500μm 为标准自动计算比例尺。")

    def process_calibration(self, pixel_distance):
        # 注意：这里的 pixel_distance 是在缩放后的画面上画的线
        # 我们需要把它还原成基于原图真实像素的距离
        real_pixel_distance = pixel_distance / self.scale_factor
        
        self.pixel_to_um = 1500.0 / real_pixel_distance
        self.lbl_scale.setText(f"当前比例 (已标定): 1 真实像素 = {self.pixel_to_um:.2f} μm")
        self.lbl_scale.setStyleSheet("color: #4CAF50; font-weight: bold;")
        QMessageBox.information(self, "标定成功", f"物理尺寸匹配完毕。您可以开始发射激光了！")

    def handle_zoom(self, delta):
        """处理滚轮缩放逻辑"""
        if delta > 0:
            self.scale_factor *= 1.15 # 放大
        else:
            self.scale_factor /= 1.15 # 缩小
            
        # 限制最小和最大缩放比例
        self.scale_factor = max(0.2, min(self.scale_factor, 5.0))
        self.update_display()

    def keyPressEvent(self, event):
        """实现 WASD / 方向键 平移逻辑 (控制 ScrollArea 的滚动条)"""
        step = 50
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar = self.scroll_area.horizontalScrollBar()
        
        if event.key() in (Qt.Key.Key_W, Qt.Key.Key_Up):
            v_bar.setValue(v_bar.value() - step)
        elif event.key() in (Qt.Key.Key_S, Qt.Key.Key_Down):
            v_bar.setValue(v_bar.value() + step)
        elif event.key() in (Qt.Key.Key_A, Qt.Key.Key_Left):
            h_bar.setValue(h_bar.value() - step)
        elif event.key() in (Qt.Key.Key_D, Qt.Key.Key_Right):
            h_bar.setValue(h_bar.value() + step)
        else:
            super().keyPressEvent(event)

    def on_canvas_click(self, click_x, click_y):
        if self.current_image is None or self.image_label.mode == "calibrate":
            return
            
        # 获取当前显示的缩放后图像的尺寸
        displayed_pixmap = self.image_label.pixmap()
        if not displayed_pixmap: return
        disp_w, disp_h = displayed_pixmap.width(), displayed_pixmap.height()
        
        # 因为 Label 设置了居中，如果显示区域大于图片，图片周围会有黑边。需要计算这个偏移。
        lbl_w = self.image_label.width()
        lbl_h = self.image_label.height()
        offset_x = max(0, (lbl_w - disp_w) // 2)
        offset_y = max(0, (lbl_h - disp_h) // 2)
        
        # 减去居中黑边偏移
        rel_x = click_x - offset_x
        rel_y = click_y - offset_y
        
        # 检查是否点击在图片内部
        if rel_x < 0 or rel_x >= disp_w or rel_y < 0 or rel_y >= disp_h:
            return
            
        # 极其关键：将缩放后的点击坐标，映射回 OpenCV 原始矩阵的真实像素坐标
        real_x = int(rel_x / self.scale_factor)
        real_y = int(rel_y / self.scale_factor)
        
        power = self.slider_power.value()
        duration = self.slider_duration.value() / 1000.0 
        spot = self.slider_spot.value()
        wave = self.combo_wave.currentText()
        
        # 调用核心渲染引擎，传入的是真实的像素坐标
        self.current_image = render_laser_spot(
            self.current_image, real_x, real_y, power, duration, spot, wave, self.pixel_to_um
        )
        self.update_display()
        
        # --- 记录数据 (记录真实的像素坐标，无视缩放) ---
        elapsed_ms = int((time.time() - self.start_time_counter) * 1000)
        spot_record = {
            "spot_id": len(self.action_stream) + 1,
            "timestamp_ms": elapsed_ms,
            "position_px": [real_x, real_y], 
            "parameters": {
                "power_mw": power,
                "duration_s": duration,
                "size_um": spot,
                "wavelength": wave.split()[0] # 提取波长单词如 "Green"
            }
        }
        self.action_stream.append(spot_record)
        self.lbl_spot_count.setText(f"<b>已击发:</b> {len(self.action_stream)} 点")

    def update_display(self):
        """将 numpy 矩阵转为 QPixmap 并根据 scale_factor 进行缩放显示"""
        if self.current_image is None: return
            
        rgb_image = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qt_img = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        
        # 应用缩放
        if self.scale_factor != 1.0:
            new_w = int(w * self.scale_factor)
            new_h = int(h * self.scale_factor)
            pixmap = pixmap.scaled(new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        self.image_label.setPixmap(pixmap)
        # 更新 Label 的固定大小以适配 ScrollArea 的滚动
        self.image_label.setFixedSize(pixmap.size())

    def export_json_and_exit(self):
        if not self.action_stream:
            QMessageBox.warning(self, "提示", "未发射激光，不生成文件。")
            self.close()
            return
            
        end_time = datetime.now()
        session_id = f"{self.student_id}_{self.start_time.strftime('%Y%m%d_%H%M%S')}"
        img_h, img_w = self.current_image.shape[:2]
        
        data = {
            "session_info": {
                "session_id": session_id,
                "student_id": self.student_id,
                "case_id": self.case_id,
                "image_path": os.path.abspath(self.image_path),
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_spots": len(self.action_stream)
            },
            "environment": {
                "image_resolution": [img_w, img_h], # 记录原始分辨率
                "pixel_to_um_ratio": round(self.pixel_to_um, 3)
            },
            "action_stream": self.action_stream
        }
        
        output_filename = f"{session_id}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        QMessageBox.information(self, "成功", f"数据已导出: {output_filename}")
        self.close()

# ---------------------------------------------------------
# PROGRAM ENTRY POINT
# ---------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    
    # 强制前置输入
    student_id, ok = QInputDialog.getText(None, "登录", "请输入考生编号:")
    if not ok or not student_id.strip(): sys.exit()
        
    image_path, _ = QFileDialog.getOpenFileName(None, "选择图像", "", "Images (*.png *.jpg *.jpeg *.bmp)")
    if not image_path: sys.exit()
        
    window = LaserSimulatorApp(student_id.strip(), image_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()