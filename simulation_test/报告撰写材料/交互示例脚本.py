import sys
import os
import cv2
import numpy as np
import json
import time
import math
from datetime import datetime
from statistics import NormalDist

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, 
                             QVBoxLayout, QLabel, QSlider, QComboBox, 
                             QPushButton, QGroupBox, QFormLayout, QMessageBox,
                             QScrollArea, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QEvent
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QRadialGradient

# =========================================================
# 理论物理模型与校准引擎
# =========================================================

class LaserPhysicalModel:
    def __init__(self, gt_params):
        self.gt_P = gt_params.get("power", 200.0)
        self.gt_S = gt_params.get("spot_size", 200.0)
        self.gt_T = gt_params.get("exposure_time", 100.0)
        self.gt_lam = gt_params.get("wavelength", 532.0)
        
        self.beta_E = 1.2
        self.beta_T = 0.5
        
        # 参数范围与 UI 滑条保持一致
        self.power_range = (50.0, 400.0)
        self.spot_range = (50.0, 400.0)
        self.duration_range = (10.0, 500.0)
        self.wavelengths = (532.0, 577.0, 672.0)

        self.beta_0 = 0.0
        self.tau_0 = 0.0
        self.tau_1 = 0.0
        self.tau_2 = 0.0
        # 病例偏置：只作用于强度公式 z，不作用于分段函数。
        # 默认 0，只有病例显式提供时才做偏移。
        self.beta_0 = float(gt_params.get("z_bias", 0.0))
        # 渲染使用绝对 z 轴锚点，病例偏置会通过 z 直接影响连续渲染
        self.render_z_min = -2.0
        self.render_z_max = 4.5
        self._initialize_thresholds_and_beta_from_normal()

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

    def _initialize_thresholds_and_beta_from_normal(self):
        # 在 raw_z 空间确定四等分阈值（分段函数基线）
        mu, sigma = self._estimate_raw_z_distribution()
        if sigma <= 1e-8:
            raw_tau_0 = mu - 0.1
            raw_tau_1 = mu
            raw_tau_2 = mu + 0.1
        else:
            dist = NormalDist(mu=mu, sigma=sigma)
            raw_tau_0 = dist.inv_cdf(0.25)
            raw_tau_1 = dist.inv_cdf(0.50)
            raw_tau_2 = dist.inv_cdf(0.75)

        # 分段函数固定在原始正态分位上；beta 只作用于强度公式 z
        self.tau_0 = raw_tau_0
        self.tau_1 = raw_tau_1
        self.tau_2 = raw_tau_2

    def _get_lambda_factor(self, wavelength):
        # 经验性的波长修正：黄光略强于绿光，红光相对偏弱
        if wavelength == 532.0:
            return 0.0
        elif wavelength == 577.0:
            return 0.18
        elif wavelength == 672.0:
            return -0.35
        else:
            return 0.0
        
    def _compute_raw_z(self, P, S, T, lam):
        if S <= 0 or P <= 0 or T <= 0: return -999
        energy_term = self.beta_E * math.log((P * T) / (S ** 2))
        density_term = self.beta_T * math.log(P / (S ** 2))
        lam_term = self._get_lambda_factor(lam)
        return energy_term + density_term + lam_term
        
    def compute_z_and_grade(self, P, S, T, lam):
        z = self.beta_0 + self._compute_raw_z(P, S, T, lam)
        if z < self.tau_0: return z, 1 
        elif z < self.tau_1: return z, 2 
        elif z < self.tau_2: return z, 3 
        else: return z, 4 

    def get_render_visibility(self, z):
        if self.render_z_max <= self.render_z_min:
            return 1.0
        vis = (z - self.render_z_min) / (self.render_z_max - self.render_z_min)
        return float(np.clip(vis, 0.0, 1.0))

# =========================================================
# 渲染核心
# =========================================================

def render_laser_spot_v2(img, center_x, center_y, power_mw, duration_ms, spot_size_um, wavelength_nm, pixel_to_um, model: LaserPhysicalModel):
    def smoothstep(edge0, edge1, x):
        if edge1 <= edge0:
            return 1.0 if x >= edge1 else 0.0
        t = (x - edge0) / (edge1 - edge0)
        t = float(np.clip(t, 0.0, 1.0))
        return t * t * (3.0 - 2.0 * t)

    radius_um = spot_size_um / 2.0
    radius_px = max(1.0, radius_um / max(pixel_to_um, 1e-6))

    z_val, grade = model.compute_z_and_grade(power_mw, spot_size_um, duration_ms, wavelength_nm)
    visibility = model.get_render_visibility(z_val)

    p_min, p_max = model.power_range
    t_min, t_max = model.duration_range
    s_min, s_max = model.spot_range
    p_n = float(np.clip((power_mw - p_min) / max(1e-6, p_max - p_min), 0.0, 1.0))
    t_n = float(np.clip((duration_ms - t_min) / max(1e-6, t_max - t_min), 0.0, 1.0))
    s_n = float(np.clip((spot_size_um - s_min) / max(1e-6, s_max - s_min), 0.0, 1.0))

    energy_n = float(np.clip(0.56 * p_n + 0.44 * t_n, 0.0, 1.0))
    effective_radius = radius_px * (0.92 + 0.26 * s_n)

    grid_half = int(max(8, effective_radius * (3.0 + 1.8 * energy_n)))
    h, w, _ = img.shape
    x_min, x_max = max(0, center_x - grid_half), min(w, center_x + grid_half + 1)
    y_min, y_max = max(0, center_y - grid_half), min(h, center_y + grid_half + 1)
    if x_min >= x_max or y_min >= y_max:
        return img, 0

    y_coords, x_coords = np.ogrid[y_min - center_y:y_max - center_y, x_min - center_x:x_max - center_x]
    dist = np.sqrt(x_coords.astype(np.float32) ** 2 + y_coords.astype(np.float32) ** 2)
    r = dist / max(1e-6, effective_radius)

    # ---------------------------------------------------------
    # 核心修改 1：使用 Super-Gaussian 函数塑造更真实的物理轮廓
    # ---------------------------------------------------------
    # r**4 让光斑中心更加平坦，边缘下降更陡峭，消除“棉花球”感
    core_mask = np.exp(-((r / 0.85) ** 4)) 
    # 水肿区依然用平缓的高斯，但限制其范围
    edema_mask = np.exp(-((r / 1.2) ** 2)) - core_mask
    edema_mask = np.clip(edema_mask, 0.0, 1.0)

    # 能量影响强度
    burn_intensity = 0.3 + 0.7 * energy_n
    
    # 提取感兴趣区域 (ROI)
    roi = img[y_min:y_max, x_min:x_max].copy()
    
    # ---------------------------------------------------------
    # 核心修改 2：转入 HSV 色彩空间进行组织变性模拟
    # ---------------------------------------------------------
    roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
    
    # H (色相), S (饱和度), V (明度)
    H, S, V = cv2.split(roi_hsv)

    # 1. 核心灼伤区：强烈的脱色 (降低 S) 和 变白 (提高 V)
    # 能量越高，脱色越严重，明度越接近 255
    core_s_drop = core_mask * burn_intensity * 0.85
    core_v_boost = core_mask * burn_intensity * (255.0 - V) * 0.8
    
    # 2. 周边水肿区：轻微脱色，轻微发灰发亮
    edema_s_drop = edema_mask * burn_intensity * 0.4
    edema_v_boost = edema_mask * burn_intensity * (255.0 - V) * 0.3

    # 应用修改
    S_new = S * (1.0 - np.clip(core_s_drop + edema_s_drop, 0.0, 1.0))
    V_new = V + core_v_boost + edema_v_boost
    
    # 合并并转回 BGR
    roi_hsv_new = cv2.merge([H, np.clip(S_new, 0, 255), np.clip(V_new, 0, 255)]).astype(np.uint8)
    blended_roi = cv2.cvtColor(roi_hsv_new, cv2.COLOR_HSV2BGR).astype(np.float32)

    # ---------------------------------------------------------
    # 核心修改 3：叠加一层微弱的凝固色，并保留底层纹理
    # ---------------------------------------------------------
    # 即使改变了 HSV，直接呈现底图结构有时会显得组织太“干净”。
    # 我们用 Screen (滤色) 混合模式叠加一层灰白，模拟坏死组织的浑浊感
    coagulation_color = np.array([210, 220, 220], dtype=np.float32) # 偏冷的灰白色
    
    # 滤色混合公式: 1 - (1-a)*(1-b)
    roi_norm = blended_roi / 255.0
    color_norm = coagulation_color / 255.0
    
    # 仅在核心区应用浑浊
    opacity = np.expand_dims(core_mask * burn_intensity * 0.6, axis=-1) 
    
    screen_blend = 1.0 - (1.0 - roi_norm) * (1.0 - color_norm * opacity)
    final_roi = screen_blend * 255.0

    # 写入原图
    img[y_min:y_max, x_min:x_max] = np.clip(final_roi, 0.0, 255.0).astype(np.uint8)
    
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

        # 每次击发的短暂闪光（覆盖层，不改底图数据）
        self.flash_pos = None
        self.flash_radius = 0
        self.flash_alpha = 0.0
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(16)
        self.flash_timer.timeout.connect(self._advance_flash)

    def trigger_flash(self, x, y, radius):
        self.flash_pos = (int(x), int(y))
        self.flash_radius = max(8, int(radius))
        self.flash_alpha = 1.0
        if not self.flash_timer.isActive():
            self.flash_timer.start()
        self.update()

    def _advance_flash(self):
        self.flash_alpha -= 0.16
        if self.flash_alpha <= 0.0:
            self.flash_alpha = 0.0
            self.flash_timer.stop()
            self.flash_pos = None
        self.update()

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

    # def wheelEvent(self, event):
    #     delta = event.angleDelta().y()
    #     if delta != 0:
    #         if QApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
    #             self.zoomed.emit(delta)
    #         else:
    #             self.focused.emit(delta)
    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta != 0:
            # 禁用 Ctrl+滚轮数字缩放，强制所有滚轮输入用于 Z 轴焦段调节
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

        # 击发闪光：中心亮白，外围暖白，短时衰减
        if self.flash_pos and self.flash_alpha > 0.0:
            fx, fy = self.flash_pos
            r = self.flash_radius
            outer_alpha = int(140 * self.flash_alpha)
            inner_alpha = int(220 * self.flash_alpha)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 245, 190, outer_alpha))
            painter.drawEllipse(fx - int(r * 1.8), fy - int(r * 1.8), int(r * 3.6), int(r * 3.6))

            painter.setBrush(QColor(255, 255, 245, inner_alpha))
            painter.drawEllipse(fx - r, fy - r, r * 2, r * 2)


class SlitOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.slit_enabled = True
        self.slit_width_ratio = 0.22
        self.slit_margin = 10
        self.slit_feather = 26
        # 0.0 = 最左, 1.0 = 最右；由水平滚动位置驱动
        self.slit_position_ratio = 0.5
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 全治疗窗闪光：高亮红闪，模拟更强烈的视觉刺激
        self.flash_alpha = 0.0
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(16)
        self.flash_timer.timeout.connect(self._advance_flash)

    def trigger_flash(self):
        self.flash_alpha = 1.0
        if not self.flash_timer.isActive():
            self.flash_timer.start()
        self.update()

    def _advance_flash(self):
        self.flash_alpha -= 0.14
        if self.flash_alpha <= 0.0:
            self.flash_alpha = 0.0
            self.flash_timer.stop()
        self.update()

    def _compute_slit_bounds(self):
        w, h = self.width(), self.height()
        slit_w = max(30, int(w * self.slit_width_ratio))
        slit_w = min(slit_w, max(30, w - 2 * self.slit_margin))
        movable_span = max(0, w - 2 * self.slit_margin - slit_w)
        ratio = float(np.clip(self.slit_position_ratio, 0.0, 1.0))
        x1 = self.slit_margin + int(round(movable_span * ratio))
        x2 = min(w - self.slit_margin, x1 + slit_w)
        return x1, x2

    def set_position_ratio(self, ratio):
        self.slit_position_ratio = float(np.clip(ratio, 0.0, 1.0))
        self.update()

    def contains_point(self, x, y):
        x1, x2 = self._compute_slit_bounds()
        return x1 <= x <= x2 and 0 <= y <= self.height()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.slit_enabled or self.width() <= 2 or self.height() <= 2:
            return

        painter = QPainter(self)
        w, h = self.width(), self.height()
        x1, x2 = self._compute_slit_bounds()

        painter.fillRect(0, 0, x1, h, QColor(0, 0, 0, 205))
        painter.fillRect(x2, 0, w - x2, h, QColor(0, 0, 0, 205))

        f = self.slit_feather
        for i in range(f):
            a = int(140 * (1.0 - i / max(1, f)))
            if x1 - i >= 0:
                painter.fillRect(x1 - i, 0, 1, h, QColor(0, 0, 0, a))
            if x2 + i < w:
                painter.fillRect(x2 + i, 0, 1, h, QColor(0, 0, 0, a))

        painter.setPen(QPen(QColor(180, 220, 255, 120), 1, Qt.PenStyle.SolidLine))
        painter.drawRect(x1, self.slit_margin, max(1, x2 - x1), max(1, h - 2 * self.slit_margin))

        # 整个治疗区域红闪：偏红且高亮，尽量形成晃眼感
        if self.flash_alpha > 0.0:
            slit_h = max(1, h - 2 * self.slit_margin)
            slit_w = max(1, x2 - x1)
            a_main = int(220 * self.flash_alpha)
            a_hot = int(245 * self.flash_alpha)

            # 主红闪覆盖整个裂隙窗口
            painter.fillRect(x1, self.slit_margin, slit_w, slit_h, QColor(255, 36, 24, a_main))

            # 中央白热条，增强刺眼感
            hot_w = max(1, int(slit_w * 0.38))
            hot_x = x1 + (slit_w - hot_w) // 2
            painter.fillRect(hot_x, self.slit_margin, hot_w, slit_h, QColor(255, 246, 246, a_hot))

            # 边缘红晕，再叠一层暖红
            painter.fillRect(x1, self.slit_margin, slit_w, slit_h, QColor(255, 70, 40, int(110 * self.flash_alpha)))


class GlobalFlashOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.flash_alpha = 0.0
        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(16)
        self.flash_timer.timeout.connect(self._advance_flash)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def trigger_flash(self):
        self.flash_alpha = 1.0
        if not self.flash_timer.isActive():
            self.flash_timer.start()
        self.update()

    def _advance_flash(self):
        # 指数衰减比线性衰减更接近真实闪光回落
        self.flash_alpha *= 0.78
        if self.flash_alpha <= 0.0:
            self.flash_alpha = 0.0
            self.flash_timer.stop()
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.flash_alpha <= 0.0:
            return

        painter = QPainter(self)
        w, h = self.width(), self.height()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 先全屏轻微提亮，再叠加径向热闪，避免任何矩形/椭圆轮廓
        base_alpha = int(52 * self.flash_alpha)
        painter.fillRect(0, 0, w, h, QColor(255, 247, 238, base_alpha))

        cx, cy = w * 0.5, h * 0.5
        radius = max(w, h) * 0.78
        grad = QRadialGradient(cx, cy, radius)
        grad.setColorAt(0.00, QColor(255, 255, 250, int(170 * self.flash_alpha)))
        grad.setColorAt(0.30, QColor(255, 246, 234, int(110 * self.flash_alpha)))
        grad.setColorAt(0.62, QColor(255, 236, 220, int(42 * self.flash_alpha)))
        grad.setColorAt(1.00, QColor(255, 236, 220, 0))
        painter.fillRect(0, 0, w, h, grad)

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

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        self.init_ui()
        self.load_image(image_path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_slit_overlay_geometry()

    def eventFilter(self, obj, event):
        # 视口尺寸变化时同步裂隙灯遮罩，确保始终铺满右侧观察区
        if hasattr(self, 'scroll_area') and obj == self.scroll_area.viewport() and event.type() == QEvent.Type.Resize:
            self._sync_slit_overlay_geometry()
        return super().eventFilter(obj, event)

    def _sync_slit_overlay_geometry(self):
        if hasattr(self, 'slit_overlay') and self.slit_overlay is not None:
            vp = self.scroll_area.viewport()
            self.slit_overlay.setGeometry(vp.rect())
            self._sync_slit_overlay_position()
            self.slit_overlay.raise_()
        if hasattr(self, 'page_flash_overlay') and self.page_flash_overlay is not None:
            cw = self.centralWidget()
            if cw is not None:
                self.page_flash_overlay.setGeometry(cw.rect())
                self.page_flash_overlay.raise_()

    def _sync_slit_overlay_position(self):
        if not hasattr(self, 'slit_overlay') or self.slit_overlay is None:
            return
        h_bar = self.scroll_area.horizontalScrollBar()
        h_max = h_bar.maximum()
        ratio = (h_bar.value() / h_max) if h_max > 0 else 0.5
        self.slit_overlay.set_position_ratio(ratio)

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
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.image_label = ClickableImageLabel()
        self.image_label.setStyleSheet("background-color: black;")
        
        self.image_label.clicked.connect(self.on_canvas_click)
        self.image_label.calibration_done.connect(self.process_calibration)
        # self.image_label.zoomed.connect(self.handle_zoom) 
        self.image_label.focused.connect(self.handle_focus)
        self.image_label.hovered.connect(self.handle_hover)
        self.image_label.pan_requested.connect(self.handle_pan)
        
        self.scroll_area.setWidget(self.image_label)

        # 固定在视口上的裂隙灯遮罩层：图像滚动时遮罩不跟随移动
        self.slit_overlay = SlitOverlay(self.scroll_area.viewport())
        self.slit_overlay.setGeometry(self.scroll_area.viewport().rect())
        self.slit_overlay.show()
        self.slit_overlay.raise_()
        self.scroll_area.viewport().installEventFilter(self)

        # 全页面闪光层：挂在 centralWidget 顶层，始终覆盖控制区+观察区
        self.page_flash_overlay = GlobalFlashOverlay(self.centralWidget())
        self.page_flash_overlay.setGeometry(self.centralWidget().rect())
        self.page_flash_overlay.show()
        self.page_flash_overlay.raise_()
        
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self.check_focus_state)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.check_focus_state)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(lambda _: self._sync_slit_overlay_position())
        
        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.scroll_area, stretch=1)
        self._sync_slit_overlay_position()

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
        # 1. 计算原始图像的像素-微米比例 (基于视盘 1500 μm 的临床均值)
        # 注意这里不要除以 scale_factor，因为标定是在原图比例下进行的
        self.pixel_to_um = 1500.0 / pixel_distance
        self.lbl_scale.setText(f"已标定: 1 px = {self.pixel_to_um:.2f} μm")

        # 2. 自动计算符合物理视野的缩放比例
        # 设定我们的屏幕观察区宽度，代表真实世界里 6000 μm 的物理跨度
        TARGET_FOV_UM = 6000.0 
        
        # 获取当前显示区(视口)的实际像素宽度
        viewport_width = self.scroll_area.viewport().width()
        
        # 核心公式：自动计算 scale_factor
        self.scale_factor = (viewport_width * self.pixel_to_um) / TARGET_FOV_UM
        
        # 限制一下极值，防止由于标定失误导致程序崩溃
        self.scale_factor = max(0.5, min(self.scale_factor, 15.0))

        # 3. 强制刷新图像，应用新的缩放
        self.check_focus_state(force_update=True)
        self.update_aiming_ring()

        # 4. 自动将视角（滚动条）移动到眼底图像的中心点
        # 使用 QTimer 略微延迟执行，等待 Qt 底层完成放大后的布局重绘
        QTimer.singleShot(50, self._center_camera_view)
        
        QMessageBox.information(self, "标定完成", f"系统已自动将画面缩放至真实裂隙灯物理视野 (约 6.0 mm 跨度)。")

    def _center_camera_view(self):
        # 模拟医生刚坐下时，视野默认对准眼底中心
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(int(h_bar.maximum() / 2))
        v_bar.setValue(int(v_bar.maximum() / 2))
        
    def handle_pan(self, dx, dy):
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        h_bar.setValue(h_bar.value() - dx)
        v_bar.setValue(v_bar.value() - dy)

    def keyPressEvent(self, event):
        key = event.key()
        step = 40

        # 方向键移动裂隙灯窗口（与右键拖拽等效）
        if key == Qt.Key.Key_Left:
            self.handle_pan(step, 0)
            event.accept()
            return
        if key == Qt.Key.Key_Right:
            self.handle_pan(-step, 0)
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            self.handle_pan(0, step)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            self.handle_pan(0, -step)
            event.accept()
            return

        # 键盘调焦：PageUp / PageDown 与滚轮调焦语义一致
        if key == Qt.Key.Key_PageUp:
            self.handle_focus(120)
            event.accept()
            return
        if key == Qt.Key.Key_PageDown:
            self.handle_focus(-120)
            event.accept()
            return

        super().keyPressEvent(event)

    def handle_zoom(self, delta):
        if delta > 0: self.scale_factor *= 1.15 
        else: self.scale_factor /= 1.15 
        self.scale_factor = max(0.2, min(self.scale_factor, 5.0))
        self.check_focus_state(force_update=True)

    def handle_focus(self, delta):
        step = 10.0 if delta > 0 else -10.0
        self.z_offset += step
        self.z_offset = max(-1500.0, min(self.z_offset, 1500.0)) # 扩大焦段范围以适应更强的曲率散焦
        self.lbl_focus.setText(f"<b>系统焦段 (Z): {self.z_offset:.1f}</b><br><b style='color:red'>大幅平移后画面将严重失焦，请滚轮调焦。</b>")
        self.check_focus_state()

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

    def get_optimal_z(self):
        if self.original_image is None: return 0.0
        h_bar = self.scroll_area.horizontalScrollBar()
        v_bar = self.scroll_area.verticalScrollBar()
        viewport = self.scroll_area.viewport()
        vp_x, vp_y = viewport.width() / 2.0, viewport.height() / 2.0
        disp_x = h_bar.value() + vp_x
        disp_y = v_bar.value() + vp_y
        img_x = disp_x / max(self.scale_factor, 1e-6)
        img_y = disp_y / max(self.scale_factor, 1e-6)
        h, w = self.original_image.shape[:2]
        r = math.hypot(img_x - w / 2.0, img_y - h / 2.0)
        # ====================================================
        # 景深模型修改：提高球面曲率对深度 (Z) 的影响
        # 这里的系数从 0.15 提高到 0.45，意味着偏离中心时 Z 值变化更快
        # ====================================================
        return r * 0.45 

    def check_focus_state(self, force_update=False):
        optimal_z = self.get_optimal_z()
        focus_diff = abs(self.z_offset - optimal_z)
        # ====================================================
        # 模糊模型修改：极大增强模糊效果
        # 1. 将敏感度系数从 15.0 降低到 5.0 (越小越敏感，焦斑扩散越快)
        # 2. 将模糊等级上限从 10 提高到 30 (高斯核最大将达到 61x61 像素)
        # ====================================================
        new_blur = int(focus_diff / 5.0) 
        new_blur = min(new_blur, 30) 
        
        if force_update or new_blur != self.current_blur_level:
            self.current_blur_level = new_blur
            self.update_display_blur()

    def on_canvas_click(self, click_x, click_y):
        if self.current_image is None or self.image_label.mode == "calibrate": return

        # 真实裂隙灯语义：仅能在裂隙窗口看到并操作
        if hasattr(self, 'slit_overlay') and self.slit_overlay is not None:
            vp_pos = self.image_label.mapTo(self.scroll_area.viewport(), QPoint(click_x, click_y))
            if not self.slit_overlay.contains_point(vp_pos.x(), vp_pos.y()):
                return

        displayed_pixmap = self.image_label.pixmap()
        if not displayed_pixmap: return
        
        disp_w, disp_h = displayed_pixmap.width(), displayed_pixmap.height()
        lbl_w, lbl_h = self.image_label.width(), self.image_label.height()
        offset_x = max(0, (lbl_w - disp_w) // 2)
        offset_y = max(0, (lbl_h - disp_h) // 2)
        
        rel_x, rel_y = click_x - offset_x, click_y - offset_y
        if rel_x < 0 or rel_x >= disp_w or rel_y < 0 or rel_y >= disp_h: return
            
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

        # 视觉反馈：每次击发让整个治疗区域出现强烈红闪
        # 关闭裂隙窗口局部红闪，避免出现局部矩形伪影
        if hasattr(self, 'page_flash_overlay') and self.page_flash_overlay is not None:
            self.page_flash_overlay.trigger_flash()

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
        if self.current_image is None: return
        
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
    IMAGE_PATH = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\simulation_test\test.png"
    JSON_PATH = r"C:\Users\21333\Documents\GitHub\26Spring_MIP_SurgicalTeachingSys\题目样本.json"
    
    if not os.path.exists(IMAGE_PATH) or not os.path.exists(JSON_PATH):
        print("Error: Required files not found.")
        sys.exit(1)
        
    window = LaserSimulatorApp(IMAGE_PATH, JSON_PATH)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()