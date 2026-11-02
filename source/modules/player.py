import wx
import os
import sys
import threading
import subprocess
import json
import time
import tempfile
from urllib.parse import urlparse
from modules.settings_manager import get_playback_device, get_seek_time


def _setup_vlc_environment():
    """
    Locates bundled libvlc.dll and plugins directory across dev ('source/dll file')
    and Nuitka standalone build ('main.dist') environments.
    """
    if os.name != 'nt':
        return

    module_dir = os.path.dirname(os.path.abspath(__file__))
    source_root = os.path.abspath(os.path.join(module_dir, ".."))
    cwd = os.path.abspath(os.getcwd())

    candidates = [
        os.path.join(cwd, "dll file"),
        os.path.join(source_root, "dll file"),
        cwd,
        source_root,
        os.path.join(cwd, "vlc lib"),
        os.path.join(source_root, "vlc lib"),
    ]

    for candidate in candidates:
        libvlc_dll = os.path.join(candidate, "libvlc.dll")
        if os.path.exists(libvlc_dll):
            try:
                os.add_dll_directory(candidate)
            except Exception:
                pass
            os.environ["PYTHON_VLC_MODULE_PATH"] = candidate
            plugins_dir = os.path.join(candidate, "plugins")
            if os.path.isdir(plugins_dir):
                os.environ["VLC_PLUGIN_PATH"] = plugins_dir
            break


_setup_vlc_environment()
import vlc


def _get_ytdlp_path():
    """Finds the bundled yt-dlp executable or falls back to system PATH."""
    module_dir = os.path.dirname(os.path.abspath(__file__))
    source_root = os.path.abspath(os.path.join(module_dir, ".."))
    candidates = [
        os.path.join(os.getcwd(), "lib", "yt-dlp.exe"),
        os.path.join(source_root, "lib", "yt-dlp.exe"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "yt-dlp"


def _is_youtube_url(url):
    """Checks whether the URL points to YouTube."""
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        return any(domain in host for domain in ("youtube.com", "youtu.be", "youtube-nocookie.com"))
    except Exception:
        return False


def get_audio_devices():
    """Returns a list of tuples: (device_id, device_description) using VLC."""
    devices = [('default', 'Default Device')]
    inst = None
    mp = None
    try:
        inst = vlc.Instance(["--quiet"])
        mp = inst.media_player_new()
        devs = mp.audio_output_device_enum()
        if devs:
            try:
                dev = devs
                while dev:
                    d = dev.contents
                    dev_id = d.device.decode('utf-8', 'ignore') if d.device else ''
                    dev_desc = d.description.decode('utf-8', 'ignore') if d.description else ''
                    if dev_id:
                        devices.append((dev_id, dev_desc))
                    dev = d.next
            finally:
                vlc.libvlc_audio_output_device_list_release(devs)
    except Exception as e:
        print(f"Error getting audio devices: {e}")
    finally:
        try:
            if mp:
                mp.release()
            if inst:
                inst.release()
        except Exception:
            pass
    return devices


class VLCStreamSource:
    """Represents a prepared media source ready for VLC playback."""
    def __init__(self, primary_mrl, is_local_path=False, audio_slave_url=None, temp_files=None):
        self.primary_mrl = primary_mrl
        self.is_local_path = is_local_path
        self.audio_slave_url = audio_slave_url
        self.temp_files = temp_files or []


_all_temp_files = set()


def _create_hls_master_playlist(video_fmt, audio_fmt):
    """
    Creates a temporary standard HLS Master Playlist (.m3u8) combining
    separate video and audio HLS variant streams for VLC's adaptive demuxer.
    """
    video_url = video_fmt["url"]
    audio_url = audio_fmt["url"]
    tbr = video_fmt.get("tbr") or 1200
    bandwidth = max(256000, int(float(tbr) * 1000))
    width = video_fmt.get("width") or 1280
    height = video_fmt.get("height") or 720
    resolution = f"{width}x{height}"

    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="default",DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"',
        f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={resolution},AUDIO="aud"',
        video_url,
    ]

    fd, temp_path = tempfile.mkstemp(prefix="te_tube_vlc_", suffix=".m3u8")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    _all_temp_files.add(temp_path)
    return temp_path


def _resolve_vlc_source(url, audio_only=False):
    """
    Resolves a URL or file path into a VLCStreamSource.
    - Local files and direct non-YouTube streams are passed straight to VLC.
    - YouTube links use default yt-dlp extraction (no hardcoded player_client or -f b)
      so yt-dlp updates never break playback, feeding native HLS/audio streams to VLC.
    """
    if os.path.exists(url):
        return VLCStreamSource(os.path.abspath(url), is_local_path=True)

    if not _is_youtube_url(url):
        return VLCStreamSource(url, is_local_path=False)

    ytdlp_path = _get_ytdlp_path()

    if audio_only:
        # Prefer HLS m3u8 audio (instant start & zero-lag seeking in VLC), fallback to m4a/bestaudio
        fmt_selector = "bestaudio[protocol*=m3u8]/bestaudio[ext=m4a]/bestaudio/best"
    else:
        # Prefer H.264 (avc1) HLS video + HLS audio for VLC adaptive demuxer, with safe fallbacks
        fmt_selector = (
            "bestvideo[height<=720][vcodec^=avc1][protocol*=m3u8]+bestaudio[protocol*=m3u8]/"
            "best[height<=720][vcodec^=avc1]/"
            "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/"
            "best[height<=720]/best"
        )

    cmd = [
        ytdlp_path,
        "--no-playlist",
        "-j",
        "-f",
        fmt_selector,
        url,
    ]

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    stdout, stderr = process.communicate()

    if process.returncode != 0:
        err_msg = (stderr or "").strip().splitlines()
        short_err = err_msg[-1] if err_msg else "Unknown stream resolution error"
        raise RuntimeError(f"Could not resolve media stream: {short_err}")

    info = None
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            info = json.loads(line)
            break

    if not info:
        raise RuntimeError("No stream metadata returned.")

    if audio_only:
        stream_url = info.get("url")
        if not stream_url and info.get("requested_formats"):
            stream_url = info["requested_formats"][-1].get("url")
        if not stream_url:
            raise RuntimeError("Could not extract audio stream URL for VLC.")
        return VLCStreamSource(stream_url, is_local_path=False)

    reqs = info.get("requested_formats")
    if reqs and len(reqs) >= 2:
        video_fmt, audio_fmt = reqs[0], reqs[1]
        v_proto = (video_fmt.get("protocol") or "").lower()
        a_proto = (audio_fmt.get("protocol") or "").lower()

        if "m3u8" in v_proto and "m3u8" in a_proto:
            m3u8_path = _create_hls_master_playlist(video_fmt, audio_fmt)
            return VLCStreamSource(
                m3u8_path,
                is_local_path=True,
                temp_files=[m3u8_path],
            )
        else:
            return VLCStreamSource(
                video_fmt["url"],
                is_local_path=False,
                audio_slave_url=audio_fmt.get("url"),
            )

    stream_url = info.get("url")
    if not stream_url:
        raise RuntimeError("Could not extract video stream URL for VLC.")
    return VLCStreamSource(stream_url, is_local_path=False)


class VLCPlayerEngine:
    """
    Encapsulates libvlc Instance, MediaPlayer, audio device routing,
    rapid seek accumulation, and temporary playlist cleanup.
    """
    def __init__(self, audio_only=False):
        self.audio_only = audio_only
        self.temp_files = []
        self.media = None
        self._last_seek_target = None
        self._last_seek_ts = 0.0

        vlc_args = [
            "--quiet",
            "--no-video-title-show",
            "--network-caching=1500",
        ]
        if self.audio_only:
            vlc_args.append("--no-video")

        self.instance = vlc.Instance(vlc_args)
        self.media_player = self.instance.media_player_new()
        self.output_device = get_playback_device()
        self._apply_audio_device()

    def _apply_audio_device(self):
        if self.output_device and self.output_device != 'default' and self.media_player:
            try:
                dev_bytes = (
                    self.output_device.encode('utf-8')
                    if isinstance(self.output_device, str)
                    else self.output_device
                )
                self.media_player.audio_output_device_set(None, dev_bytes)
            except Exception as e:
                print(f"Error setting audio output device: {e}")

    def set_window_handle(self, handle):
        if self.audio_only or not self.media_player or not handle:
            return
        if os.name == 'nt':
            self.media_player.set_hwnd(handle)
        elif sys.platform == 'linux':
            self.media_player.set_xwindow(handle)
        elif sys.platform == 'darwin':
            self.media_player.set_nsobject(handle)

    def load_and_play(self, source: VLCStreamSource):
        if source.temp_files:
            self.temp_files.extend(source.temp_files)

        if source.is_local_path:
            media = self.instance.media_new_path(source.primary_mrl)
        else:
            media = self.instance.media_new(source.primary_mrl)

        if source.audio_slave_url:
            try:
                media.slaves_add(vlc.MediaSlaveType.audio, 4, source.audio_slave_url)
            except Exception:
                media.add_option(f":input-slave={source.audio_slave_url}")

        self.media = media
        self.media_player.set_media(media)
        self._apply_audio_device()
        self.media_player.play()
        self._apply_audio_device()

    def is_playing(self):
        return bool(self.media_player and self.media_player.is_playing())

    def play(self):
        if self.media_player:
            self.media_player.play()

    def pause(self):
        if self.media_player:
            self.media_player.pause()

    def get_length(self):
        return self.media_player.get_length() if self.media_player else 0

    def get_time(self):
        if not self.media_player:
            return 0
        # If a seek just occurred within the last 1.5s, return the target time while VLC buffers
        if self._last_seek_target is not None and (time.monotonic() - self._last_seek_ts) < 1.5:
            return self._last_seek_target
        return self.media_player.get_time()

    def set_time(self, time_ms):
        if not self.media_player:
            return 0
        length = self.get_length()
        if length > 0:
            time_ms = max(0, min(length - 500, int(time_ms)))
        else:
            time_ms = max(0, int(time_ms))
        self._last_seek_target = time_ms
        self._last_seek_ts = time.monotonic()
        self.media_player.set_time(time_ms)
        return time_ms

    def seek_relative(self, delta_ms):
        cur = self.get_time()
        if cur < 0:
            cur = 0
        return self.set_time(cur + delta_ms)

    def get_volume(self):
        if not self.media_player:
            return 100
        vol = self.media_player.audio_get_volume()
        return vol if vol >= 0 else 100

    def set_volume(self, volume):
        if not self.media_player:
            return 100
        volume = max(0, min(100, int(volume)))
        self.media_player.audio_set_volume(volume)
        return volume

    def get_mute(self):
        if not self.media_player:
            return False
        return bool(self.media_player.audio_get_mute())

    def set_mute(self, muted):
        if self.media_player:
            self.media_player.audio_set_mute(bool(muted))

    def toggle_mute(self):
        new_state = not self.get_mute()
        self.set_mute(new_state)
        return new_state

    def get_state(self):
        return self.media_player.get_state() if self.media_player else vlc.State.NothingSpecial

    def cleanup(self, fast_exit=False):
        mp = self.media_player
        med = self.media
        inst = self.instance
        temps = list(self.temp_files)

        self.media_player = None
        self.media = None
        self.instance = None
        self.temp_files.clear()

        if fast_exit:
            for path in temps:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            return

        if mp:
            try:
                if not self.audio_only and os.name == 'nt':
                    mp.set_hwnd(0)
            except Exception:
                pass

        def _async_release():
            if mp:
                try:
                    mp.stop()
                except Exception:
                    pass
                try:
                    mp.release()
                except Exception:
                    pass
            if med:
                try:
                    med.release()
                except Exception:
                    pass
            if inst:
                try:
                    inst.release()
                except Exception:
                    pass
            for path in temps:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

        threading.Thread(target=_async_release, daemon=True).start()


class PlayerFrame(wx.Frame):
    def __init__(self, parent, title, audio_only, previous_focus=None):
        mode_prefix = "Playing Audio" if audio_only else "Playing Video"
        frame_size = (640, 280) if audio_only else (800, 600)
        super().__init__(parent, title=f"{mode_prefix}: {title}", size=frame_size)
        self.audio_only = audio_only
        self.video_title = title
        self.previous_focus = previous_focus
        self.seek_ms = get_seek_time() * 1000
        self._error_reported = False
        self._is_closing = False

        # Reuse parent's speaker if available to avoid multiple COM/TTS instances
        self.speaker = getattr(parent, "speaker", None) if parent else None
        if self.speaker is None:
            try:
                from accessible_output2.outputs.auto import Auto
                self.speaker = Auto()
            except Exception as e:
                print(f"TTS Init Error: {e}")

        self.engine = VLCPlayerEngine(audio_only=self.audio_only)

        self.init_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)

        # Timer to update UI
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(500)

    def init_ui(self):
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Video panel (only shown in video mode)
        self.videopanel = wx.Panel(self.panel)
        self.videopanel.SetBackgroundColour(wx.BLACK)

        if self.audio_only:
            self.videopanel.Hide()
        else:
            self.engine.set_window_handle(self.videopanel.GetHandle())
            vbox.Add(self.videopanel, 1, wx.EXPAND | wx.ALL, 0)

        # Controls container
        ctrl_vbox = wx.BoxSizer(wx.VERTICAL)

        # Status display
        self.status_text = wx.StaticText(self.panel, label="Status: Playing")
        self.set_accessible_name(self.status_text, "Status: Playing")
        ctrl_vbox.Add(self.status_text, 0, wx.ALIGN_CENTER | wx.TOP, 8)

        # Time Slider and Labels
        # Keep StaticText label immediately preceding wx.Slider for Win32/MSAA association
        time_hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.time_pos_lbl = wx.StaticText(self.panel, label="&Position:")
        self.time_slider = wx.Slider(self.panel, value=0, minValue=0, maxValue=1000)
        self.curr_time_lbl = wx.StaticText(self.panel, label="00:00")
        self.total_time_lbl = wx.StaticText(self.panel, label="00:00")

        self.time_slider.Bind(wx.EVT_SCROLL, self.on_set_time)

        time_hbox.Add(self.time_pos_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        time_hbox.Add(self.time_slider, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        time_hbox.Add(self.curr_time_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        time_hbox.Add(self.total_time_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        ctrl_vbox.Add(time_hbox, 0, wx.EXPAND | wx.TOP, 10)

        # Playback Buttons and Volume
        btn_hbox = wx.BoxSizer(wx.HORIZONTAL)

        play_hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.play_btn = wx.Button(self.panel, label="&Pause")
        self.play_btn.Bind(wx.EVT_BUTTON, self.on_play_pause)
        play_hbox.Add(self.play_btn, 0, wx.ALL, 5)

        self.mute_btn = wx.Button(self.panel, label="&Mute")
        self.mute_btn.Bind(wx.EVT_BUTTON, self.on_toggle_mute)
        play_hbox.Add(self.mute_btn, 0, wx.ALL, 5)

        vol_hbox = wx.BoxSizer(wx.HORIZONTAL)
        vol_lbl = wx.StaticText(self.panel, label="&Volume:")
        self.vol_slider = wx.Slider(self.panel, value=100, minValue=0, maxValue=100)
        self.vol_slider.Bind(wx.EVT_SCROLL, self.on_set_volume)
        vol_hbox.Add(vol_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)
        vol_hbox.Add(self.vol_slider, 1, wx.EXPAND | wx.ALL, 5)

        btn_hbox.Add(play_hbox, 0, wx.EXPAND)
        btn_hbox.Add(vol_hbox, 1, wx.EXPAND)

        ctrl_vbox.Add(btn_hbox, 0, wx.EXPAND | wx.ALL, 5)

        # Keyboard Control Area
        # Using a Button ensures NVDA stays in Focus Mode so arrow keys control media playback
        kb_instructions = (
            "Keyboard Control Area. Space: Play or Pause, Left and Right arrows: Seek, "
            "Up and Down arrows: Volume, M: Mute or Unmute, T: Speak current time, "
            "Home: Restart from beginning, End: Jump to end, Alt+K: Focus this control area, "
            "Escape: Close player."
        )
        self.kb_area = wx.Button(self.panel, label="Keyboard Control Area")
        self.set_accessible_name(
            self.kb_area,
            kb_instructions,
            description=kb_instructions,
        )
        ctrl_vbox.Add(self.kb_area, 0, wx.EXPAND | wx.ALL, 5)

        vbox.Add(ctrl_vbox, 0, wx.EXPAND | wx.ALL, 5)
        self.panel.SetSizer(vbox)

        # Accessibility names & human-readable slider values
        self.set_accessible_name(self.play_btn, "Pause")
        self.set_accessible_name(self.mute_btn, "Mute")
        self.set_accessible_name(
            self.time_slider,
            "Time position",
            value_callback=self._get_time_slider_accessible_value,
        )
        self.set_accessible_name(
            self.vol_slider,
            "Volume",
            value_callback=self._get_vol_slider_accessible_value,
        )

        # Global keyboard hook for frame-wide media shortcuts
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

    def _get_time_slider_accessible_value(self):
        if not self.engine:
            return "00:00"
        time_ms = max(0, self.engine.get_time())
        length_ms = self.engine.get_length()
        if length_ms > 0:
            return f"{self.format_time(time_ms)} of {self.format_time(length_ms)}"
        return self.format_time(time_ms)

    def _get_vol_slider_accessible_value(self):
        if not self.vol_slider:
            return "100 percent"
        return f"{self.vol_slider.GetValue()} percent"

    def set_accessible_name(self, control, name, description="", value_callback=None):
        control.SetName(name)
        if description:
            try:
                control.SetHelpText(description)
            except Exception:
                pass
        try:
            acc = control.GetAccessible()
            if acc:
                acc.SetName(name)
        except Exception:
            pass

    def play_source(self, source: VLCStreamSource):
        self.engine.load_and_play(source)
        if self.audio_only:
            self.Centre()
        else:
            self.ShowFullScreen(True)
        self.Raise()
        wx.CallAfter(self.kb_area.SetFocus)
        wx.CallAfter(self.update_play_btn_state)

    def on_play_pause(self, event):
        if not self.engine:
            return
        if self.engine.is_playing():
            self.engine.pause()
            self.play_btn.SetLabel("&Play")
            self.set_accessible_name(self.play_btn, "Play")
            self.status_text.SetLabel("Status: Paused")
            self.set_accessible_name(self.status_text, "Status: Paused")
            self.speak_text("Paused")
        else:
            self.engine.play()
            self.play_btn.SetLabel("&Pause")
            self.set_accessible_name(self.play_btn, "Pause")
            self.status_text.SetLabel("Status: Playing")
            self.set_accessible_name(self.status_text, "Status: Playing")
            self.speak_text("Playing")

    def on_toggle_mute(self, event):
        if not self.engine:
            return
        is_muted = self.engine.toggle_mute()
        if is_muted:
            self.mute_btn.SetLabel("&Unmute")
            self.set_accessible_name(self.mute_btn, "Unmute")
            self.speak_text("Muted")
        else:
            self.mute_btn.SetLabel("&Mute")
            self.set_accessible_name(self.mute_btn, "Mute")
            self.speak_text("Unmuted")

    def update_play_btn_state(self):
        if not self.engine:
            return
        if self.engine.is_playing():
            self.play_btn.SetLabel("&Pause")
            self.set_accessible_name(self.play_btn, "Pause")
            self.status_text.SetLabel("Status: Playing")
            self.set_accessible_name(self.status_text, "Status: Playing")
        else:
            self.play_btn.SetLabel("&Play")
            self.set_accessible_name(self.play_btn, "Play")
            self.status_text.SetLabel("Status: Paused")
            self.set_accessible_name(self.status_text, "Status: Paused")

    def on_set_time(self, event):
        if not self.engine:
            return
        val = self.time_slider.GetValue()
        length = self.engine.get_length()
        if length > 0:
            new_time = int(length * (val / 1000.0))
            self.engine.set_time(new_time)
            self.curr_time_lbl.SetLabel(self.format_time(new_time))

    def on_set_volume(self, event):
        if not self.engine:
            return
        val = self.vol_slider.GetValue()
        self.engine.set_volume(val)

    def format_time(self, ms):
        s = max(0, int(ms / 1000))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def on_timer(self, event):
        if self._is_closing or not self.engine or not self.engine.media_player:
            return

        length = self.engine.get_length()
        time_ms = self.engine.get_time()

        if length > 0 and time_ms >= 0:
            pos = max(0, min(1000, int((time_ms / length) * 1000)))
            self.time_slider.SetValue(pos)
            self.curr_time_lbl.SetLabel(self.format_time(time_ms))
            self.total_time_lbl.SetLabel(self.format_time(length))

        state = self.engine.get_state()
        if state == vlc.State.Ended:
            wx.CallAfter(self.Close)
        elif state == vlc.State.Error and not self._error_reported:
            self._error_reported = True
            self.status_text.SetLabel("Status: Playback Error")
            self.set_accessible_name(self.status_text, "Status: Playback Error")
            self.speak_text("Playback error occurred")

    def on_key_down(self, event):
        if self._is_closing or not self.engine:
            event.Skip()
            return

        keycode = event.GetKeyCode()
        focused = self.FindFocus()

        if keycode == ord('K') and event.AltDown():
            self.kb_area.SetFocus()
            self.speak_text("Keyboard control area focused")
        elif keycode == wx.WXK_ESCAPE:
            wx.CallAfter(self.Close)
        elif keycode == wx.WXK_SPACE:
            # Allow Space on Mute button to activate Mute instead of Play/Pause
            if focused == self.mute_btn:
                self.on_toggle_mute(None)
            else:
                self.on_play_pause(None)
        elif keycode == wx.WXK_LEFT:
            if focused == self.vol_slider:
                vol = self.engine.get_volume()
                new_vol = self.engine.set_volume(vol - 5)
                self.vol_slider.SetValue(new_vol)
                self.speak_text(f"Volume {new_vol} percent")
            else:
                new_time = self.engine.seek_relative(-self.seek_ms)
                self._speak_target_time(new_time)
        elif keycode == wx.WXK_RIGHT:
            if focused == self.vol_slider:
                vol = self.engine.get_volume()
                new_vol = self.engine.set_volume(vol + 5)
                self.vol_slider.SetValue(new_vol)
                self.speak_text(f"Volume {new_vol} percent")
            else:
                new_time = self.engine.seek_relative(self.seek_ms)
                self._speak_target_time(new_time)
        elif keycode == wx.WXK_HOME:
            self.engine.set_time(0)
            self.speak_text("Restarted from beginning")
        elif keycode == wx.WXK_END:
            length = self.engine.get_length()
            if length > 0:
                self.engine.set_time(max(0, length - 1000))
                self.speak_text("Jumped to end")
        elif keycode == wx.WXK_UP:
            vol = self.engine.get_volume()
            new_vol = self.engine.set_volume(vol + 5)
            self.vol_slider.SetValue(new_vol)
            self.speak_text(f"Volume {new_vol} percent")
        elif keycode == wx.WXK_DOWN:
            vol = self.engine.get_volume()
            new_vol = self.engine.set_volume(vol - 5)
            self.vol_slider.SetValue(new_vol)
            self.speak_text(f"Volume {new_vol} percent")
        elif keycode in (ord('M'), ord('m')):
            self.on_toggle_mute(None)
        elif keycode in (ord('T'), ord('t')):
            self.speak_current_time()
        else:
            event.Skip()

    def speak_text(self, text):
        if not self.speaker:
            return
        try:
            if hasattr(self.speaker, "output"):
                self.speaker.output(text, interrupt=True)
            elif hasattr(self.speaker, "speak"):
                self.speaker.speak(text)
        except Exception as e:
            print(f"TTS Error: {e}")

    def _format_spoken_time(self, time_ms):
        s = max(0, int(time_ms / 1000))
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)

        parts = []
        if h > 0:
            parts.append(f"{h} hours")
        if m > 0:
            parts.append(f"{m} minutes")
        parts.append(f"{s} seconds")
        return ", ".join(parts) if parts else "0 seconds"

    def speak_current_time(self):
        if not self.engine:
            return
        time_ms = self.engine.get_time()
        length_ms = self.engine.get_length()
        if time_ms >= 0:
            cur_str = self._format_spoken_time(time_ms)
            if length_ms > 0:
                total_str = self._format_spoken_time(length_ms)
                self.speak_text(f"{cur_str} of {total_str}")
            else:
                self.speak_text(cur_str)

    def _speak_target_time(self, time_ms):
        if time_ms >= 0:
            self.speak_text(self._format_spoken_time(time_ms))

    def on_close(self, event):
        global _current_player
        if self._is_closing:
            return
        self._is_closing = True

        if _current_player is self:
            _current_player = None

        if self.timer.IsRunning():
            self.timer.Stop()

        if self.engine:
            self.engine.cleanup()
            self.engine = None

        prev = self.previous_focus
        parent = self.GetParent()

        try:
            if self.IsFullScreen():
                self.ShowFullScreen(False)
            self.Hide()
        except Exception:
            pass

        self.Destroy()

        def _restore_focus_to_main():
            try:
                if parent:
                    if parent.IsIconized():
                        parent.Iconize(False)
                    parent.Show()
                    parent.Raise()
                if prev:
                    try:
                        if isinstance(prev, wx.ListBox) and prev.GetCount() > 0 and prev.GetSelection() == wx.NOT_FOUND:
                            prev.SetSelection(0)
                        prev.SetFocus()
                        return
                    except Exception:
                        pass
                if parent and hasattr(parent, "restore_list_focus"):
                    parent.restore_list_focus()
                elif parent:
                    parent.SetFocus()
            except Exception:
                pass

        wx.CallAfter(_restore_focus_to_main)
        wx.CallLater(40, _restore_focus_to_main)


_current_player = None


def close_current_player(fast_exit=False):
    """Safely closes and cleans up any active PlayerFrame instance."""
    global _current_player
    player_inst = _current_player
    _current_player = None
    if player_inst:
        if fast_exit:
            try:
                if getattr(player_inst, "engine", None):
                    player_inst.engine.cleanup(fast_exit=True)
                    player_inst.engine = None
            except Exception:
                pass
        else:
            try:
                player_inst.Close()
            except Exception:
                pass
    if fast_exit:
        for path in list(_all_temp_files):
            try:
                if os.path.exists(path):
                    os.remove(path)
                _all_temp_files.discard(path)
            except Exception:
                pass


def play_video(url, title="Unknown Video", audio_only=False, on_start_callback=None, previous_focus=None):
    def worker():
        try:
            source = _resolve_vlc_source(url, audio_only=audio_only)
            wx.CallAfter(_on_source_ready, source, title, audio_only, on_start_callback, previous_focus)
        except Exception as e:
            if on_start_callback:
                wx.CallAfter(on_start_callback, error=str(e))

    threading.Thread(target=worker, daemon=True).start()


def _on_source_ready(source, title, audio_only, on_start_callback, previous_focus):
    """
    First signals PlayProgressDialog to close (via on_start_callback) so the modal loop
    exits and PlayProgressDialog is destroyed, then opens PlayerFrame cleanly via CallLater.
    """
    if on_start_callback:
        try:
            on_start_callback()
        except Exception:
            pass
        wx.CallLater(30, _show_player, source, title, audio_only, previous_focus)
    else:
        _show_player(source, title, audio_only, previous_focus)


def _show_player(source, title, audio_only, previous_focus=None):
    global _current_player
    try:
        close_current_player()

        app = wx.GetApp()
        parent_win = app.GetTopWindow() if app else None
        if previous_focus is None and parent_win and hasattr(parent_win, "_get_restore_focus_target"):
            previous_focus = parent_win._get_restore_focus_target()

        _current_player = PlayerFrame(
            parent_win,
            title,
            audio_only,
            previous_focus=previous_focus,
        )
        _current_player.Show()
        _current_player.play_source(source)
    except Exception as e:
        wx.MessageBox(f"Error starting playback: {e}", "Playback Error", wx.OK | wx.ICON_ERROR)
