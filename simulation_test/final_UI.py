import math
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # optional
    HAS_DND = True
except Exception:
    HAS_DND = False
    DND_FILES = None
    TkinterDnD = None

from PIL import Image, ImageTk, ImageDraw, ImageFilter


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def smoothstep(x):
    x = clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


class RetinaLaserSimulator:
    """
    Heuristic simulator for retinal photocoagulation spot placement.

    Important:
    - This is a visual simulation tool, not a medical device.
    - Lens scaling is based on literature-reported spot-size conversion factors.
    - Lesion size / appearance uses tunable engineering heuristics.
    """

    LENS_COEFFS = {
        "Goldmann": 1.08,
        "Krieger": 1.53,
        "Panfundoscope": 1.41,
        "Mainster": 1.05,
    }

    # Simple wavelength absorption / visibility proxy. Tunable.
    # Uses linear interpolation between these anchor points.
    WAVE_POINTS = [
        (450, 0.65),
        (514, 0.95),
        (532, 1.00),
        (561, 0.98),
        (577, 0.95),
        (647, 0.78),
        (810, 0.55),
    ]

    def __init__(self, root):
        self.root = root
        self.root.title("Retinal Laser Spot Simulator")
        self.root.geometry("1500x980")
        self.root.configure(bg="#f2f4f7")

        self.image_original = None
        self.image_display = None
        self.display_scale = 1.0
        self.display_offset = (0, 0)
        self.photo = None
        self.current_image_path = None
        self.fov_center_canvas = (0.0, 0.0)
        self.fov_radius_canvas = 0.0
        self.minimap_popup = None

        self.calibration_points = []
        self.is_calibrating = False
        self.um_per_pixel = None  # original-image pixel scale
        self.lesions = []

        # Session helpers
        self.timer_seconds = 0
        self.timer_running = False
        self.timer_job = None
        self.timer_text_var = tk.StringVar(value="00:00")
        self.spot_count_var = tk.IntVar(value=0)
        self.surgery_ended = False

        # Variables
        self.mode_var = tk.StringVar(value="single")
        self.lens_var = tk.StringVar(value="Goldmann")
        self.wavelength_var = tk.StringVar(value="532")
        self.power_var = tk.DoubleVar(value=180)
        self.duration_var = tk.DoubleVar(value=20)
        self.pulse_mode_var = tk.StringVar(value="single_pulse")
        self.interval_s_var = tk.DoubleVar(value=0.20)
        self.spot_size_um_var = tk.DoubleVar(value=200)
        self.aiming_beam_level_var = tk.DoubleVar(value=50)
        self.titrate_mode_var = tk.BooleanVar(value=False)

        self.shape_var = tk.StringVar(value="square")
        self.shape_param_var = tk.IntVar(value=3)
        self.spacing_x_spot_var = tk.DoubleVar(value=1.0)
        self.rotation_deg_var = tk.DoubleVar(value=0.0)
        self.offset_dx_var = tk.DoubleVar(value=0.0)
        self.offset_dy_var = tk.DoubleVar(value=0.0)

        self.disc_um_var = tk.DoubleVar(value=1500)

        self.build_ui()
        self.bind_events()
        self.update_status()

    def build_ui(self):
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TLabel", background="#f2f4f7", font=("Arial", 11))
        style.configure("Header.TLabel", font=("Arial", 16, "bold"))
        style.configure("Small.TLabel", font=("Arial", 10))
        style.configure("Action.TButton", padding=(12, 6), font=("Arial", 10, "bold"))
        style.configure("Danger.TButton", padding=(12, 6), font=("Arial", 10, "bold"))

        # Left: image
        left = ttk.Frame(outer)
        left.pack(side="left", fill="both", expand=True)

        title = ttk.Label(left, text="Surgical Simulation", style="Header.TLabel")
        title.pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(0, 8))
        ttk.Button(btns, text="Undo Last", command=self.undo_last, style="Action.TButton").pack(side="left", padx=6)
        ttk.Button(btns, text="Clear All", command=self.clear_lesions, style="Action.TButton").pack(side="left", padx=6)
        ttk.Button(btns, text="Start Disc Calibration", command=self.start_calibration, style="Action.TButton").pack(side="left", padx=6)
        ttk.Button(btns, text="Reset Calibration", command=self.reset_calibration, style="Action.TButton").pack(side="left", padx=6)
        ttk.Button(btns, text="Mini-map", command=self.open_minimap_popup, style="Action.TButton").pack(side="left", padx=6)
        ttk.Button(btns, text="End Surgery", command=self.end_surgery, style="Danger.TButton").pack(side="left", padx=6)

        info_bar = ttk.Frame(left)
        info_bar.pack(fill="x", pady=(0, 8))
        ttk.Label(info_bar, text="Timer", style="Small.TLabel").pack(side="left")
        ttk.Label(info_bar, textvariable=self.timer_text_var, style="Header.TLabel").pack(side="left", padx=(6, 14))
        ttk.Separator(info_bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Label(info_bar, text="Spots", style="Small.TLabel").pack(side="left")
        ttk.Label(info_bar, textvariable=self.spot_count_var, style="Header.TLabel").pack(side="left", padx=(6, 0))

        self.hint_label = ttk.Label(
            left,
            text=(
                "Left click: fire current mode pattern | Right click: remove nearest | "
                "Calibration mode: click two optic-disc edge points"
            ),
            style="Small.TLabel"
        )
        self.hint_label.pack(anchor="w", pady=(0, 6))

        self.canvas_frame = tk.Frame(left, bg="#d9dde3", bd=1, relief="solid")
        self.canvas_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.canvas_frame, bg="#101418", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # Right: controls
        right = ttk.Frame(outer, width=420)
        right.pack(side="right", fill="y", padx=(12, 0))
        right.pack_propagate(False)

        ttk.Label(right, text="Control Panel", style="Header.TLabel").pack(anchor="w", pady=(0, 10))

        single_group = ttk.LabelFrame(right, text="Single-Shot Mode")
        single_group.pack(fill="x", pady=(0, 8))
        self.make_labeled_option(single_group, "mode", self.mode_var, ["single", "matrix"], self.on_mode_change)
        self.make_labeled_option(single_group, "wavelength_nm", self.wavelength_var, ["532", "577", "659"], self.on_param_change)
        self.make_labeled_scale(single_group, "power_mw", self.power_var, 50, 800, self.on_param_change)
        self.make_labeled_scale(single_group, "duration_ms", self.duration_var, 10, 500, self.on_param_change)
        self.make_labeled_option(single_group, "pulse_mode", self.pulse_mode_var, ["single_pulse", "repeat"], self.on_param_change)
        self.make_labeled_scale(single_group, "interval_s", self.interval_s_var, 0.05, 1.0, self.on_param_change)
        self.make_labeled_scale(single_group, "spot_size_um", self.spot_size_um_var, 50, 800, self.on_param_change)
        self.make_labeled_option(single_group, "fundus_lens", self.lens_var, list(self.LENS_COEFFS.keys()), self.on_param_change)
        self.make_labeled_scale(single_group, "aiming_beam_level", self.aiming_beam_level_var, 0, 100, self.on_param_change)
        self.make_labeled_check(single_group, "titrate_mode", self.titrate_mode_var, self.on_param_change)

        matrix_group = ttk.LabelFrame(right, text="Matrix Mode")
        matrix_group.pack(fill="x", pady=(0, 8))
        self.matrix_widgets = []
        self.matrix_widgets.extend(self.make_labeled_option(matrix_group, "shape", self.shape_var, ["square", "line", "triangle", "circle", "quarter_circle", "half_circle"], self.on_param_change))
        self.matrix_widgets.extend(self.make_labeled_entry(matrix_group, "shape_param", self.shape_param_var, self.on_param_change))
        self.matrix_widgets.extend(self.make_labeled_scale(matrix_group, "spacing_x_spot", self.spacing_x_spot_var, 0.25, 3.0, self.on_param_change))
        self.matrix_widgets.extend(self.make_labeled_scale(matrix_group, "rotation_deg", self.rotation_deg_var, -180, 180, self.on_param_change))
        self.matrix_widgets.extend(self.make_labeled_entry(matrix_group, "xy_offset_dx", self.offset_dx_var, self.on_param_change))
        self.matrix_widgets.extend(self.make_labeled_entry(matrix_group, "xy_offset_dy", self.offset_dy_var, self.on_param_change))

        calib_group = ttk.LabelFrame(right, text="Calibration")
        calib_group.pack(fill="x", pady=(0, 8))
        self.make_labeled_entry(calib_group, "optic_disc_um", self.disc_um_var, None)

        ttk.Separator(right).pack(fill="x", pady=10)
        self.status_text = tk.Text(right, height=18, wrap="word", font=("Consolas", 10))
        self.status_text.pack(fill="both", expand=True)
        self.on_mode_change()

    def make_labeled_scale(self, parent, label, var, lo, hi, callback):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        ttk.Label(frame, text=label).pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x")
        scale = ttk.Scale(row, variable=var, from_=lo, to=hi, orient="horizontal", command=lambda *_: callback())
        scale.pack(side="left", fill="x", expand=True)
        entry = ttk.Entry(row, textvariable=var, width=8)
        entry.pack(side="left", padx=(8, 0))
        entry.bind("<Return>", lambda e: callback())
        return [scale, entry]

    def make_labeled_entry(self, parent, label, var, callback):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        ttk.Label(frame, text=label).pack(anchor="w")
        entry = ttk.Entry(frame, textvariable=var)
        entry.pack(fill="x")
        if callback:
            entry.bind("<Return>", lambda e: callback())
        return [entry]

    def make_labeled_option(self, parent, label, var, values, callback):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        ttk.Label(frame, text=label).pack(anchor="w")
        cb = ttk.Combobox(frame, textvariable=var, values=values, state="readonly")
        cb.pack(fill="x")
        cb.bind("<<ComboboxSelected>>", lambda e: callback())
        return [cb]

    def make_labeled_check(self, parent, label, var, callback):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)
        chk = ttk.Checkbutton(frame, text=label, variable=var, command=callback)
        chk.pack(anchor="w")
        return [chk]

    def bind_events(self):
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.on_drop)

    def on_drop(self, event):
        data = event.data.strip()
        if data.startswith("{") and data.endswith("}"):
            data = data[1:-1]
        if os.path.isfile(data):
            self.load_image(data)

    def load_image_dialog(self):
        path = filedialog.askopenfilename(
            title="Open fundus image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            img = Image.open(path).convert("RGB")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return

        self.image_original = img
        self.current_image_path = path
        self.lesions.clear()
        self.calibration_points.clear()
        self.is_calibrating = False
        self.um_per_pixel = None
        self.surgery_ended = False
        self.reset_timer()
        self.start_timer()
        self.redraw()
        self.update_status()

    def start_calibration(self):
        if self.image_original is None:
            messagebox.showinfo("No image", "Load an image first.")
            return
        self.is_calibrating = True
        self.calibration_points.clear()
        self.update_status()

    def reset_calibration(self):
        self.calibration_points.clear()
        self.is_calibrating = False
        self.um_per_pixel = None
        self.redraw()
        self.update_status()

    def clear_lesions(self):
        self.lesions.clear()
        self.redraw()
        self.update_status()

    def undo_last(self):
        if self.lesions:
            self.lesions.pop()
            self.redraw()
            self.update_status()

    def on_param_change(self):
        self.redraw()
        if hasattr(self, "status_text"):
            self.update_status()

    def on_mode_change(self, *_):
        is_matrix = self.mode_var.get() == "matrix"
        state = "readonly" if is_matrix else "disabled"
        entry_state = "normal" if is_matrix else "disabled"
        for widget in getattr(self, "matrix_widgets", []):
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=state)
            elif isinstance(widget, ttk.Scale):
                widget.configure(state=entry_state)
            else:
                widget.configure(state=entry_state)
        self.on_param_change()

    def _spot_um_per_pixel(self):
        if self.um_per_pixel is not None:
            return max(self.um_per_pixel, 1e-6)
        return 2.0

    def _build_matrix_points(self, cx, cy):
        shape = self.shape_var.get()
        n = max(1, int(self.shape_param_var.get()))
        spacing_ratio = clamp(float(self.spacing_x_spot_var.get()), 0.25, 3.0)
        spot_um = max(1.0, float(self.spot_size_um_var.get()))
        spacing_px = max(1.0, (spot_um * spacing_ratio) / self._spot_um_per_pixel())
        local_pts = []

        if shape == "square":
            side = max(2, min(5, n))
            half = (side - 1) / 2.0
            for j in range(side):
                for i in range(side):
                    local_pts.append(((i - half) * spacing_px, (j - half) * spacing_px))
        elif shape == "line":
            cnt = max(2, min(15, n))
            half = (cnt - 1) / 2.0
            for i in range(cnt):
                local_pts.append(((i - half) * spacing_px, 0.0))
        elif shape == "triangle":
            rows = max(2, min(15, n))
            for row in range(rows):
                cols = row + 1
                start_x = -0.5 * (cols - 1) * spacing_px
                y = (row - (rows - 1) / 2.0) * spacing_px
                for col in range(cols):
                    local_pts.append((start_x + col * spacing_px, y))
        elif shape == "circle":
            cnt = max(4, n)
            radius = spacing_px
            for i in range(cnt):
                a = 2.0 * math.pi * i / cnt
                local_pts.append((radius * math.cos(a), radius * math.sin(a)))
        elif shape == "quarter_circle":
            cnt = max(2, n)
            radius = spacing_px
            for i in range(cnt):
                a = (math.pi / 2.0) * i / max(1, cnt - 1)
                local_pts.append((radius * math.cos(a), radius * math.sin(a)))
        elif shape == "half_circle":
            cnt = max(2, n)
            radius = spacing_px
            for i in range(cnt):
                a = math.pi * i / max(1, cnt - 1)
                local_pts.append((radius * math.cos(a), radius * math.sin(a)))
        else:
            local_pts.append((0.0, 0.0))

        rot_rad = math.radians(float(self.rotation_deg_var.get()))
        cos_r = math.cos(rot_rad)
        sin_r = math.sin(rot_rad)
        dx = float(self.offset_dx_var.get())
        dy = float(self.offset_dy_var.get())
        out = []
        for lx, ly in local_pts:
            rx = lx * cos_r - ly * sin_r
            ry = lx * sin_r + ly * cos_r
            out.append((cx + rx + dx, cy + ry + dy))
        return out

    def generate_shot_points(self, cx, cy):
        if self.mode_var.get() == "matrix":
            return self._build_matrix_points(cx, cy)
        return [(cx, cy)]

    @staticmethod
    def format_seconds(total_seconds):
        total_seconds = max(0, int(total_seconds))
        mm, ss = divmod(total_seconds, 60)
        hh, mm = divmod(mm, 60)
        if hh > 0:
            return f"{hh:02d}:{mm:02d}:{ss:02d}"
        return f"{mm:02d}:{ss:02d}"

    def _tick_timer(self):
        if not self.timer_running:
            return
        self.timer_seconds += 1
        self.timer_text_var.set(self.format_seconds(self.timer_seconds))
        self.timer_job = self.root.after(1000, self._tick_timer)

    def start_timer(self):
        if self.timer_running:
            return
        self.timer_running = True
        self.timer_job = self.root.after(1000, self._tick_timer)

    def open_minimap_popup(self):
        if self.minimap_popup is not None and self.minimap_popup.winfo_exists():
            self.minimap_popup.deiconify()
            self.minimap_popup.lift()
            self.minimap_popup.focus_force()
            return

        popup = tk.Toplevel(self.root)
        self.minimap_popup = popup
        popup.title("Mini-map")
        popup.configure(bg="#1c2432")
        popup.resizable(False, False)

        w = 360
        h = 390
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + (root_w - w) // 2
        y = root_y + (root_h - h) // 2
        popup.geometry(f"{w}x{h}+{x}+{y}")

        header = tk.Frame(popup, bg="#233049", height=40)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Mini-map", bg="#233049", fg="#e6edf9", font=("Arial", 12, "bold")).pack(side="left", padx=12)
        tk.Button(
            header,
            text="×",
            command=self.close_minimap_popup,
            bg="#233049",
            fg="#e6edf9",
            activebackground="#3a4a6a",
            activeforeground="#ffffff",
            bd=0,
            font=("Arial", 14, "bold"),
            width=3,
        ).pack(side="right", padx=4, pady=2)

        body = tk.Frame(popup, bg="#1c2432")
        body.pack(fill="both", expand=True, padx=14, pady=14)

        mini = tk.Canvas(body, width=300, height=300, bg="#1f2530", highlightthickness=0)
        mini.pack()
        mini.create_rectangle(18, 18, 282, 282, outline="#5d6b82", width=2, dash=(4, 3))
        mini.create_text(150, 138, text="MINI MAP", fill="#b6c3d9", font=("Arial", 16, "bold"))
        mini.create_text(150, 168, text="Reserved", fill="#8b98ad", font=("Arial", 11))

        popup.protocol("WM_DELETE_WINDOW", self.close_minimap_popup)

    def close_minimap_popup(self):
        if self.minimap_popup is not None and self.minimap_popup.winfo_exists():
            self.minimap_popup.destroy()
        self.minimap_popup = None

    def pause_timer(self):
        self.timer_running = False
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

    def reset_timer(self):
        self.pause_timer()
        self.timer_seconds = 0
        self.timer_text_var.set("00:00")

    def end_surgery(self):
        if self.surgery_ended:
            messagebox.showinfo("Surgery", "Surgery has already ended.")
            return
        self.pause_timer()
        self.surgery_ended = True
        messagebox.showinfo(
            "Surgery Summary",
            f"Elapsed time: {self.format_seconds(self.timer_seconds)}\n"
            f"Spot count: {len(self.lesions)}",
        )

    def canvas_to_image(self, x, y):
        if self.image_original is None or self.image_display is None:
            return None
        ox, oy = self.display_offset
        dx = x - ox
        dy = y - oy
        if dx < 0 or dy < 0 or dx >= self.image_display.width or dy >= self.image_display.height:
            return None
        ix = dx / self.display_scale
        iy = dy / self.display_scale
        if ix < 0 or iy < 0 or ix >= self.image_original.width or iy >= self.image_original.height:
            return None
        return ix, iy

    def image_to_canvas(self, ix, iy):
        ox, oy = self.display_offset
        return ox + ix * self.display_scale, oy + iy * self.display_scale

    def on_left_click(self, event):
        if self.image_original is None:
            return
        if self.surgery_ended:
            messagebox.showinfo("Surgery ended", "Load a new image to start a new surgery.")
            return
        pt = self.canvas_to_image(event.x, event.y)
        if pt is None:
            return

        if self.is_calibrating:
            self.calibration_points.append(pt)
            if len(self.calibration_points) == 2:
                self.finish_calibration()
            self.redraw()
            self.update_status()
            return

        points = self.generate_shot_points(pt[0], pt[1])
        for x, y in points:
            if x < 0 or y < 0 or x >= self.image_original.width or y >= self.image_original.height:
                continue
            self.lesions.append(self.build_lesion(x, y))
        self.redraw()
        self.update_status()

    def on_right_click(self, event):
        if not self.lesions or self.image_original is None:
            return
        pt = self.canvas_to_image(event.x, event.y)
        if pt is None:
            return
        x, y = pt
        nearest_i = None
        nearest_d2 = None
        for i, lesion in enumerate(self.lesions):
            dx = lesion["x"] - x
            dy = lesion["y"] - y
            d2 = dx * dx + dy * dy
            if nearest_d2 is None or d2 < nearest_d2:
                nearest_d2 = d2
                nearest_i = i
        if nearest_i is not None:
            self.lesions.pop(nearest_i)
            self.redraw()
            self.update_status()

    def finish_calibration(self):
        if len(self.calibration_points) != 2:
            return
        (x1, y1), (x2, y2) = self.calibration_points
        dist_px = math.hypot(x2 - x1, y2 - y1)
        if dist_px <= 1e-6:
            messagebox.showwarning("Calibration", "The two points are too close.")
            self.calibration_points.clear()
            return
        disc_um = max(1.0, float(self.disc_um_var.get()))
        self.um_per_pixel = disc_um / dist_px
        self.is_calibrating = False
        self.calibration_points.clear()
        self.redraw()
        self.update_status()

    def get_lens_coeff(self):
        name = self.lens_var.get()
        return self.LENS_COEFFS.get(name, 1.0)

    def wavelength_factor(self, nm):
        pts = self.WAVE_POINTS
        nm = float(nm)
        if nm <= pts[0][0]:
            return pts[0][1]
        if nm >= pts[-1][0]:
            return pts[-1][1]
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            if x1 <= nm <= x2:
                t = (nm - x1) / (x2 - x1)
                return y1 + t * (y2 - y1)
        return 1.0

    def compute_metrics(self):
        panel_um = max(1.0, float(self.spot_size_um_var.get()))
        duration_ms = max(0.1, float(self.duration_var.get()))
        power_mw = max(0.1, float(self.power_var.get()))
        wavelength_nm = float(self.wavelength_var.get())
        lens_coeff = self.get_lens_coeff()
        beam_um = panel_um * lens_coeff
        set_radius_um = panel_um / 2.0

        wave_factor = self.wavelength_factor(wavelength_nm)

        # Irradiance-like severity proxy: power * duration / beam^2, wavelength-weighted.
        exposure_proxy = wave_factor * power_mw * duration_ms / max(beam_um * beam_um, 1e-6)
        aiming_factor = 0.80 + 0.40 * clamp(float(self.aiming_beam_level_var.get()) / 100.0, 0.0, 1.0)
        titrate_factor = 0.85 if self.titrate_mode_var.get() else 1.0
        exposure_proxy *= aiming_factor * titrate_factor
        # Tuned for interactive visual feedback, not clinical dosing.
        severity = 1.0 / (1.0 + math.exp(-(exposure_proxy - 0.08) / 0.03))
        severity = clamp(severity, 0.0, 1.0)

        # Fixed lesion diffusion model (UI tuning removed).
        a = 0.15
        b = 70.0
        c = 0.0025
        d = 0.35
        k_min = 0.45
        k_max = 3.81
        k_diff = a + b / max(set_radius_um, 1e-6) + c * duration_ms + d * severity
        k_diff = clamp(k_diff, k_min, k_max)
        lesion_um = beam_um * k_diff

        grade = 1 + 3 * severity
        grade_label = self.grade_label(grade)

        return {
            "panel_um": panel_um,
            "duration_ms": duration_ms,
            "power_mw": power_mw,
            "wavelength_nm": wavelength_nm,
            "mode": self.mode_var.get(),
            "pulse_mode": self.pulse_mode_var.get(),
            "interval_s": float(self.interval_s_var.get()),
            "lens_coeff": lens_coeff,
            "beam_um": beam_um,
            "set_radius_um": set_radius_um,
            "wave_factor": wave_factor,
            "exposure_proxy": exposure_proxy,
            "severity": severity,
            "grade": grade,
            "grade_label": grade_label,
            "k_diff": k_diff,
            "lesion_um": lesion_um,
        }

    @staticmethod
    def grade_label(grade):
        if grade < 1.75:
            return "Grade I"
        if grade < 2.5:
            return "Grade II"
        if grade < 3.25:
            return "Grade III"
        return "Grade IV"

    def lesion_color(self, wavelength_nm, severity):
        # Produces a warm lesion tone with subtle wavelength tint.
        # 532/577 nm -> more yellow-green; longer wavelengths -> more orange/red.
        s = clamp(severity, 0.0, 1.0)
        if wavelength_nm <= 560:
            core = (
                int(230 + 20 * s),
                int(245 - 8 * s),
                int(165 - 60 * s),
                int(95 + 80 * s),
            )
            halo = (
                int(235 + 10 * s),
                int(230 + 5 * s),
                int(200 - 30 * s),
                int(40 + 55 * s),
            )
        elif wavelength_nm <= 620:
            core = (
                int(242 + 10 * s),
                int(230 - 15 * s),
                int(150 - 40 * s),
                int(95 + 75 * s),
            )
            halo = (
                int(240 + 8 * s),
                int(225 - 5 * s),
                int(190 - 20 * s),
                int(35 + 55 * s),
            )
        else:
            core = (
                int(250),
                int(215 - 20 * s),
                int(145 - 25 * s),
                int(85 + 70 * s),
            )
            halo = (
                int(245),
                int(220 - 10 * s),
                int(185 - 10 * s),
                int(30 + 45 * s),
            )
        return core, halo

    def build_lesion(self, x, y):
        m = self.compute_metrics()
        return {
            "x": x,
            "y": y,
            **m,
        }

    def render_overlay_rgba(self):
        if self.image_original is None:
            return None

        base = self.image_original.copy().convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))

        if self.um_per_pixel is None:
            # Show calibration points only.
            composed = Image.alpha_composite(base, overlay)
            return composed

        for lesion in self.lesions:
            core, halo = self.lesion_color(lesion["wavelength_nm"], lesion["severity"])
            lesion_radius_px = max(1.0, (lesion["lesion_um"] / self.um_per_pixel) / 2.0)
            beam_radius_px = max(1.0, (lesion["beam_um"] / self.um_per_pixel) / 2.0)
            patch_radius = int(max(8, lesion_radius_px * 3.5))
            patch = Image.new("RGBA", (patch_radius * 2 + 1, patch_radius * 2 + 1), (0, 0, 0, 0))
            draw = ImageDraw.Draw(patch, "RGBA")
            cx = cy = patch_radius

            # Outer diffuse halo
            outer_r = lesion_radius_px * (0.95 + 0.20 * lesion["severity"])
            draw.ellipse((cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r), fill=halo)

            # Optional pale ring
            ring_alpha = int(20 + 65 * lesion["severity"])
            ring_color = (255, 245, 210, ring_alpha)
            ring_r = lesion_radius_px * (0.65 + 0.10 * lesion["severity"])
            draw.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r), outline=ring_color, width=max(1, int(max(1, lesion_radius_px * 0.08))))

            # Beam/core marker
            inner_r = max(1.0, min(beam_radius_px * 0.55, lesion_radius_px * (0.22 + 0.30 * lesion["severity"])))
            draw.ellipse((cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r), fill=core)

            # Stronger lesions get a bright center
            if lesion["severity"] > 0.62:
                hot_r = max(1.0, inner_r * (0.35 + 0.25 * lesion["severity"]))
                hot = (255, 255, 240, int(60 + 90 * lesion["severity"]))
                draw.ellipse((cx - hot_r, cy - hot_r, cx + hot_r, cy + hot_r), fill=hot)

            blur_px = max(1, int(lesion_radius_px * (0.15 + 0.35 * (1.0 - lesion["severity"]))))
            patch = patch.filter(ImageFilter.GaussianBlur(radius=blur_px))

            left = int(round(lesion["x"] - patch_radius))
            top = int(round(lesion["y"] - patch_radius))
            overlay.alpha_composite(patch, dest=(left, top))

        composed = Image.alpha_composite(base, overlay)
        return composed

    def redraw(self):
        self.canvas.delete("all")
        cw = max(100, self.canvas.winfo_width())
        ch = max(100, self.canvas.winfo_height())
        fov_r = max(30, int(min(cw, ch) * 0.46))
        fov_cx = cw / 2.0
        fov_cy = ch / 2.0
        self.fov_center_canvas = (fov_cx, fov_cy)
        self.fov_radius_canvas = float(fov_r)

        if self.image_original is None:
            self.canvas.create_oval(
                fov_cx - fov_r,
                fov_cy - fov_r,
                fov_cx + fov_r,
                fov_cy + fov_r,
                fill="#03080f",
                outline="#8da2bf",
                width=2,
            )
            self.canvas.create_text(
                fov_cx,
                fov_cy,
                anchor="center",
                fill="#c8d2e0",
                font=("Arial", 18, "bold"),
                text="Microscope FOV",
            )
            return

        composed = self.render_overlay_rgba()
        iw, ih = composed.size
        scale = min((2 * fov_r) / iw, (2 * fov_r) / ih)
        dw, dh = max(1, int(iw * scale)), max(1, int(ih * scale))
        display = composed.resize((dw, dh), Image.LANCZOS)

        self.image_display = display
        self.display_scale = scale
        ox = int(fov_cx - dw / 2)
        oy = int(fov_cy - dh / 2)
        self.display_offset = (ox, oy)

        mask = Image.new("L", (dw, dh), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((0, 0, dw - 1, dh - 1), fill=255)
        circular_display = Image.new("RGBA", (dw, dh), (0, 0, 0, 0))
        circular_display.paste(display.convert("RGBA"), (0, 0), mask)

        self.photo = ImageTk.PhotoImage(circular_display)
        self.canvas.create_image(ox, oy, image=self.photo, anchor="nw")
        self.canvas.create_oval(
            fov_cx - fov_r,
            fov_cy - fov_r,
            fov_cx + fov_r,
            fov_cy + fov_r,
            outline="#8da2bf",
            width=2,
        )

        # Calibration points / scale marks on top.
        for i, pt in enumerate(self.calibration_points):
            cx, cy = self.image_to_canvas(pt[0], pt[1])
            r = 5
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline="#00d4ff", width=2)
            self.canvas.create_text(cx + 10, cy - 10, text=f"C{i+1}", fill="#00d4ff", anchor="nw")
        if len(self.calibration_points) == 2:
            p1 = self.image_to_canvas(*self.calibration_points[0])
            p2 = self.image_to_canvas(*self.calibration_points[1])
            self.canvas.create_line(*p1, *p2, fill="#00d4ff", width=2, dash=(6, 4))

        # Show lesion centers
        for idx, lesion in enumerate(self.lesions, start=1):
            cx, cy = self.image_to_canvas(lesion["x"], lesion["y"])
            r = 2
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#ffffff", outline="")
            if len(self.lesions) <= 50:
                self.canvas.create_text(cx + 6, cy + 6, text=str(idx), fill="#ffffff", anchor="nw", font=("Arial", 8, "bold"))

    def update_status(self):
        self.status_text.delete("1.0", "end")
        metrics = self.compute_metrics()
        self.spot_count_var.set(len(self.lesions))
        lines = []
        lines.append("=== Current parameter set ===")
        lines.append(f"mode             : {metrics['mode']}")
        lines.append(f"pulse_mode       : {metrics['pulse_mode']}")
        lines.append(f"interval_s       : {metrics['interval_s']:.2f}")
        lines.append(f"Lens coeff       : {metrics['lens_coeff']:.3f}")
        lines.append(f"Wavelength (nm)  : {metrics['wavelength_nm']:.1f}")
        lines.append(f"Spot size (µm)   : {metrics['panel_um']:.1f}")
        lines.append(f"Beam on retina   : {metrics['beam_um']:.1f} µm")
        lines.append(f"Duration (ms)    : {metrics['duration_ms']:.1f}")
        lines.append(f"Power (mW)       : {metrics['power_mw']:.1f}")
        lines.append(f"Aiming level     : {self.aiming_beam_level_var.get():.0f}")
        lines.append(f"Titrate mode     : {bool(self.titrate_mode_var.get())}")
        lines.append(f"Wave factor      : {metrics['wave_factor']:.3f}")
        lines.append(f"Exposure proxy   : {metrics['exposure_proxy']:.4f}")
        lines.append(f"Severity         : {metrics['severity']:.3f}")
        lines.append(f"Auto grade       : {metrics['grade']:.2f} ({metrics['grade_label']})")
        lines.append(f"Diffusion k      : {metrics['k_diff']:.3f}")
        lines.append(f"Lesion diameter  : {metrics['lesion_um']:.1f} µm")
        lines.append("")
        lines.append("=== Calibration ===")
        if self.um_per_pixel is None:
            if self.is_calibrating:
                lines.append("Mode             : waiting for 2 optic-disc clicks")
            else:
                lines.append("Scale            : not calibrated")
        else:
            lines.append(f"Scale            : {self.um_per_pixel:.4f} µm / pixel")
            lines.append(f"Scale inverse    : {1.0 / self.um_per_pixel:.4f} pixel / µm")
        lines.append("")
        lines.append("=== Matrix mode ===")
        lines.append(f"shape            : {self.shape_var.get()}")
        lines.append(f"shape_param      : {int(self.shape_param_var.get())}")
        lines.append(f"spacing_x_spot   : {self.spacing_x_spot_var.get():.2f}")
        lines.append(f"rotation_deg     : {self.rotation_deg_var.get():.1f}")
        lines.append(f"xy_offset        : ({self.offset_dx_var.get():.1f}, {self.offset_dy_var.get():.1f})")
        lines.append("")
        lines.append("=== Image / lesions ===")
        if self.current_image_path:
            lines.append(f"Image            : {os.path.basename(self.current_image_path)}")
        lines.append(f"Lesion count     : {len(self.lesions)}")
        if self.lesions and self.um_per_pixel is not None:
            areas = [math.pi * (l['lesion_um'] / 2.0) ** 2 for l in self.lesions]
            lines.append(f"Total area       : {sum(areas):.0f} µm²")
            lines.append(f"Mean diameter    : {sum(l['lesion_um'] for l in self.lesions)/len(self.lesions):.1f} µm")

        self.status_text.insert("1.0", "\n".join(lines))

    def export_overlay(self):
        if self.image_original is None:
            return
        composed = self.render_overlay_rgba()
        if composed is None:
            return
        out = filedialog.asksaveasfilename(
            title="Export overlay",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg;*.jpeg")],
        )
        if not out:
            return
        try:
            if out.lower().endswith((".jpg", ".jpeg")):
                composed.convert("RGB").save(out, quality=95)
            else:
                composed.save(out)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))


def main():
    root_cls = TkinterDnD.Tk if HAS_DND else tk.Tk
    root = root_cls()
    app = RetinaLaserSimulator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
