import copy
import io
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from PIL import Image, ImageTk

from camera_controller import camera_controller
from camera_state import EXECUTION_MODES, ZOOM_FACTORS, build_camera_configs, normalize_camera_config


FIELD_SPECS = [
    ("width", "Width", int),
    ("height", "Height", int),
    ("framerate", "Framerate", int),
    ("bitrate", "Bitrate", int),
    ("target_ip", "Target IP", str),
    ("target_port", "Target Port", int),
]

SSH_FIELD_SPECS = [
    ("ssh_host", "SSH Host", str),
    ("ssh_port", "SSH Port", int),
    ("ssh_user", "SSH User", str),
    ("ssh_password", "SSH Password", str),
]

ZOOM_OPTIONS = list(ZOOM_FACTORS.keys())


class CameraCard(ttk.LabelFrame):
    def __init__(self, master, app, cam_id, config):
        super().__init__(master, text=f"Camera {cam_id}", padding=14)
        self.app = app
        self.cam_id = cam_id
        self.vars = {}
        self.execution_var = tk.StringVar(value="local")
        self.zoom_var = tk.StringVar(value="1x")
        self.zoom_summary = tk.StringVar(value="")
        self.mirror_var = tk.BooleanVar(value=False)
        self.rotation_var = tk.StringVar(value="0")
        self.sender_state = tk.StringVar(value="Stopped")
        self.receiver_state = tk.StringVar(value="Stopped")
        self._build_layout(config)
        self.sync_from_config(config)

    def _build_layout(self, config):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text=f"Device: {config['device']}").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(self, textvariable=self.sender_state).grid(row=1, column=0, sticky="w")
        ttk.Label(self, textvariable=self.receiver_state).grid(row=1, column=1, sticky="w")

        row = 2
        execution_container = ttk.Frame(self)
        execution_container.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        execution_container.columnconfigure(0, weight=1)
        execution_container.columnconfigure(1, weight=1)
        ttk.Label(execution_container, text="Execution Mode").grid(row=0, column=0, sticky="w")
        execution_select = ttk.Combobox(
            execution_container,
            textvariable=self.execution_var,
            values=list(EXECUTION_MODES),
            state="readonly",
            width=12,
        )
        execution_select.grid(row=1, column=0, sticky="w")
        row += 1

        for index, (field_name, label, _field_type) in enumerate(FIELD_SPECS):
            if index % 2 == 0:
                row += 1
            column = (index % 2) * 2
            container = ttk.Frame(self)
            container.grid(row=row, column=column // 2, sticky="ew", padx=(0, 8) if column == 0 else 0, pady=4)
            container.columnconfigure(0, weight=1)
            ttk.Label(container, text=label).grid(row=0, column=0, sticky="w")
            variable = tk.StringVar()
            self.vars[field_name] = variable
            ttk.Entry(container, textvariable=variable, width=18).grid(row=1, column=0, sticky="ew")

        for index, (field_name, label, _field_type) in enumerate(SSH_FIELD_SPECS):
            if index % 2 == 0:
                row += 1
            column = (index % 2) * 2
            container = ttk.Frame(self)
            container.grid(row=row, column=column // 2, sticky="ew", padx=(0, 8) if column == 0 else 0, pady=4)
            container.columnconfigure(0, weight=1)
            ttk.Label(container, text=label).grid(row=0, column=0, sticky="w")
            variable = tk.StringVar()
            self.vars[field_name] = variable
            show = "*" if field_name == "ssh_password" else None
            ttk.Entry(container, textvariable=variable, width=18, show=show).grid(row=1, column=0, sticky="ew")

        row += 1
        zoom_container = ttk.Frame(self)
        zoom_container.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        zoom_container.columnconfigure(0, weight=1)
        zoom_container.columnconfigure(1, weight=1)
        ttk.Label(zoom_container, text="Zoom").grid(row=0, column=0, sticky="w")
        zoom_select = ttk.Combobox(
            zoom_container,
            textvariable=self.zoom_var,
            values=ZOOM_OPTIONS,
            state="readonly",
            width=12,
        )
        zoom_select.grid(row=1, column=0, sticky="w")
        ttk.Label(zoom_container, textvariable=self.zoom_summary).grid(row=1, column=1, sticky="w", padx=(12, 0))

        row += 1
        mirror_container = ttk.Frame(self)
        mirror_container.grid(row=row, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Checkbutton(
            mirror_container,
            text="Mirror Horizontally",
            variable=self.mirror_var,
            onvalue=True,
            offvalue=False,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(mirror_container, text="Rotation").grid(row=0, column=1, sticky="w", padx=(12, 0))
        rotation_select = ttk.Combobox(
            mirror_container,
            textvariable=self.rotation_var,
            values=["0", "90", "180", "270"],
            state="readonly",
            width=5,
        )
        rotation_select.grid(row=0, column=2, sticky="w")

        button_row = row + 1
        controls = ttk.Frame(self)
        controls.grid(row=button_row, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for column in range(3):
            controls.columnconfigure(column, weight=1)

        ttk.Button(controls, text="Start Sender", command=self.start_sender).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(controls, text="Stop Sender", command=self.stop_sender).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(controls, text="Apply Settings", command=self.apply_changes).grid(row=0, column=2, sticky="ew", padx=(6, 0))

        receiver_controls = ttk.Frame(self)
        receiver_controls.grid(row=button_row + 1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for column in range(3):
            receiver_controls.columnconfigure(column, weight=1)
        ttk.Button(receiver_controls, text="Open Preview", command=self.open_preview).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(receiver_controls, text="Open Receiver", command=self.start_receiver).grid(
            row=0, column=1, sticky="ew", padx=3
        )
        ttk.Button(receiver_controls, text="Close Receiver", command=self.stop_receiver).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

    def _read_form(self):
        updated = copy.deepcopy(self.app.camera_configs[self.cam_id])
        for field_name, label, field_type in FIELD_SPECS:
            raw_value = self.vars[field_name].get().strip()
            if field_type is int:
                try:
                    updated[field_name] = int(raw_value)
                except ValueError as exc:
                    raise ValueError(f"{label} must be an integer") from exc
            else:
                updated[field_name] = raw_value
        for field_name, label, field_type in SSH_FIELD_SPECS:
            raw_value = self.vars[field_name].get().strip()
            if field_type is int:
                try:
                    updated[field_name] = int(raw_value)
                except ValueError as exc:
                    raise ValueError(f"{label} must be an integer") from exc
            else:
                updated[field_name] = raw_value
        updated["execution_mode"] = self.execution_var.get().strip() or "local"
        updated["zoom"] = self.zoom_var.get().strip() or "1x"
        updated["mirror_horizontal"] = self.mirror_var.get()
        try:
            updated["rotation"] = int(self.rotation_var.get().strip() or "0")
        except ValueError:
            updated["rotation"] = 0
        return normalize_camera_config(updated)

    def sync_from_config(self, config):
        for field_name, _label, _field_type in FIELD_SPECS:
            self.vars[field_name].set(str(config[field_name]))
        for field_name, _label, _field_type in SSH_FIELD_SPECS:
            self.vars[field_name].set(str(config[field_name]))
        self.execution_var.set(config.get("execution_mode", "local"))
        self.zoom_var.set(config.get("zoom", "1x"))
        self.mirror_var.set(bool(config.get("mirror_horizontal", False)))
        self.rotation_var.set(str(config.get("rotation", 0)))
        self.zoom_summary.set(
            f"Auto crop L/R {config['crop_left']}/{config['crop_right']} • T/B {config['crop_top']}/{config['crop_bottom']}"
        )
        self._refresh_status_labels(config)

    def _refresh_status_labels(self, config):
        sender_text = "Sender: Running" if config.get("sender_running") else "Sender: Stopped"
        receiver_text = "Receiver: Running" if config.get("receiver_running") else "Receiver: Stopped"
        self.sender_state.set(sender_text)
        self.receiver_state.set(receiver_text)

    def apply_changes(self):
        try:
            updated = self._read_form()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        self.app.camera_configs[self.cam_id].update(updated)
        if self.app.camera_configs[self.cam_id].get("sender_running"):
            camera_controller.start_sender(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.refresh_statuses(message=f"Applied settings for camera {self.cam_id}")

    def start_sender(self):
        try:
            updated = self._read_form()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return
        self.app.camera_configs[self.cam_id].update(updated)
        camera_controller.start_sender(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.refresh_statuses(message=f"Started sender for camera {self.cam_id}")

    def stop_sender(self):
        camera_controller.stop_sender(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.refresh_statuses(message=f"Stopped sender for camera {self.cam_id}")

    def start_receiver(self):
        try:
            updated = self._read_form()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return
        self.app.camera_configs[self.cam_id].update(updated)
        camera_controller.start_receiver(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.refresh_statuses(message=f"Opened receiver for camera {self.cam_id}")

    def stop_receiver(self):
        camera_controller.stop_receiver(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.refresh_statuses(message=f"Closed receiver for camera {self.cam_id}")

    def open_preview(self):
        try:
            updated = self._read_form()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc), parent=self)
            return

        self.app.camera_configs[self.cam_id].update(updated)
        if not self.app.camera_configs[self.cam_id].get("sender_running"):
            camera_controller.start_sender(self.cam_id, self.app.camera_configs[self.cam_id])
        self.app.open_preview(self.cam_id)
        self.app.refresh_statuses(message=f"Opened preview for camera {self.cam_id}")


class PreviewWindow(tk.Toplevel):
    JPEG_START = b"\xff\xd8"
    JPEG_END = b"\xff\xd9"

    def __init__(self, app, cam_id):
        super().__init__(app)
        self.app = app
        self.cam_id = cam_id
        self.config = copy.deepcopy(app.camera_configs[cam_id])
        self.process = None
        self.reader_thread = None
        self.stderr_thread = None
        self.frame_queue = queue.Queue(maxsize=1)
        self.photo = None
        self._closed = False

        self.title(f"Camera {cam_id} Preview")
        self.geometry("980x620")
        self.minsize(720, 480)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.status_text = tk.StringVar(value="Waiting for frames...")
        self._build_ui()
        self._start_pipeline()
        self.after(40, self._drain_frame_queue)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=f"Camera {self.cam_id} UDP Preview",
            font=("TkDefaultFont", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                f"Port {self.config['target_port']} • {self.config['width']}x{self.config['height']} @ "
                f"{self.config['framerate']}fps • Zoom {self.config.get('zoom', '1x')}"
                f" • Mirror {'On' if self.config.get('mirror_horizontal') else 'Off'}"
                f" • Exec {self.config.get('execution_mode', 'local') }"
            ),
        ).grid(row=1, column=0, sticky="w")
        ttk.Button(header, text="Close", command=self.close).grid(row=0, column=1, rowspan=2, sticky="e")

        self.image_label = ttk.Label(
            outer,
            text="Waiting for frames...",
            anchor="center",
            relief="sunken",
        )
        self.image_label.grid(row=1, column=0, sticky="nsew")

        ttk.Label(outer, textvariable=self.status_text).grid(row=2, column=0, sticky="ew", pady=(8, 0))

    def _build_pipeline(self):
        port = self.config["target_port"]
        width, height = self._preview_dimensions()
        framerate = min(15, int(self.config["framerate"]))
        rotation = int(self.config.get("rotation", 0))
        mirror = self.config.get("mirror_horizontal", False)

        rotation_stage = ""
        if rotation == 90:
            rotation_stage = "videoflip video-direction=90r ! "
        elif rotation == 180:
            rotation_stage = "videoflip video-direction=180 ! "
        elif rotation == 270:
            rotation_stage = "videoflip video-direction=90l ! "

        mirror_stage = "videoflip video-direction=horizontal-flip ! " if mirror else ""

        return (
            "gst-launch-1.0 -q "
            f"udpsrc port={port} caps=\"application/x-rtp,media=video,payload=96,encoding-name=H264\" ! "
            "rtpjitterbuffer latency=0 drop-on-latency=true ! "
            "rtph264depay ! avdec_h264 ! videoconvert ! "
            "queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! "
            f"videoscale ! videorate drop-only=true ! video/x-raw,width={width},height={height},framerate={framerate}/1 ! "
            f"{rotation_stage}{mirror_stage}"
            "jpegenc quality=70 ! fdsink fd=1"
        )

    def _preview_dimensions(self):
        width = int(self.config["width"])
        height = int(self.config["height"])
        max_width = 960
        max_height = 540

        scale = min(max_width / width, max_height / height, 1.0)
        preview_width = max(1, int(width * scale))
        preview_height = max(1, int(height * scale))
        return preview_width, preview_height

    def _start_pipeline(self):
        pipeline = self._build_pipeline()
        self.process = subprocess.Popen(
            ["bash", "-lc", pipeline],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self.stderr_thread.start()

    def _reader_loop(self):
        buffer = bytearray()
        while self.process and self.process.stdout and not self._closed:
            chunk = self.process.stdout.read(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                frame = self._extract_jpeg_frame(buffer)
                if frame is None:
                    break
                while not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        break
                self.frame_queue.put(frame)

    def _stderr_loop(self):
        if not self.process or not self.process.stderr:
            return
        for raw_line in iter(self.process.stderr.readline, b""):
            if self._closed:
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                self.after(0, self.status_text.set, line)

    @classmethod
    def _extract_jpeg_frame(cls, buffer):
        start = buffer.find(cls.JPEG_START)
        if start == -1:
            if len(buffer) > len(cls.JPEG_START):
                del buffer[:-len(cls.JPEG_START)]
            return None

        end = buffer.find(cls.JPEG_END, start)
        if end == -1:
            if start > 0:
                del buffer[:start]
            return None

        end += len(cls.JPEG_END)
        frame = bytes(buffer[start:end])
        del buffer[:end]
        return frame

    def _drain_frame_queue(self):
        if self._closed:
            return

        latest_frame = None
        while True:
            try:
                latest_frame = self.frame_queue.get_nowait()
            except queue.Empty:
                break

        if latest_frame is not None:
            image = Image.open(io.BytesIO(latest_frame))
            self.photo = ImageTk.PhotoImage(image)
            self.image_label.configure(image=self.photo, text="")
            self.status_text.set("Streaming")
        elif self.process and self.process.poll() is not None:
            self.status_text.set("Preview pipeline exited")

        self.after(40, self._drain_frame_queue)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
        self.app.unregister_preview(self.cam_id)
        self.destroy()


class VisionDesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vision App Controller")
        self.geometry("1180x780")
        self.minsize(980, 680)
        self.camera_configs = build_camera_configs()
        self.cards = {}
        self.preview_windows = {}
        self.status_text = tk.StringVar(value="Ready")
        self._build_ui()
        self.refresh_statuses(message="Loaded camera configuration")
        self.after(5000, self._poll_statuses)

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Vision App Controller", font=("TkDefaultFont", 18, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, text="Native Python desktop UI for camera sender/receiver control").grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )
        ttk.Button(header, text="Refresh Status", command=self.refresh_statuses).grid(row=0, column=1, rowspan=2, sticky="e")

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        canvas_window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfigure(canvas_window_id, width=event.width)

        content.bind(
            "<Configure>",
            _on_content_configure,
        )
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _scroll_linux_up(_event):
            canvas.yview_scroll(-3, "units")

        def _scroll_linux_down(_event):
            canvas.yview_scroll(3, "units")

        def _scroll_mousewheel(event):
            # Windows / macOS wheel path.
            delta = -1 if event.delta > 0 else 1
            canvas.yview_scroll(delta * 3, "units")

        canvas.bind_all("<MouseWheel>", _scroll_mousewheel)
        canvas.bind_all("<Button-4>", _scroll_linux_up)
        canvas.bind_all("<Button-5>", _scroll_linux_down)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        for column in range(2):
            content.columnconfigure(column, weight=1)

        for index, (cam_id, config) in enumerate(self.camera_configs.items()):
            card = CameraCard(content, self, cam_id, config)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=8, pady=8)
            self.cards[cam_id] = card

        status_bar = ttk.Frame(outer)
        status_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status_text).grid(row=0, column=0, sticky="w")

    def refresh_statuses(self, message=None):
        camera_controller.sync_statuses(self.camera_configs)
        for cam_id, card in self.cards.items():
            card.sync_from_config(self.camera_configs[cam_id])
        self.status_text.set(message or "Statuses refreshed")

    def _poll_statuses(self):
        self.refresh_statuses(message="Statuses refreshed")
        self.after(5000, self._poll_statuses)

    def open_preview(self, cam_id):
        preview = self.preview_windows.get(cam_id)
        if preview is not None and preview.winfo_exists():
            preview.lift()
            preview.focus_force()
            return
        self.preview_windows[cam_id] = PreviewWindow(self, cam_id)

    def unregister_preview(self, cam_id):
        self.preview_windows.pop(cam_id, None)


def main():
    app = VisionDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()