import sys
import time
import threading
import queue
import urllib.parse
import os
import tempfile
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from ftplib import FTP
import tkinter as tk
from tkinter import messagebox, ttk
from ffpyplayer.player import MediaPlayer
from PIL import Image, ImageTk

# Router credentials
FTP_HOST = "192.168.1.1"
FTP_USER = "pepsiSinghCloud"
FTP_PASS = "qazwsx12"  # <-- Put your router password here

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.flac', '.m4a', '.webm'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
PLAYBACK_SPEEDS = {
    "0.5x":  {"vf": "setpts=2.0*PTS", "af": "atempo=0.5"},
    "1.0x":  {},
    "1.25x": {"vf": "setpts=0.8*PTS", "af": "atempo=1.25"},
    "1.5x":  {"vf": "setpts=0.66667*PTS", "af": "atempo=1.5"},
    "2.0x":  {"vf": "setpts=0.5*PTS", "af": "atempo=2.0"},
}

class FTPProxyHandler(BaseHTTPRequestHandler):
    ftp_host = ""
    ftp_user = ""
    ftp_pass = ""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path != '/stream':
            self.send_error(404, "Not Found")
            return
            
        query = urllib.parse.parse_qs(parsed_url.query)
        remote_path = query.get('path', [''])[0]
        if not remote_path:
            self.send_error(400, "Missing path parameter")
            return
            
        remote_path = urllib.parse.unquote(remote_path)
            
        try:
            ftp = FTP(self.ftp_host)
            ftp.login(user=self.ftp_user, passwd=self.ftp_pass)
            ftp.voidcmd('TYPE I') # Switch to binary mode to allow REST seeks
        except Exception as e:
            self.send_error(500, f"FTP Connection failed: {e}")
            return
            
        try:
            try:
                file_size = ftp.size(remote_path)
            except Exception:
                file_size = -1
                
            range_header = self.headers.get('Range')
            start_byte = 0
            end_byte = file_size - 1 if file_size > 0 else -1
            
            if range_header:
                try:
                    range_str = range_header.replace('bytes=', '')
                    parts = range_str.split('-')
                    if parts[0]:
                        start_byte = int(parts[0])
                    if len(parts) > 1 and parts[1]:
                        end_byte = int(parts[1])
                except Exception:
                    pass
            
            if range_header and file_size > 0:
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start_byte}-{end_byte}/{file_size}')
                content_length = end_byte - start_byte + 1
            else:
                self.send_response(200)
                content_length = file_size if file_size > 0 else -1
                
            self.send_header('Content-Type', 'video/mp4')
            if content_length >= 0:
                self.send_header('Content-Length', str(content_length))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            
            if start_byte > 0:
                ftp.sendcmd(f"REST {start_byte}")
                
            class ClientDisconnected(Exception):
                pass
                
            def data_callback(data):
                try:
                    self.wfile.write(data)
                except (socket.error, ConnectionResetError, BrokenPipeError):
                    raise ClientDisconnected()
                    
            try:
                ftp.retrbinary(f"RETR {remote_path}", data_callback, blocksize=65536)
            except ClientDisconnected:
                pass
            except Exception:
                pass
                
        finally:
            try:
                ftp.close()
            except Exception:
                pass

class RouterMediaCenter:
    def __init__(self, root):
        self.root = root
        self.root.title("Nokia Router Media Browser & Player")
        self.root.geometry("1080x680")
        
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

        # Configure modern dark style
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        bg_dark = "#12131c"      # Dark slate background
        bg_side = "#0c0c12"      # Deeper sidebar surface
        fg_white = "#e2e8f0"     # Elegant off-white
        fg_muted = "#94a3b8"     # Sleek gray
        accent_indigo = "#5c54e5"# Vibrant Indigo primary
        accent_hover = "#7069ed" # Accent hover
        border_zinc = "#1f2130"  # Divider line
        
        self.root.config(bg=bg_dark)
        
        # Styles configurations
        self.style.configure("TFrame", background=bg_dark)
        self.style.configure("Sidebar.TFrame", background=bg_side)
        self.style.configure("Toolbar.TFrame", background=bg_side)
        
        self.style.configure("TLabel", background=bg_dark, foreground=fg_white, font=("Segoe UI", 10))
        self.style.configure("Path.TLabel", background=bg_side, foreground=fg_white, font=("Segoe UI", 10, "bold"))
        self.style.configure("BrowserPath.TLabel", background=bg_side, foreground=fg_muted, font=("Consolas", 9))
        
        self.style.configure("TButton", background=border_zinc, foreground=fg_white, borderwidth=0, focuscolor="none", font=("Segoe UI", 9, "bold"))
        self.style.map("TButton", background=[("active", "#2d2e3b"), ("pressed", "#14151c")])
        self.style.configure("Primary.TButton", background=accent_indigo, foreground="#ffffff", borderwidth=0, focuscolor="none", font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", accent_hover), ("pressed", "#4b43c6")])
        
        self.style.configure("Vertical.TScrollbar", troughcolor=bg_side, background=border_zinc, borderwidth=0, arrowsize=10)
        self.style.configure("Horizontal.TScale", troughcolor=border_zinc, background=accent_indigo, borderwidth=0, sliderthickness=12)
        self.style.configure("TPanedwindow", background=bg_dark)
        self.style.configure("TCombobox", fieldbackground="#1e1f29", background=border_zinc, foreground=fg_white, borderwidth=0)
        
        # Style Treeview
        self.style.configure("Treeview", 
                             background=bg_side, 
                             fieldbackground=bg_side, 
                             foreground=fg_white, 
                             borderwidth=0, 
                             font=("Segoe UI", 10), 
                             rowheight=32)
        self.style.map("Treeview", 
                       background=[("selected", accent_indigo)], 
                       foreground=[("selected", "#ffffff")])

        # Top Universal Tool Bar
        self.toolbar = ttk.Frame(root, padding=8, style="Toolbar.TFrame")
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        title_label = ttk.Label(self.toolbar, text="NOKIA ROUTER MEDIA CENTER", font=("Segoe UI", 11, "bold"), background=bg_side, foreground="#ffffff")
        title_label.pack(side=tk.LEFT, padx=(10, 20))

        self.sidebar_btn = ttk.Button(self.toolbar, text="◀ Hide Sidebar", command=self.toggle_sidebar)
        self.sidebar_btn.pack(side=tk.LEFT, padx=5)

        self.fs_btn = ttk.Button(self.toolbar, text="📺 Fullscreen (F11)", command=self.toggle_fullscreen)
        self.fs_btn.pack(side=tk.RIGHT, padx=5)

        # Main Workspace splitter pane
        self.paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # ---- LEFT FRAME: BROWSER ----
        self.browser_frame = ttk.Frame(self.paned_window, style="Sidebar.TFrame")
        self.paned_window.add(self.browser_frame, weight=1)

        self.path_label = ttk.Label(self.browser_frame, text="Path: /", style="BrowserPath.TLabel")
        self.path_label.pack(anchor="w", padx=15, pady=(15, 5))

        list_container = ttk.Frame(self.browser_frame, style="Sidebar.TFrame")
        list_container.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # ttk.Treeview is much more modern and customizable than tk.Listbox
        self.tree = ttk.Treeview(list_container, show="tree", selectmode=tk.BROWSE, style="Treeview")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.column("#0", minwidth=0, width=200, stretch=True)

        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.tree.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(self.browser_frame, style="Sidebar.TFrame")
        btn_frame.pack(fill=tk.X, padx=15, pady=15)
        ttk.Button(btn_frame, text="📁 Up", command=self.go_back, width=8).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="▶ Play", command=self.play_selected, style="Primary.TButton").pack(side=tk.RIGHT)

        # ---- RIGHT FRAME: PLAYER ----
        self.player_frame = ttk.Frame(self.paned_window, padding=10)
        self.paned_window.add(self.player_frame, weight=3)

        # Video Screen Canvas
        self.canvas = tk.Canvas(self.player_frame, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Control Panel (Slider + Buttons)
        self.controls_frame = ttk.Frame(self.player_frame)
        self.controls_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Track Slider Frame
        slider_frame = ttk.Frame(self.controls_frame)
        slider_frame.pack(fill=tk.X, expand=True, side=tk.TOP, pady=5)

        self.slider_var = tk.DoubleVar()
        self.slider = ttk.Scale(slider_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.slider_var, command=self.on_slider_move, style="Horizontal.TScale")
        self.slider.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=(0, 15))
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)

        self.time_label = ttk.Label(slider_frame, text="00:00 / 00:00", font=("Consolas", 10))
        self.time_label.pack(side=tk.RIGHT)

        # Control Panel Actions Card (Centered controls deck)
        actions_card = ttk.Frame(self.controls_frame, padding=10, style="Sidebar.TFrame")
        actions_card.pack(fill=tk.X, side=tk.TOP, pady=5)
        
        controls_center = ttk.Frame(actions_card, style="Sidebar.TFrame")
        controls_center.pack(anchor=tk.CENTER)
        
        self.play_pause_btn = ttk.Button(controls_center, text="▶ Play", width=12, command=self.toggle_play_pause, style="Primary.TButton")
        self.play_pause_btn.pack(side=tk.LEFT, padx=8)
        
        self.stop_btn = ttk.Button(controls_center, text="⏹ Stop", width=10, command=self.stop_video)
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        
        vol_label = ttk.Label(controls_center, text="🔊", font=("Segoe UI", 11), background=bg_side, foreground=fg_white)
        vol_label.pack(side=tk.LEFT, padx=(25, 2))
        
        self.volume_var = tk.DoubleVar(value=70)
        self.volume_scale = ttk.Scale(controls_center, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.volume_var, command=self.on_volume_change, style="Horizontal.TScale", length=90)
        self.volume_scale.pack(side=tk.LEFT, padx=5)
        
        speed_label = ttk.Label(controls_center, text="Speed:", background=bg_side, foreground=fg_muted)
        speed_label.pack(side=tk.LEFT, padx=(25, 5))
        
        self.speed_combo = ttk.Combobox(controls_center, values=["0.5x", "1.0x", "1.25x", "1.5x", "2.0x"], width=6, state="readonly")
        self.speed_combo.set("1.0x")
        self.speed_combo.pack(side=tk.LEFT, padx=5)
        self.speed_combo.bind("<<ComboboxSelected>>", self.on_speed_change)

        # Keyboard Bindings for native adjustments
        self.root.bind("<F11>", lambda event: self.toggle_fullscreen())
        self.root.bind("<Escape>", lambda event: self.exit_fullscreen())

        # Playback Control Flags
        self.is_playing = False
        self.is_paused = False
        self.video_thread = None
        self.cap = None
        self.player = None
        self.seeking = False
        self.queue = queue.Queue(maxsize=2)
        self.canvas_image_id = None
        self.temp_filepath = None
        self.downloading = False
        self.download_thread = None
        self.opened_temp_files = []
        self.current_video_url = None
        self.total_duration_str = "00:00"
        
        # Start local HTTP stream proxy server
        self.start_proxy_server()
 
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
        # Clear Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
            
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
            
            if is_dir:
                display_name = f"📁  {name}"
            else:
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    display_name = f"🖼️  {name}"
                elif ext in VIDEO_EXTENSIONS:
                    display_name = f"🎬  {name}"
                else:
                    display_name = f"📄  {name}"
                    
            self.current_items.append({"name": name, "is_dir": is_dir})
            # Insert into tree view with the index as iid
            self.tree.insert("", "end", iid=str(len(self.current_items) - 1), text=display_name)

    def on_double_click(self, event):
        selection = self.tree.selection()
        if not selection: return
        index = int(selection[0])
        item = self.current_items[index]
        if item["is_dir"]:
            self.ftp.cwd(item["name"])
            self.refresh_list()
        else:
            self.open_media_item(item["name"])

    def go_back(self):
        try:
            self.ftp.cwd("..")
            self.refresh_list()
        except: pass

    def play_selected(self):
        selection = self.tree.selection()
        if selection:
            index = int(selection[0])
            item = self.current_items[index]
            if not item["is_dir"]:
                self.open_media_item(item["name"])

    def start_proxy_server(self):
        # Find a free port dynamically
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        self.proxy_port = sock.getsockname()[1]
        sock.close()
        
        # Set configuration on Handler class
        FTPProxyHandler.ftp_host = FTP_HOST
        FTPProxyHandler.ftp_user = FTP_USER
        FTPProxyHandler.ftp_pass = FTP_PASS
        
        # Start server in thread
        self.httpd = ThreadingHTTPServer(('127.0.0.1', self.proxy_port), FTPProxyHandler)
        self.http_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.http_thread.start()

    def open_media_item(self, filename):
        self.stop_video()
        
        ext = os.path.splitext(filename)[1].lower()
        
        if ext in VIDEO_EXTENSIONS:
            self.start_video_stream(filename)
        elif ext in IMAGE_EXTENSIONS:
            self.display_image_from_ftp(filename)
        else:
            self.open_file_in_system(filename)

    def start_video_stream(self, filename, start_time=0):
        current_dir = self.ftp.pwd()
        full_path = f"{current_dir}/{filename}" if current_dir != "/" else f"/{filename}"
        
        # Stream from our local HTTP proxy!
        quoted_path = urllib.parse.quote(full_path)
        video_url = f"http://127.0.0.1:{self.proxy_port}/stream?path={quoted_path}"
        self.current_video_url = video_url
        
        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
                
        self.is_playing = True
        self.is_paused = False
        self.play_pause_btn.config(text="⏸ Pause")
        
        self.video_thread = threading.Thread(target=self.video_loop, args=(video_url, start_time), daemon=True)
        self.video_thread.start()
        
        self.root.after(15, self.update_gui)

    def display_image_from_ftp(self, filename):
        self.path_label.config(text=f"Loading image: {filename}...")
        
        def download_and_show():
            try:
                download_ftp = FTP(FTP_HOST)
                download_ftp.login(user=FTP_USER, passwd=FTP_PASS)
                download_ftp.cwd(self.ftp.pwd())
                
                suffix = os.path.splitext(filename)[1]
                temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
                
                with os.fdopen(temp_fd, 'wb') as f:
                    download_ftp.retrbinary(f"RETR {filename}", f.write)
                    
                download_ftp.quit()
                self.queue.put(("display_image", temp_path))
            except Exception as e:
                self.queue.put(("error", f"Failed to load image: {e}"))
                
        self.is_playing = True
        threading.Thread(target=download_and_show, daemon=True).start()
        self.root.after(15, self.update_gui)

    def open_file_in_system(self, filename):
        self.path_label.config(text=f"Opening {filename}...")
        
        def download_and_open():
            try:
                download_ftp = FTP(FTP_HOST)
                download_ftp.login(user=FTP_USER, passwd=FTP_PASS)
                download_ftp.cwd(self.ftp.pwd())
                
                suffix = os.path.splitext(filename)[1]
                temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
                
                with os.fdopen(temp_fd, 'wb') as f:
                    download_ftp.retrbinary(f"RETR {filename}", f.write)
                    
                download_ftp.quit()
                
                # Keep reference to clean up on window close
                self.opened_temp_files.append(temp_path)
                
                # Open using default system program
                os.startfile(temp_path)
                
                self.queue.put(("system_open_complete", None))
            except Exception as e:
                self.queue.put(("error", f"Failed to open file: {e}"))
                
        self.is_playing = True
        threading.Thread(target=download_and_open, daemon=True).start()
        self.root.after(15, self.update_gui)

    def update_gui(self):
        if not self.is_playing:
            return
        
        try:
            last_frame = None
            while True:
                msg = self.queue.get_nowait()
                msg_type, data = msg
                
                if msg_type == "setup":
                    duration = data
                    if duration and duration > 0:
                        self.slider.config(to=duration)
                        self.total_duration_str = self.format_time(duration)
                        self.time_label.config(text=f"00:00 / {self.total_duration_str}")
                elif msg_type == "frame":
                    last_frame = data
                elif msg_type == "display_image":
                    temp_path = data
                    pwd = self.ftp.pwd()
                    self.path_label.config(text=f"Path: {pwd}")
                    
                    try:
                        pil_img = Image.open(temp_path)
                        w = self.canvas.winfo_width()
                        h = self.canvas.winfo_height()
                        
                        if w > 10 and h > 10:
                            img_w, img_h = pil_img.size
                            aspect_image = img_w / img_h
                            aspect_canvas = w / h
                            
                            if aspect_image > aspect_canvas:
                                new_w = w
                                new_h = int(w / aspect_image)
                            else:
                                new_h = h
                                new_w = int(h * aspect_image)
                                
                            new_w = max(1, new_w)
                            new_h = max(1, new_h)
                            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
                            
                        imgtk = ImageTk.PhotoImage(image=pil_img)
                        self.canvas.delete("all")
                        self.canvas_image_id = self.canvas.create_image(
                            w // 2, h // 2, 
                            anchor=tk.CENTER, 
                            image=imgtk
                        )
                        self.canvas.image = imgtk
                    except Exception as e:
                        messagebox.showerror("Error", f"Could not display image: {e}")
                    finally:
                        try:
                            os.remove(temp_path)
                        except Exception:
                            pass
                        self.is_playing = False
                        
                elif msg_type == "system_open_complete":
                    pwd = self.ftp.pwd()
                    self.path_label.config(text=f"Path: {pwd}")
                    self.is_playing = False
                    
                elif msg_type == "error":
                    messagebox.showerror("Error", data)
                    self.stop_video()
                    break
                elif msg_type == "stop":
                    self.stop_video()
                    break
                    
                self.queue.task_done()
                
            # If we received any frame message in this tick, draw the most recent one!
            if last_frame is not None:
                img, pts = last_frame
                self.slider_var.set(pts)
                elapsed_str = self.format_time(pts)
                self.time_label.config(text=f"{elapsed_str} / {self.total_duration_str}")
                
                imgtk = ImageTk.PhotoImage(image=img)
                w = self.canvas.winfo_width()
                h = self.canvas.winfo_height()
                
                if w > 10 and h > 10:
                    if self.canvas_image_id is None:
                        self.canvas_image_id = self.canvas.create_image(
                            w // 2, h // 2, 
                            anchor=tk.CENTER, 
                            image=imgtk
                        )
                    else:
                        self.canvas.coords(self.canvas_image_id, w // 2, h // 2)
                        self.canvas.itemconfig(self.canvas_image_id, image=imgtk)
                    self.canvas.image = imgtk
        except queue.Empty:
            pass
            
        if self.is_playing:
            self.root.after(10, self.update_gui)

    def video_loop(self, url, start_time=0):
        # Configure filters based on chosen speed
        speed_key = self.speed_combo.get()
        opts = PLAYBACK_SPEEDS.get(speed_key, {})
        
        self.player = MediaPlayer(url, ff_opts=opts)
        
        start_init = time.time()
        duration = None
        while self.is_playing and duration is None:
            metadata = self.player.get_metadata()
            if metadata:
                duration = metadata.get('duration')
            time.sleep(0.05)
            if time.time() - start_init > 10.0:
                self.queue.put(("error", "Timeout waiting for video stream metadata."))
                self.is_playing = False
                return

        self.queue.put(("setup", duration))
        
        # Set initial volume from the UI slider
        self.player.set_volume(self.volume_var.get() / 100.0)
        
        # Seek if starting from offset (speed changes)
        if start_time > 0:
            self.player.seek(start_time, relative=False)

        while self.is_playing:
            if self.seeking:
                time.sleep(0.05)
                continue
                
            if self.is_paused:
                time.sleep(0.05)
                continue

            frame, val = self.player.get_frame()
            if val == 'eof':
                break
                
            if frame is None:
                time.sleep(0.005)
                continue

            img, pts = frame
            
            # Sync video frame to audio master clock
            master_clock = self.player.get_pts()
            diff = pts - master_clock
            if diff > 0.01:
                # Frame is in the future. Sleep to sync (cap to 100ms max to prevent freeze)
                time.sleep(min(diff, 0.1))
            elif diff < -0.1:
                # Frame is too far in the past. Skip it (drop frame)
                continue

            # Frame parsing and resize is handled on the background thread
            w, h = img.get_size()
            arr = img.to_bytearray()
            
            try:
                pil_img = Image.frombytes("RGB", (w, h), arr[0])
            except Exception:
                continue

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if canvas_w > 10 and canvas_h > 10:
                aspect_video = w / h
                aspect_canvas = canvas_w / canvas_h
                
                if aspect_video > aspect_canvas:
                    new_w = canvas_w
                    new_h = int(canvas_w / aspect_video)
                else:
                    new_h = canvas_h
                    new_w = int(canvas_h * aspect_video)
                
                new_w = max(1, new_w)
                new_h = max(1, new_h)
                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)

            try:
                # Throttled queue insertion
                self.queue.put(("frame", (pil_img, pts)), timeout=0.1)
            except queue.Full:
                pass

            time.sleep(0.002)

        self.player.close_player()
        self.queue.put(("stop", None))

    def on_slider_move(self, value):
        self.seeking = True

    def on_slider_release(self, event):
        if self.is_playing and hasattr(self, 'video_thread') and self.video_thread:
            target_time = self.slider_var.get()
            if hasattr(self, 'player') and self.player:
                self.player.seek(target_time, relative=False)
            
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
        self.seeking = False

    def toggle_play_pause(self):
        if not self.is_playing:
            self.play_selected()
            return
            
        if self.is_paused:
            self.is_paused = False
            if hasattr(self, 'player') and self.player:
                self.player.set_pause(False)
            self.play_pause_btn.config(text="⏸ Pause")
        else:
            self.is_paused = True
            if hasattr(self, 'player') and self.player:
                self.player.set_pause(True)
            self.play_pause_btn.config(text="▶ Play")

    def on_volume_change(self, val):
        volume = float(val) / 100.0
        if hasattr(self, 'player') and self.player:
            self.player.set_volume(volume)

    def on_speed_change(self, event=None):
        if not self.is_playing or not self.current_video_url:
            return
            
        # Get current playback time
        current_time = self.slider_var.get()
        
        # Stop active video thread and player
        self.is_playing = False
        if hasattr(self, 'video_thread') and self.video_thread:
            self.video_thread.join(timeout=1.0)
            self.video_thread = None
            
        if hasattr(self, 'player') and self.player:
            self.player.close_player()
            self.player = None
            
        # Clear frame queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
                
        # Start new stream at offset
        self.is_playing = True
        self.is_paused = False
        self.play_pause_btn.config(text="⏸ Pause")
        
        self.video_thread = threading.Thread(
            target=self.video_loop, 
            args=(self.current_video_url, current_time), 
            daemon=True
        )
        self.video_thread.start()

    def format_time(self, seconds):
        if seconds is None or seconds < 0:
            return "00:00"
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def stop_video(self):
        self.is_playing = False
        self.is_paused = False
        self.play_pause_btn.config(text="▶ Play")
        self.time_label.config(text="00:00 / 00:00")
        self.slider_var.set(0)
        
        if hasattr(self, 'video_thread') and self.video_thread:
            self.video_thread.join(timeout=1.0)
            self.video_thread = None
            
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        
        self.canvas_image_id = None
        self.canvas.delete("all")
        pwd = self.ftp.pwd()
        self.path_label.config(text=f"Path: {pwd}")

    def on_close_window(self):
        self.stop_video()
        
        # Shutdown HTTP stream proxy server
        if hasattr(self, 'httpd') and self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
                
        # Clean up all system-opened temp files
        if hasattr(self, 'opened_temp_files'):
            for path in self.opened_temp_files:
                try:
                    os.remove(path)
                except Exception:
                    pass
                    
        try: self.ftp.quit()
        except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = RouterMediaCenter(root)
    root.mainloop()