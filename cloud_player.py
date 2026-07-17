import sys
import time
import threading
from ftplib import FTP
import tkinter as tk
from tkinter import messagebox, ttk
import cv2
from ffpyplayer.player import MediaPlayer
from PIL import Image, ImageTk

# Router credentials
FTP_HOST = "192.168.1.1"
FTP_USER = "pepsiSinghCloud"
FTP_PASS = "qazwsx12"  # <-- Put your router password here

class RouterMediaCenter:
    def __init__(self, root):
        self.root = root
        self.root.title("Nokia Router Media Browser & Player")
        self.root.geometry("1000x640")
        
        # Connect to Router FTP
        try:
            self.ftp = FTP(FTP_HOST)
            self.ftp.login(user=FTP_USER, passwd=FTP_PASS)
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not connect to router:\n{e}")
            sys.exit()

        # Layout tracking states
        self.sidebar_visible = True
        self.is_fullscreen = False

        # Top Universal Tool Bar (For Panel & Screen Visibility Management)
        self.toolbar = ttk.Frame(root, padding=5)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        self.sidebar_btn = ttk.Button(self.toolbar, text="◀ Hide Sidebar", command=self.toggle_sidebar)
        self.sidebar_btn.pack(side=tk.LEFT, padx=5)

        self.fs_btn = ttk.Button(self.toolbar, text="📺 Fullscreen (F11)", command=self.toggle_fullscreen)
        self.fs_btn.pack(side=tk.RIGHT, padx=5)

        # Main Workspace splitter pane
        self.paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ---- LEFT FRAME: BROWSER ----
        self.browser_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.browser_frame, weight=1)

        self.path_label = ttk.Label(self.browser_frame, text="Path: /", font=("Arial", 9, "bold"))
        self.path_label.pack(anchor="w", padx=5, pady=5)

        self.listbox = tk.Listbox(self.browser_frame, font=("Arial", 10), selectmode=tk.SINGLE)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.listbox.bind("<Double-1>", self.on_double_click)

        btn_frame = ttk.Frame(self.browser_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(btn_frame, text="📁 Up", command=self.go_back, width=8).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="▶ Play", command=self.play_selected).pack(side=tk.RIGHT)

        # ---- RIGHT FRAME: PLAYER ----
        self.player_frame = ttk.Frame(self.paned_window)
        self.paned_window.add(self.player_frame, weight=3)

        # Video Screen Canvas
        self.canvas = tk.Canvas(self.player_frame, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Control Panel (Slider + Buttons)
        self.controls_frame = ttk.Frame(self.player_frame)
        self.controls_frame.pack(fill=tk.X, padx=5, pady=5)

        # Track Slider
        self.slider_var = tk.DoubleVar()
        self.slider = ttk.Scale(self.controls_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.slider_var, command=self.on_slider_move)
        self.slider.pack(fill=tk.X, expand=True, side=tk.TOP, pady=2)
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)

        # Control Panel Actions Row
        actions_frame = ttk.Frame(self.controls_frame)
        actions_frame.pack(fill=tk.X, side=tk.TOP, pady=2)
        self.stop_btn = ttk.Button(actions_frame, text="⏹ Stop Video", command=self.stop_video)
        self.stop_btn.pack(side=tk.TOP)

        # Keyboard Bindings for native adjustments
        self.root.bind("<F11>", lambda event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda event: self.exit_fullscreen())

        # Playback Control Flags
        self.is_playing = False
        self.video_thread = None
        self.cap = None
        self.player = None
        self.seeking = False

        # Load Folder Items
        self.current_items = []
        self.refresh_list()
        
        # Clean Window Intercept
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)

    def toggle_sidebar(self):
        """Collapses or opens the left-hand browser tray panel frame."""
        if self.sidebar_visible:
            self.paned_window.forget(self.browser_frame)
            self.sidebar_btn.config(text="▶ Show Sidebar")
            self.sidebar_visible = False
        else:
            self.paned_window.insert(0, self.browser_frame, weight=1)
            self.sidebar_btn.config(text="◀ Hide Sidebar")
            self.sidebar_visible = True

    def toggle_fullscreen(self):
        """Switches display between windowed desktop structure and total video fill screen."""
        if not self.is_fullscreen:
            # Entering Fullscreen
            if self.sidebar_visible:
                self.toggle_sidebar() # Automatically hide browser out of view
            self.toolbar.pack_forget()
            self.controls_frame.pack_forget()
            self.root.attributes("-fullscreen", True)
            self.fs_btn.config(text="📺 Exit Fullscreen")
            self.is_fullscreen = True
        else:
            self.exit_fullscreen()

    def exit_fullscreen(self):
        """Forces app boundaries back to standard desktop boundaries windowing layout."""
        if self.is_fullscreen:
            self.root.attributes("-fullscreen", False)
            self.toolbar.pack(side=tk.TOP, fill=tk.X)
            self.controls_frame.pack(fill=tk.X, padx=5, pady=5)
            if not self.sidebar_visible:
                self.toggle_sidebar()
            self.fs_btn.config(text="📺 Fullscreen (F11)")
            self.is_fullscreen = False

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        self.current_items = []
        pwd = self.ftp.pwd()
        self.path_label.config(text=f"Path: {pwd}")
        
        lines = []
        self.ftp.retrlines('LIST', lines.append)
        for line in lines:
            parts = line.split(maxsplit=8)
            if len(parts) < 9: continue
            name = parts[8]
            is_dir = line.startswith('d')
            display_name = f"📁 {name}" if is_dir else f"🎬 {name}"
            self.current_items.append({"name": name, "is_dir": is_dir})
            self.listbox.insert(tk.END, display_name)

    def on_double_click(self, event):
        selection = self.listbox.curselection()
        if not selection: return
        item = self.current_items[selection[0]]
        if item["is_dir"]:
            self.ftp.cwd(item["name"])
            self.refresh_list()
        else:
            self.start_video_stream(item["name"])

    def go_back(self):
        try:
            self.ftp.cwd("..")
            self.refresh_list()
        except: pass

    def play_selected(self):
        selection = self.listbox.curselection()
        if selection:
            item = self.current_items[selection[0]]
            if not item["is_dir"]:
                self.start_video_stream(item["name"])

    def start_video_stream(self, filename):
        self.stop_video()
        
        current_dir = self.ftp.pwd().strip("/")
        full_path = f"{current_dir}/{filename}" if current_dir else filename
        video_url = f"ftp://{FTP_USER}:{FTP_PASS}@{FTP_HOST}/{full_path}"
        
        self.is_playing = True
        self.video_thread = threading.Thread(target=self.video_loop, args=(video_url,), daemon=True)
        self.video_thread.start()

    def video_loop(self, url):
        # CV_CAP_FFMPEG flag stabilizes network connection layer parsing blocks
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.player = MediaPlayer(url)
        
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Could not stream video data packet safely over FTP network.")
            self.is_playing = False
            return

        total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0: fps = 24
        frame_delay = 1.0 / fps

        # Set up timeline slider bounds safely
        if total_frames > 0:
            self.slider.config(to=total_frames)

        start_time = time.time()
        frame_count = 0

        while self.is_playing and self.cap.isOpened():
            if self.seeking:
                time.sleep(0.1)
                continue

            try:
                ret, frame = self.cap.read()
                if not ret: 
                    # Network packet buffering dropped briefly, wait and continue instead of failing loop
                    time.sleep(0.05)
                    continue
            except Exception:
                continue

            # Audio frame sync pump
            self.player.get_frame()

            # Update tracking timeline position safely
            current_frame = int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            self.slider_var.set(current_frame)

            # Resize frame dynamically matching canvas screen viewport geometry grid properties
            w = self.canvas.winfo_width()
            h = self.canvas.winfo_height()
            if w > 10 and h > 10:
                frame = cv2.resize(frame, (w, h))

            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
            img = Image.fromarray(cv2image)
            imgtk = ImageTk.PhotoImage(image=img)

            # Draw onto canvas viewport area cleanly
            self.canvas.create_image(0, 0, anchor=tk.NW, image=imgtk)
            self.canvas.image = imgtk

            frame_count += 1
            expected_time = start_time + frame_count * frame_delay
            now = time.time()
            if expected_time > now:
                time.sleep(expected_time - now)

        self.cap.release()
        self.player.close_player()
        self.canvas.delete("all")

    def on_slider_move(self, value):
        self.seeking = True

    def on_slider_release(self, event):
        if self.cap and self.cap.isOpened():
            target_frame = int(self.slider_var.get())
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            if fps > 0:
                self.player.seek(target_frame / fps, relative=False)
        self.seeking = False

    def stop_video(self):
        self.is_playing = False
        if self.video_thread:
            self.video_thread.join(timeout=1.0)

    def on_close_window(self):
        self.stop_video()
        try: self.ftp.quit()
        except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RouterMediaCenter(root)
    root.mainloop()