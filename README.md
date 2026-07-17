# Router Network Media Player

A lightweight, multi-threaded Python desktop application designed to stream video, view images, and open documents directly from storage attached to a network router over FTP.

Developed specifically for routers (e.g., Nokia router models) with connection constraints and protocols that only support FTP.

## Features

- **No-Buffer Instant Streaming**: Streams video files instantly using an integrated, local multi-threaded HTTP range proxy. No waiting for the whole file to download.
- **Audio-Video Synchronization**: Synchronizes video frames in real-time with the audio track master clock to prevent accelerated playback or latency drift.
- **Dynamic Speed Controls**: Adjust playback speed dynamically (`0.5x`, `1.0x`, `1.25x`, `1.5x`, `2.0x`) with audio-video filters matching in lock-step.
- **Integrated Image Viewer**: Automatically downloads and renders images (`.jpg`, `.png`, `.gif`, `.webp`) scaled to fit the view canvas.
- **Native Document Opener**: Integrates with Windows OS default handlers to launch documents (PDF, TXT, office documents) using `os.startfile`, automatically cleaning up temporary files.
- **Premium Dark UI**: Built with a sleek dark-slate modern interface featuring a vertical scrollable directories explorer (`ttk.Treeview`) and unified toolbar/card decks.

## Prerequisites

Ensure you have python (3.9+) and standard packages installed. The media framework relies on `ffpyplayer` which acts as a wrapper around FFmpeg and SDL.

## Setup Instructions

1. **Clone or copy** the files to your local workspace directory.
2. Create and activate a python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

## Configuration

Open `cloud_player.py` and modify the credentials section at the top of the file to match your router configuration:
```python
# Router credentials
FTP_HOST = "192.168.1.1"
FTP_USER = "pepsiSinghCloud"
FTP_PASS = "YOUR_ROUTER_PASSWORD"
```

## Running the Application

Launch the player using:
```powershell
python cloud_player.py
```
- **F11**: Toggle fullscreen player.
- **Escape**: Exit fullscreen player.
- Use the **Up** button to navigate directories and double-click folders or items to open.
