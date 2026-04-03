import sys
import os
import cv2
import numpy as np
import json
import math

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QPushButton, QGroupBox, 
                             QFormLayout, QMessageBox, QScrollArea, QFileDialog, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap

# ==========================================
# 核心渲染引擎 (与记录器保持绝对一致)
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
# 视图组件 (仅支持查看和缩放平移)
# ==========================================
class PlaybackMarkerView(QLabel):
    zoomed = pyqtSignal(int)
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta != 0: self.zoomed.emit(delta)

# ==========================================
# 回放主程序
# ==========================================
class PlaybackSimulatorApp(QMainWindow):
    def __init__(self, json_path):
        super().__init__()
        self.json_path = json_path
        self.setWindowTitle("视网膜光凝手术 - 录像回放系统")
        self.setFixedSize(1400, 900)
        
        # 1. 解析 JSON 数据
        if not self.load_record_data():
            sys.exit()
            
        # 回放控制状态
        self.current_playback_time_ms = 0
        self.current_spot_idx = 0
        self.is_playing = False
        self.scale_factor = 1.0
        
        # 定时器设置 (30 FPS 刷新率，约 33ms 一帧)
        self.tick_interval_ms = 33
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_playback_tick)
        
        self.init_ui()
        self.update_display()

    def load_record_data(self):
        """解析JSON并加载对应的原图"""
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                self.record_data = json.load(f)
                
            self.session_info = self.record_data["session_info"]
            self.action_stream = self.record_data.get("action_stream", [])
            self.pixel_to_um = self.record_data["environment"]["pixel_to_um_ratio"]
            
            # 尝试加载原图
            image_path = self.session_info.get("image_path", "")
            if not os.path.exists(image_path):
                # 如果原路径失效，弹窗让用户手动找图
                QMessageBox.warning(None, "图像丢失", f"记录中的图像路径失效:\n{image_path}\n请手动定位该底图。")
                image_path, _ = QFileDialog.getOpenFileName(None, "寻找缺失的眼底图像", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                if not image_path: return False
                
            self.original_image = cv2.imread(image_path)
            if self.original_image is None:
                QMessageBox.critical(None, "错误", "图像读取失败！")
                return False
                
            self.current_image = self.original_image.copy()
            
            # 计算总时长
            if self.action_stream:
                self.total_time_ms = self.action_stream[-1]["timestamp_ms"] + 500 # 多留0.5秒尾巴
            else:
                self.total_time_ms = 0
                
            return True
            
        except Exception as e:
            QMessageBox.critical(None, "读取失败", f"无法解析记录文件:\n{str(e)}")
            return False

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        
        # ========== 左侧控制面板 ==========
        control_panel = QWidget()
        control_panel.setFixedWidth(350)
        control_layout = QVBoxLayout(control_panel)
        
        # 记录信息面板
        info_group = QGroupBox("📋 录像信息")
        info_layout = QFormLayout()
        info_layout.addRow("操作者:", QLabel(self.session_info.get("student_id", "未知")))
        info_layout.addRow("病例ID:", QLabel(self.session_info.get("case_id", "未知")))
        info_layout.addRow("总击发数:", QLabel(f"{len(self.action_stream)} 点"))
        info_layout.addRow("操作总时长:", QLabel(f"{self.total_time_ms / 1000:.1f} 秒"))
        info_layout.addRow("标定比例尺:", QLabel(f"1px = {self.pixel_to_um:.2f}μm"))
        info_group.setLayout(info_layout)
        control_layout.addWidget(info_group)
        
        # 回放控制面板
        playback_group = QGroupBox("▶️ 回放控制")
        pb_layout = QVBoxLayout()
        
        # 进度状态
        self.lbl_progress = QLabel("进度: 0 / 0 点 (0.0s)")
        self.lbl_progress.setStyleSheet("font-weight: bold; color: #2196F3; font-size: 14px;")
        pb_layout.addWidget(self.lbl_progress)
        
        # 倍速选择
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("播放速度:"))
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["1.0x (正常)", "2.0x (快进)", "5.0x (极速)", "0.5x (慢放)"])
        speed_layout.addWidget(self.combo_speed)
        pb_layout.addLayout(speed_layout)
        
        # 播放/暂停按钮
        self.btn_play = QPushButton("▶️ 开始播放")
        self.btn_play.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.btn_play.clicked.connect(self.toggle_playback)
        pb_layout.addWidget(self.btn_play)
        
        # 重置按钮
        self.btn_reset = QPushButton("🔄 重新开始")
        self.btn_reset.clicked.connect(self.reset_playback)
        pb_layout.addWidget(self.btn_reset)
        
        playback_group.setLayout(pb_layout)
        control_layout.addWidget(playback_group)
        
        control_layout.addStretch()
        main_layout.addWidget(control_panel)
        
        # ========== 右侧视图区 ==========
        self.scroll_area = QScrollArea()
        self.scroll_area.setStyleSheet("background-color: #1e1e1e;")
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidgetResizable(True)
        
        self.image_label = PlaybackMarkerView()
        self.image_label.zoomed.connect(self.handle_zoom)
        self.scroll_area.setWidget(self.image_label)
        main_layout.addWidget(self.scroll_area, stretch=1)

    # ================= 回放核心逻辑 =================
    def toggle_playback(self):
        if not self.action_stream: return
            
        if self.is_playing:
            self.is_playing = False
            self.timer.stop()
            self.btn_play.setText("▶️ 继续播放")
            self.btn_play.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        else:
            if self.current_spot_idx >= len(self.action_stream):
                self.reset_playback() # 如果播完了再点播放，就重头开始
                
            self.is_playing = True
            self.timer.start(self.tick_interval_ms)
            self.btn_play.setText("⏸️ 暂停")
            self.btn_play.setStyleSheet("background-color: #f44336; color: white; padding: 10px; font-weight: bold;")

    def reset_playback(self):
        """恢复到初始状态"""
        self.is_playing = False
        self.timer.stop()
        self.current_playback_time_ms = 0
        self.current_spot_idx = 0
        self.current_image = self.original_image.copy()
        
        self.btn_play.setText("▶️ 开始播放")
        self.btn_play.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; font-weight: bold;")
        self.update_ui_stats()
        self.update_display()

    def get_speed_multiplier(self):
        text = self.combo_speed.currentText()
        if "0.5x" in text: return 0.5
        if "2.0x" in text: return 2.0
        if "5.0x" in text: return 5.0
        return 1.0

    def on_playback_tick(self):
        """定时器心跳：检查当前时间戳，如果到了就渲染光斑"""
        if not self.is_playing: return
        
        # 推进虚拟时间
        self.current_playback_time_ms += (self.tick_interval_ms * self.get_speed_multiplier())
        
        spots_rendered = False
        
        # 循环检查是否有光斑在这个时间段内发生
        while self.current_spot_idx < len(self.action_stream):
            spot = self.action_stream[self.current_spot_idx]
            
            if spot["timestamp_ms"] <= self.current_playback_time_ms:
                # 触发渲染！
                pos = spot["position_px"]
                params = spot["parameters"]
                
                self.current_image = render_laser_spot(
                    self.current_image, pos[0], pos[1], 
                    params["power_mw"], params["duration_s"], 
                    params["size_um"], params["wavelength"], 
                    self.pixel_to_um
                )
                self.current_spot_idx += 1
                spots_rendered = True
            else:
                break # 还没到下一个光斑的时间，跳出循环等待下一次心跳
                
        if spots_rendered:
            self.update_display()
            
        self.update_ui_stats()
        
        # 检查是否播完
        if self.current_spot_idx >= len(self.action_stream):
            self.is_playing = False
            self.timer.stop()
            self.btn_play.setText("✅ 回放结束 (点击重播)")
            self.btn_play.setStyleSheet("background-color: #9E9E9E; color: white; padding: 10px; font-weight: bold;")

    # ================= 视图更新逻辑 =================
    def update_ui_stats(self):
        curr_s = self.current_playback_time_ms / 1000.0
        self.lbl_progress.setText(f"进度: {self.current_spot_idx} / {len(self.action_stream)} 点 ({curr_s:.1f}s)")

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

# ==========================================
# 启动入口
# ==========================================
def main():
    app = QApplication(sys.argv)
    
    # 强制要求选择 JSON 记录文件
    json_path, _ = QFileDialog.getOpenFileName(None, "请选择要回放的手术记录 (JSON)", "", "JSON Files (*.json)")
    if not json_path: sys.exit()
        
    window = PlaybackSimulatorApp(json_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()