import wx
import os
import threading
import subprocess
import json
import time
from modules.settings_manager import get_playback_device, get_seek_time

# Add VLC path
vlc_lib_path = os.path.abspath(os.path.join(os.getcwd(), 'vlc lib'))
if os.name == 'nt' and os.path.exists(vlc_lib_path):
    os.add_dll_directory(vlc_lib_path)
    os.environ['PYTHON_VLC_MODULE_PATH'] = vlc_lib_path

import vlc

def get_audio_devices():
    """Returns a list of tuples: (device_id, device_description)"""
    devices = [('default', 'Default Device')]
    try:
        inst = vlc.Instance()
        mp = inst.media_player_new()
        devs = mp.audio_output_device_enum()
        if devs:
            dev = devs
            while dev:
                d = dev.contents
                dev_id = d.device.decode('utf-8', 'ignore')
                dev_desc = d.description.decode('utf-8', 'ignore')
                if dev_id: # Ignore empty device id which is usually default
                    devices.append((dev_id, dev_desc))
                dev = d.next
    except Exception as e:
        print(f"Error getting audio devices: {e}")
    return devices

class PlayerFrame(wx.Frame):
    def __init__(self, parent, title, audio_only):
        super().__init__(parent, title=f"Playing: {title}", size=(800, 600))
        self.audio_only = audio_only
        self.video_title = title
        
        self.instance = vlc.Instance()
        self.media_player = self.instance.media_player_new()
        
        # Set output device if configured
        out_dev = get_playback_device()
        if out_dev and out_dev != 'default':
            self.media_player.audio_output_device_set(None, out_dev.encode('utf-8'))
            
        self.seek_ms = get_seek_time() * 1000
        
        self.init_ui()
        self.Bind(wx.EVT_CLOSE, self.on_close)
        
        # Timer to update UI
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(500)
        
    def init_ui(self):
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Video panel
        self.videopanel = wx.Panel(self.panel)
        self.videopanel.SetBackgroundColour(wx.BLACK)
        
        if os.name == 'nt':
            self.media_player.set_hwnd(self.videopanel.GetHandle())
        elif sys.platform == 'linux':
            self.media_player.set_xwindow(self.videopanel.GetHandle())
        elif sys.platform == 'darwin':
            self.media_player.set_nsobject(self.videopanel.GetHandle())
            
        vbox.Add(self.videopanel, 1, wx.EXPAND | wx.ALL, 0)
        
        # Controls panel
        ctrl_vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Title display (Optional but good for UI)
        self.status_text = wx.StaticText(self.panel, label="Status: Playing")
        self.set_accessible_name(self.status_text, "Status: Playing")
        ctrl_vbox.Add(self.status_text, 0, wx.ALIGN_CENTER | wx.TOP, 5)

        # Time Slider and Labels
        time_hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.curr_time_lbl = wx.StaticText(self.panel, label="00:00")
        self.time_slider = wx.Slider(self.panel, value=0, minValue=0, maxValue=1000)
        self.total_time_lbl = wx.StaticText(self.panel, label="00:00")
        
        self.time_slider.Bind(wx.EVT_SCROLL, self.on_set_time)
        
        time_hbox.Add(self.curr_time_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
        time_hbox.Add(self.time_slider, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        time_hbox.Add(self.total_time_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        ctrl_vbox.Add(time_hbox, 0, wx.EXPAND | wx.TOP, 10)
        
        # Buttons and Volume
        btn_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        # Playback group
        play_hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.play_btn = wx.Button(self.panel, label="Pause")
        self.play_btn.Bind(wx.EVT_BUTTON, self.on_play_pause)
        play_hbox.Add(self.play_btn, 0, wx.ALL, 5)
        
        # Volume group
        vol_hbox = wx.BoxSizer(wx.HORIZONTAL)
        vol_lbl = wx.StaticText(self.panel, label="Volume:")
        self.vol_slider = wx.Slider(self.panel, value=100, minValue=0, maxValue=100)
        self.vol_slider.Bind(wx.EVT_SCROLL, self.on_set_volume)
        vol_hbox.Add(vol_lbl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 15)
        vol_hbox.Add(self.vol_slider, 1, wx.EXPAND | wx.ALL, 5)
        
        btn_hbox.Add(play_hbox, 0, wx.EXPAND)
        btn_hbox.Add(vol_hbox, 1, wx.EXPAND)
        
        ctrl_vbox.Add(btn_hbox, 0, wx.EXPAND | wx.ALL, 5)
        
        # Keyboard Control Area
        # We use a Button so NVDA stays in Focus Mode (not Browse Mode) and does NOT swallow arrow keys for text navigation
        self.kb_area = wx.Button(self.panel, label="Keyboard Control Area")
        self.set_accessible_name(self.kb_area, "Keyboard Control Area. Press Space to play or pause, Arrows for volume and seek.")
        ctrl_vbox.Add(self.kb_area, 0, wx.EXPAND | wx.ALL, 5)
        
        vbox.Add(ctrl_vbox, 0, wx.EXPAND | wx.ALL, 5)
        
        self.panel.SetSizer(vbox)
        
        # Accessibility names
        self.set_accessible_name(self.play_btn, "Pause")
        self.set_accessible_name(self.time_slider, "Time position")
        self.set_accessible_name(self.vol_slider, "Volume")
        
        # Keyboard bindings on panel and frame to catch everything
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
        self.kb_area.Bind(wx.EVT_KEY_DOWN, self.on_key_down)

    def set_accessible_name(self, control, name):
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def play_stream(self, stream_url):
        media = self.instance.media_new(stream_url)
        self.media_player.set_media(media)
        self.media_player.play()
        self.ShowFullScreen(True)
        # Set focus to keyboard area instead of play button
        wx.CallAfter(self.kb_area.SetFocus)
        wx.CallAfter(self.update_play_btn_state)

    def on_play_pause(self, event):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_btn.SetLabel("Play")
            self.set_accessible_name(self.play_btn, "Play")
            self.status_text.SetLabel("Status: Paused")
            self.speak_text("Paused")
        else:
            self.media_player.play()
            self.play_btn.SetLabel("Pause")
            self.set_accessible_name(self.play_btn, "Pause")
            self.status_text.SetLabel("Status: Playing")
            self.speak_text("Playing")

    def update_play_btn_state(self):
        if self.media_player.is_playing():
            self.play_btn.SetLabel("Pause")
            self.set_accessible_name(self.play_btn, "Pause")
            self.status_text.SetLabel("Status: Playing")
        else:
            self.play_btn.SetLabel("Play")
            self.set_accessible_name(self.play_btn, "Play")
            self.status_text.SetLabel("Status: Paused")

    def on_set_time(self, event):
        val = self.time_slider.GetValue()
        length = self.media_player.get_length()
        if length > 0:
            new_time = int(length * (val / 1000.0))
            self.media_player.set_time(new_time)

    def on_set_volume(self, event):
        val = self.vol_slider.GetValue()
        self.media_player.audio_set_volume(val)

    def format_time(self, ms):
        s = int(ms / 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def on_timer(self, event):
        if not self.media_player:
            return
            
        length = self.media_player.get_length()
        time_ms = self.media_player.get_time()
        
        if length > 0 and time_ms >= 0:
            # Update slider
            pos = int((time_ms / length) * 1000)
            self.time_slider.SetValue(pos)
            # Update labels
            self.curr_time_lbl.SetLabel(self.format_time(time_ms))
            self.total_time_lbl.SetLabel(self.format_time(length))
            
        state = self.media_player.get_state()
        if state == vlc.State.Ended:
            self.Close()

    def on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode == ord('K') and event.AltDown():
            self.kb_area.SetFocus()
            self.speak_text("Keyboard control area focused")
        elif keycode == wx.WXK_ESCAPE:
            self.Close()
        elif keycode == wx.WXK_SPACE:
            self.on_play_pause(None)
        elif keycode == wx.WXK_LEFT:
            cur = self.media_player.get_time()
            if cur >= 0:
                new_time = max(0, cur - self.seek_ms)
                self.media_player.set_time(new_time)
                self._speak_target_time(new_time)
        elif keycode == wx.WXK_RIGHT:
            cur = self.media_player.get_time()
            if cur >= 0:
                new_time = cur + self.seek_ms
                self.media_player.set_time(new_time)
                self._speak_target_time(new_time)
        elif keycode == wx.WXK_HOME:
            self.media_player.set_time(0)
            self.speak_text("Restarted from beginning")
        elif keycode == wx.WXK_END:
            length = self.media_player.get_length()
            if length > 0:
                self.media_player.set_time(max(0, length - 1000))
                self.speak_text("Jumped to end")
        elif keycode == wx.WXK_UP:
            vol = self.media_player.audio_get_volume()
            new_vol = min(100, vol + 5)
            self.media_player.audio_set_volume(new_vol)
            self.vol_slider.SetValue(new_vol)
            self.speak_text(f"Volume {new_vol} percent")
        elif keycode == wx.WXK_DOWN:
            vol = self.media_player.audio_get_volume()
            new_vol = max(0, vol - 5)
            self.media_player.audio_set_volume(new_vol)
            self.vol_slider.SetValue(new_vol)
            self.speak_text(f"Volume {new_vol} percent")
        elif keycode == ord('T') or keycode == ord('t'):
            self.speak_current_time()
        else:
            event.Skip()

    def speak_text(self, text):
        def say_text():
            try:
                import accessible_output2.outputs.auto
                speaker = accessible_output2.outputs.auto.Auto()
                speaker.output(text)
            except Exception as e:
                print(f"TTS Error: {e}")
        threading.Thread(target=say_text, daemon=True).start()
            
    def speak_current_time(self):
        time_ms = self.media_player.get_time()
        self._speak_target_time(time_ms)

    def _speak_target_time(self, time_ms):
        if time_ms >= 0:
            s = int(time_ms / 1000)
            m, s = divmod(s, 60)
            h, m = divmod(m, 60)
            
            parts = []
            if h > 0: parts.append(f"{h} hours")
            if m > 0: parts.append(f"{m} minutes")
            parts.append(f"{s} seconds")
            time_str = ", ".join(parts) if parts else "0 seconds"
            self.speak_text(time_str)

    def on_close(self, event):
        self.timer.Stop()
        if self.media_player:
            self.media_player.stop()
            self.media_player.release()
            self.media_player = None
        if self.instance:
            self.instance.release()
            self.instance = None
        self.Destroy()


def _get_stream_url(url, audio_only):
    ytdlp_path = os.path.join(os.getcwd(), "lib", "yt-dlp.exe")
    if not os.path.exists(ytdlp_path):
        ytdlp_path = "yt-dlp"
    
    cmd = [ytdlp_path, "-j", "-f", "bestaudio" if audio_only else "best", url]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    stdout, stderr = process.communicate()
    
    if process.returncode != 0:
        raise Exception(f"yt-dlp error: {stderr}")
        
    info = json.loads(stdout)
    return info.get('url')

_current_player = None

def play_video(url, title="Unknown Video", audio_only=False, on_start_callback=None):
    def worker():
        try:
            stream_url = _get_stream_url(url, audio_only)
            if not stream_url:
                raise Exception("Could not extract stream URL")
            
            wx.CallAfter(_show_player, stream_url, title, audio_only, on_start_callback)
            
        except Exception as e:
            if on_start_callback:
                wx.CallAfter(on_start_callback, error=str(e))
                
    threading.Thread(target=worker, daemon=True).start()

def _show_player(stream_url, title, audio_only, on_start_callback):
    global _current_player
    try:
        if _current_player:
            try:
                _current_player.Close()
            except:
                pass
                
        _current_player = PlayerFrame(None, title, audio_only)
        _current_player.Show()
        _current_player.play_stream(stream_url)
        
        if on_start_callback:
            on_start_callback()
    except Exception as e:
        if on_start_callback:
            on_start_callback(error=str(e))