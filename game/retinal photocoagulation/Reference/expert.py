import sys
import os
import cv2
import numpy as np
import json
from datetime import datetime
import math

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QSlider, QComboBox, QLineEdit,
                             QPushButton, QGroupBox, QFormLayout, QMessageBox,
                             QScrollArea, QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen

# ==========================================
# 核心渲染引擎 (保持物理拟真)
# ==========================================
def render_laser_spot(img, center_x, center_y, power_mw, duration_s, spot_size_um, wavelength, pixel_to_um=3.0):
    radius_um = spot_size_um / 2.0
    radius_px = max(1, int(radius_um / pixel_to_um))
    
    if "Green" in wavelength:
        scatter_multiplier = 1.3; absorption_efficiency = 1.0
    else: 
        scatter_multiplier = 0.9; absorption_efficiency = 0.7
        
    effective_radius_px = radius_px * scatter_multiplier
    area = np.pi * (radius_um ** 2)
    if area == 0: return img
        
    energy_density = (power_mw * duration_s) / area
    damage_index = energy_density * absorption_efficiency * 400
    
    grid_half = int(effective_radius_px * 3) 
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half)
    
    if x_min >= x_max or y_min >= y_max: return img
        
    y_coords, x_coords = np.ogrid[y_min-center_y:y_max-center_y, x_min-center_x:x_max-center_x]
    dist_sq = x_coords**2 + y_coords**2
    sigma_sq = (effective_radius_px / 2.0) ** 2 if effective_radius_px > 0 else 1
        
    local_damage = np.exp(-dist_sq / (2 * sigma_sq)) * damage_index
    alpha_2d = np.clip(local_damage, 0, 1.0) ** 1.2
    alpha_3d = np.expand_dims(alpha_2d, axis=2) 
    
    burn_color = np.array([230, 230, 230], dtype=np.float32)
    roi = img[y_min:y_max, x_min:x_max].astype(np.float32)
    blended_roi = roi * (1 - alpha_3d) + burn_color * alpha_3d
    img[y_min:y_max, x_min:x_max] = blended_roi.astype(np.uint8)
    return img

# ==========================================
# 交互视图组件 (支持缩放平移 + 画线标定)
# ==========================================
class InteractiveMarkerView(QLabel):
    clicked = pyqtSignal(int, int)
    zoomed = pyqtSignal(int)
    calibration_done = pyqtSignal(float) # 新增：标定完成信号

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode = "fire" 
        self.start_pos = None
        self.end_pos = None

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
        delta = event.angleDelta().y()
        if delta != 0: self.zoomed.emit(delta)

    def paintEvent(self, event):
        super().paintEvent(event)
        # 绘制绿色的标定测量线
        if self.mode == "calibrate" and self.start_pos and self.end_pos:
            painter = QPainter(self)
            pen = QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(self.start_pos, self.end_pos)
            painter.setBrush(Qt.GlobalColor.red)
            painter.drawEllipse(self.start_pos, 4, 4)
            painter.drawEllipse(self.end_pos, 4, 4)

# ==========================================
# 专家标注主程序
# ==========================================
class ExpertAnnotationApp(QMainWindow):
    def __init__(self, expert_name, image_path):
        super().__init__()
        self.expert_name = expert_name
        self.image_path = image_path
        self.case_id = os.path.splitext(os.path.basename(image_path))[0]
        
        self.setWindowTitle(f"专家 GT 标注工具 - 专家: {self.expert_name} | 病例: {self.case_id}")
        self.setFixedSize(1500, 900)
        
        self.original_image = cv2.imread(self.image_path)
        if self.original_image is None:
            QMessageBox.critical(self, "错误", "无法读取图像！")
            sys.exit()
            
        self.current_image = self.original_image.copy()
        self.scale_factor = 1.0
        self.pixel_to_um = 2.0 # 默认比例尺
        
        self.gt_segments = []
        self.current_segment_index = -1
        
        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        control_panel = QWidget()
        control_panel.setFixedWidth(400)
        control_layout = QVBoxLayout(control_panel)
        
        # 1. 任务信息
        info_group = QGroupBox("诊断与治疗方案设定")
        info_layout = QFormLayout()
        self.edit_diagnosis = QLineEdit("视网膜马蹄形裂孔")
        self.edit_treatment = QLineEdit("双排激光光凝封堵")
        info_layout.addRow("初步诊断:", self.edit_diagnosis)
        info_layout.addRow("建议方案:", self.edit_treatment)
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)
        
        # 2. 【新增】系统状态与标定 (Calibration)
        calib_group = QGroupBox("物理尺寸标定 (Calibration)")
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
        
        # 3. 段落管理器
        seg_group = QGroupBox("手术段落管理 (Segments)")
        seg_group.setStyleSheet("QGroupBox { border: 2px solid #2196F3; font-weight: bold; }")
        seg_layout = QVBoxLayout()
        
        self.combo_segments = QComboBox()
        self.combo_segments.currentIndexChanged.connect(self.on_segment_changed)
        seg_layout.addWidget(QLabel("当前绘制段落:"))
        seg_layout.addWidget(self.combo_segments)
        
        form_seg = QFormLayout()
        self.edit_seg_category = QComboBox()
        self.edit_seg_category.addItems(["TEAR_INNER_RING", "TEAR_OUTER_RING", "MACULA_GRID", "PRP_QUADRANT", "OTHER"])
        self.edit_seg_desc = QLineEdit()
        form_seg.addRow("段落类别 (Cat):", self.edit_seg_category)
        form_seg.addRow("段落描述 (Desc):", self.edit_seg_desc)
        seg_layout.addLayout(form_seg)
        
        btn_add_seg = QPushButton("➕ 新建手术段落")
        btn_add_seg.setStyleSheet("background-color: #2196F3; color: white; padding: 5px;")
        btn_add_seg.clicked.connect(self.add_new_segment)
        seg_layout.addWidget(btn_add_seg)
        seg_group.setLayout(seg_layout)
        control_layout.addWidget(seg_group)
        
        # 4. 参数调节台
        params_group = QGroupBox("专家级参数控制台")
        form_layout = QFormLayout()
        
        self.slider_power = QSlider(Qt.Orientation.Horizontal)
        self.slider_power.setRange(50, 300); self.slider_power.setValue(180)
        self.lbl_power = QLabel("180 mW")
        self.slider_power.valueChanged.connect(lambda v: self.lbl_power.setText(f"{v} mW"))
        form_layout.addRow("⚡ 功率:", self.slider_power)
        form_layout.addRow("", self.lbl_power)
        
        self.slider_spot = QSlider(Qt.Orientation.Horizontal)
        self.slider_spot.setRange(50, 300); self.slider_spot.setValue(200)
        self.lbl_spot = QLabel("200 μm")
        self.slider_spot.valueChanged.connect(lambda v: self.lbl_spot.setText(f"{v} μm"))
        form_layout.addRow("⚫ 光斑:", self.slider_spot)
        form_layout.addRow("", self.lbl_spot)
        
        self.slider_duration = QSlider(Qt.Orientation.Horizontal)
        self.slider_duration.setRange(10, 200); self.slider_duration.setValue(100)
        self.lbl_duration = QLabel("0.10 s")
        self.slider_duration.valueChanged.connect(lambda v: self.lbl_duration.setText(f"{v/1000:.2f} s"))
        form_layout.addRow("⏱️ 时间:", self.slider_duration)
        form_layout.addRow("", self.lbl_duration)
        
        self.combo_wave = QComboBox()
        self.combo_wave.addItems(["Green (532nm)", "Red (672nm)"])
        form_layout.addRow("🌈 波长:", self.combo_wave)
        params_group.setLayout(form_layout)
        control_layout.addWidget(params_group)
        
        # 撤销与导出
        self.btn_clear = QPushButton("🗑️ 撤销上一击发")
        self.btn_clear.clicked.connect(self.undo_last_spot)
        control_layout.addWidget(self.btn_clear)
        
        control_layout.addStretch() 
        self.btn_export = QPushButton("💾 生成专家 GT 标准数据")
        self.btn_export.setStyleSheet("background-color: #ff9800; color: white; padding: 15px; font-size: 14px; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_gt_json)
        control_layout.addWidget(self.btn_export)
        main_layout.addWidget(control_panel)
        
        # 5. 右侧视图
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #1e1e1e;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidgetResizable(True)
        
        self.image_label = InteractiveMarkerView()
        self.image_label.clicked.connect(self.on_canvas_click)
        self.image_label.zoomed.connect(self.handle_zoom)
        self.image_label.calibration_done.connect(self.process_calibration) # 连接标定信号
        self.scroll_area.setWidget(self.image_label)
        main_layout.addWidget(self.scroll_area, stretch=1)
        
        # 初始化界面
        self.add_new_segment()
        self.update_display()

    # ================= 标定逻辑 =================
    def enable_calibration_mode(self):
        self.image_label.mode = "calibrate"
        QMessageBox.information(self, "标定模式", 
            "标定已开启：\n请在右侧图片中，按住鼠标左键拖动，画出『视盘』的垂直直径。\n系统将以 1500μm 为标准自动计算物理比例尺。")

    def process_calibration(self, pixel_distance):
        # 还原到无缩放的真实像素距离
        real_pixel_distance = pixel_distance / self.scale_factor
        
        self.pixel_to_um = 1500.0 / real_pixel_distance
        self.lbl_scale.setText(f"当前比例 (已标定): 1 真实像素 = {self.pixel_to_um:.2f} μm")
        self.lbl_scale.setStyleSheet("color: #4CAF50; font-weight: bold;")
        
        # 标定完成后，立刻重绘所有光斑以应用新的比例尺大小
        self.redraw_all_segments()
        
        QMessageBox.information(self, "标定成功", f"物理尺寸匹配完毕。\n当前比例: 1像素 = {self.pixel_to_um:.2f}μm")

    # ================= 段落与绘图逻辑 =================
    def add_new_segment(self):
        group_id = f"seg_{len(self.gt_segments) + 1:02d}"
        base_params = {
            "power": self.slider_power.value(),
            "size": self.slider_spot.value(),
            "duration": self.slider_duration.value() / 1000.0,
            "wave": self.combo_wave.currentText().split()[0]
        }
        new_seg = {
            "group_id": group_id,
            "category": "TEAR_INNER_RING",
            "description": f"段落 {group_id}",
            "base_params": base_params,
            "points": [],
            "overrides": {}
        }
        self.gt_segments.append(new_seg)
        self.combo_segments.addItem(f"{group_id} - 准备绘制")
        self.combo_segments.setCurrentIndex(len(self.gt_segments) - 1)
        self.edit_seg_desc.setText(new_seg["description"])

    def on_segment_changed(self, index):
        self.current_segment_index = index
        if 0 <= index < len(self.gt_segments):
            seg = self.gt_segments[index]
            self.edit_seg_category.setCurrentText(seg["category"])
            self.edit_seg_desc.setText(seg["description"])

    def on_canvas_click(self, click_x, click_y):
        if self.current_segment_index < 0 or self.image_label.mode == "calibrate":
            return
            
        displayed_pixmap = self.image_label.pixmap()
        if not displayed_pixmap: return
        disp_w, disp_h = displayed_pixmap.width(), displayed_pixmap.height()
        lbl_w, lbl_h = self.image_label.width(), self.image_label.height()
        offset_x, offset_y = max(0, (lbl_w - disp_w) // 2), max(0, (lbl_h - disp_h) // 2)
        rel_x, rel_y = click_x - offset_x, click_y - offset_y
        
        if rel_x < 0 or rel_x >= disp_w or rel_y < 0 or rel_y >= disp_h: return
        
        real_x, real_y = int(rel_x / self.scale_factor), int(rel_y / self.scale_factor)
        
        current_power = self.slider_power.value()
        current_size = self.slider_spot.value()
        current_duration = self.slider_duration.value() / 1000.0
        current_wave = self.combo_wave.currentText().split()[0]
        
        active_seg = self.gt_segments[self.current_segment_index]
        active_seg["category"] = self.edit_seg_category.currentText()
        active_seg["description"] = self.edit_seg_desc.text()
        
        pt_index = len(active_seg["points"])
        active_seg["points"].append([real_x, real_y])
        
        base = active_seg["base_params"]
        override_data = {}
        if current_power != base["power"]: override_data["power"] = current_power
        if current_size != base["size"]: override_data["size"] = current_size
        if current_duration != base["duration"]: override_data["duration"] = current_duration
        
        if override_data: active_seg["overrides"][str(pt_index)] = override_data
        self.redraw_all_segments()

    def undo_last_spot(self):
        if self.current_segment_index >= 0:
            active_seg = self.gt_segments[self.current_segment_index]
            if active_seg["points"]:
                pt_idx = str(len(active_seg["points"]) - 1)
                active_seg["points"].pop()
                if pt_idx in active_seg["overrides"]:
                    del active_seg["overrides"][pt_idx]
                self.redraw_all_segments()

    def redraw_all_segments(self):
        self.current_image = self.original_image.copy()
        
        for seg in self.gt_segments:
            base = seg["base_params"]
            for i, pt in enumerate(seg["points"]):
                ovr = seg["overrides"].get(str(i), {})
                pwr = ovr.get("power", base["power"])
                sz = ovr.get("size", base["size"])
                dur = ovr.get("duration", base["duration"])
                # 这里的渲染会读取最新的 self.pixel_to_um
                self.current_image = render_laser_spot(
                    self.current_image, pt[0], pt[1], pwr, dur, sz, base["wave"], self.pixel_to_um
                )
                
        overlay = self.current_image.copy()
        for seg in self.gt_segments:
            pts = np.array(seg["points"], np.int32)
            if len(pts) > 1:
                cv2.polylines(overlay, [pts], isClosed=False, color=(0, 255, 255), thickness=2)
                
        cv2.addWeighted(overlay, 0.6, self.current_image, 0.4, 0, self.current_image)
        self.update_display()

    def handle_zoom(self, delta):
        if delta > 0: self.scale_factor *= 1.15 
        else: self.scale_factor /= 1.15 
        self.scale_factor = max(0.2, min(self.scale_factor, 5.0))
        self.update_display()

    def keyPressEvent(self, event):
        step = 50
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar = self.scroll_area.horizontalScrollBar()
        if event.key() in (Qt.Key.Key_W, Qt.Key.Key_Up): v_bar.setValue(v_bar.value() - step)
        elif event.key() in (Qt.Key.Key_S, Qt.Key.Key_Down): v_bar.setValue(v_bar.value() + step)
        elif event.key() in (Qt.Key.Key_A, Qt.Key.Key_Left): h_bar.setValue(h_bar.value() - step)
        elif event.key() in (Qt.Key.Key_D, Qt.Key.Key_Right): h_bar.setValue(h_bar.value() + step)
        else: super().keyPressEvent(event)

    def update_display(self):
        if self.current_image is None: return
        rgb_image = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        qt_img = QImage(rgb_image.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        if self.scale_factor != 1.0:
            pixmap = pixmap.scaled(int(w * self.scale_factor), int(h * self.scale_factor), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(pixmap)
        self.image_label.setFixedSize(pixmap.size())

    def export_gt_json(self):
        valid_segments = [s for s in self.gt_segments if len(s["points"]) > 0]
        if not valid_segments:
            QMessageBox.warning(self, "提示", "没有绘制任何有效的标准点位！")
            return
            
        data = {
            "case_id": self.case_id,
            "expert_id": self.expert_name,
            "creation_time": datetime.now().isoformat(),
            "patient_info": {
                "diagnosis": self.edit_diagnosis.text(),
                "recommended_treatment": self.edit_treatment.text()
            },
            "environment": {
                "pixel_to_um_ratio": round(self.pixel_to_um, 3),
                "image_resolution": [self.original_image.shape[1], self.original_image.shape[0]]
            },
            "gt_segments": valid_segments
        }
        
        output_filename = f"GT_{self.case_id}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
            
        QMessageBox.information(self, "导出成功", f"专家标准数据已生成！\n共 {len(valid_segments)} 个手术段落。\n已保存为: {output_filename}")

# ==========================================
# 启动入口
# ==========================================
def main():
    app = QApplication(sys.argv)
    expert_name, ok = QInputDialog.getText(None, "专家认证", "请输入您的专家名称 (如 Dr. Smith):")
    if not ok or not expert_name.strip(): sys.exit()
        
    image_path, _ = QFileDialog.getOpenFileName(None, "选择要标注的眼底图像", "", "Images (*.png *.jpg *.jpeg *.bmp)")
    if not image_path: sys.exit()
        
    window = ExpertAnnotationApp(expert_name.strip(), image_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()