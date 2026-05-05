## TE_TUBE TECHNICAL ANALYSIS

This document provides a technical overview of the Te_Tube architecture for developers and advanced users.

### CORE FRAMEWORK

- Language: Python 3.x
- GUI Library: wxPython (Classic cross-platform toolkit).
- Playback Engine: mpv via the python-mpv wrapper.
- Data Engine: yt-dlp (Command-line media downloader).

### MODULE BREAKDOWN

## 1. Entry Point (main.py)

Initializes the environment by adding the lib directory to the DLL search path (essential for loading libmpv-2.dll and ffmpeg binaries on Windows). It ensures yt-dlp is available before launching the GUI.

## 2. Graphical User Interface (modules/gui.py)

The TeTubeFrame class manages the main window.

- Accessibility: Implements custom logic to set accessible names for screen readers. It uses wx.EVT_CHAR_HOOK to intercept global key events for specific interactions.
- Threading: Heavy tasks like downloading use threading.Thread to keep the UI responsive.
- Clipboard Monitoring: A wx.Timer checks for YouTube URLs in the clipboard every second using regular expressions.

## 3. Media Player (modules/player.py)

Encapsulates mpv logic.

- Isolation: Each playback instance runs in a daemon thread.
- Configuration: Automatically enables ytdl support and default keyboard bindings. Supports a dedicated Audio-Only mode which hides the video track but keeps the window for controls.

## 4. Search and Download (modules/search_engine.py and downloader.py)

- Search: Executes yt-dlp with --dump-json to retrieve structured search results without downloading.
- Download: Wraps subprocess.Popen to capture and parse progress strings from yt-dlp's standard output, providing real-time feedback to the UI via custom events.

## 5. Management (modules/ytdlp_manager.py and app_updater.py)

- yt-dlp Management: Handles the initial download and self-updating of the yt-dlp.exe binary.
- App Updates: Compares the local version against a remote version.txt on GitHub. If an update is found, it triggers updater.bat.

### DATA STORAGE

- favorites.json: Stores user-bookmarked videos.
- watch_history.json: Stores a history of the last 100 watched videos.
Files are stored in JSON format for easy reading and writing while maintaining portability.

###EXTERNAL BINARIES (lib folder)
The application relies on several compiled binaries:

- yt-dlp.exe: Core logic for YouTube interaction.
- ffmpeg.exe and ffprobe.exe: Required for media conversion and muxing.
- libmpv-2.dll: High-performance video and audio rendering.