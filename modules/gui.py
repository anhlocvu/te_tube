import wx
import os
import threading
import re
import wx.lib.newevent
from modules.search_engine import search_youtube
from modules.player import play_video
from modules.app_updater import get_latest_version, run_updater
from modules.downloader import DOWNLOAD_DIR
version="1.0"
# Define a custom event for progress updates using the modern way
DownloadEvent, EVT_DOWNLOAD_UPDATE = wx.lib.newevent.NewEvent()

class TeTubeFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Te_Tube, version: "+version, size=(800, 600))
        
        self.results = []
        self.last_clipboard_text = ""
        self.init_ui()
        self.Centre()
        
        # Use CHAR_HOOK for global hotkeys like Enter
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

        # Clipboard monitor timer
        self.clipboard_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_check_clipboard, self.clipboard_timer)
        self.clipboard_timer.Start(1000) # Check every 1 second
        
        # Check for app updates
        wx.CallAfter(self.check_for_app_updates)

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def check_for_app_updates(self):
        """Checks for application updates and prompts the user."""
        latest = get_latest_version()
        if latest and latest != version:
            msg = f"A new version is available!\n\nCurrent version: {version}\nLatest version: {latest}\n\nDo you want to update now?"
            dlg = wx.MessageDialog(self, msg, "Software Update", wx.YES_NO | wx.ICON_INFORMATION)
            if dlg.ShowModal() == wx.ID_YES:
                if run_updater():
                    self.Close()
                else:
                    wx.MessageBox("Failed to launch updater.bat. please make sure it exists in the app folder.", "Error", wx.OK | wx.ICON_ERROR)
            dlg.Destroy()

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Tab control
        self.notebook = wx.Notebook(panel)
        self.search_tab = wx.Panel(self.notebook)
        self.process_link_tab = wx.Panel(self.notebook)
        
        self.notebook.AddPage(self.search_tab, "Search")
        self.notebook.AddPage(self.process_link_tab, "Process via link")

        self.setup_search_tab()
        self.setup_process_link_tab()

        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(vbox)

        # Menu bar
        self.setup_menu_bar()

    def setup_menu_bar(self):
        menubar = wx.MenuBar()
        
        # Main Menu
        main_menu = wx.Menu()
        
        open_dir_item = main_menu.Append(wx.ID_ANY, "&Open download folder\tCtrl+D")
        self.Bind(wx.EVT_MENU, self.on_open_download_folder, open_dir_item)
        
        check_update_item = main_menu.Append(wx.ID_ANY, "Check for &updates")
        self.Bind(wx.EVT_MENU, self.on_manual_check_updates, check_update_item)
        
        main_menu.AppendSeparator()
        
        exit_item = main_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        menubar.Append(main_menu, "&Main")
        self.SetMenuBar(menubar)

    def on_open_download_folder(self, event):
        """Opens the download directory in file explorer."""
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
        os.startfile(DOWNLOAD_DIR)

    def on_manual_check_updates(self, event):
        """Manually checks for updates and notifies the user even if they are up-to-date."""
        self.SetTitle("Checking for updates...")
        latest = get_latest_version()
        self.SetTitle(f"Te_Tube, version: {version}")
        
        if latest:
            if latest != version:
                msg = f"A new version is available!\n\nCurrent version: {version}\nLatest version: {latest}\n\nDo you want to update now?"
                dlg = wx.MessageDialog(self, msg, "Software Update", wx.YES_NO | wx.ICON_INFORMATION)
                if dlg.ShowModal() == wx.ID_YES:
                    if run_updater():
                        self.Close()
                    else:
                        wx.MessageBox("Failed to launch updater.bat. please make sure it exists in the app folder.", "Error", wx.OK | wx.ICON_ERROR)
                dlg.Destroy()
            else:
                wx.MessageBox(f"You are using the latest version (v{version}).", "Software Update", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("Could not check for updates. Please check your internet connection.", "Update Error", wx.OK | wx.ICON_ERROR)

    def on_exit(self, event):
        """Exits the application."""
        self.Close()

    def setup_search_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Search box
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self.search_tab, label="Search Query:")
        self.search_input = wx.TextCtrl(self.search_tab, style=wx.TE_PROCESS_ENTER)
        self.search_input.SetHint("Enter keywords here...")
        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        
        # Accessibility for search input
        self.set_accessible_name(self.search_input, "Search YouTube")
        
        search_button = wx.Button(self.search_tab, label="Search")
        search_button.Bind(wx.EVT_BUTTON, self.on_search)
        self.set_accessible_name(search_button, "Search")

        hbox1.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox1.Add(self.search_input, 1, wx.EXPAND | wx.ALL, 5)
        hbox1.Add(search_button, 0, wx.ALL, 5)
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 5)

        # Result list
        self.result_list = wx.ListBox(self.search_tab, style=wx.LB_SINGLE)
        self.result_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play)
        self.result_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        
        # Accessibility for list box
        self.set_accessible_name(self.result_list, "Search Results")

        vbox.Add(self.result_list, 1, wx.EXPAND | wx.ALL, 5)
        self.search_tab.SetSizer(vbox)

    def setup_process_link_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Link input box
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        link_label = wx.StaticText(self.process_link_tab, label="Enter link video:")
        self.link_input = wx.TextCtrl(self.process_link_tab, style=wx.TE_PROCESS_ENTER)
        self.link_input.SetHint("Paste YouTube link here...")
        
        # Accessibility for link input
        self.set_accessible_name(self.link_input, "Enter link video")
        
        hbox1.Add(link_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox1.Add(self.link_input, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 10)
        
        # Action buttons
        hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        
        play_button = wx.Button(self.process_link_tab, label="Play")
        play_button.Bind(wx.EVT_BUTTON, self.on_play_link)
        self.set_accessible_name(play_button, "Play")
        
        download_button = wx.Button(self.process_link_tab, label="Download")
        download_button.Bind(wx.EVT_BUTTON, self.on_download_link)
        self.set_accessible_name(download_button, "Download")
        
        hbox2.Add(play_button, 1, wx.ALL | wx.EXPAND, 5)
        hbox2.Add(download_button, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(hbox2, 0, wx.EXPAND | wx.ALL, 5)
        
        self.process_link_tab.SetSizer(vbox)

    def on_search(self, event):
        query = self.search_input.GetValue()
        if not query:
            return

        # Show status
        self.SetTitle(f"Searching for '{query}'...")
        
        # Clear previous results
        self.result_list.Clear()
        try:
            self.results = search_youtube(query)
            
            for item in self.results:
                display_text = f"{item['title']} [{item['duration']}] - {item['uploader']}"
                self.result_list.Append(display_text)
        except Exception as e:
            wx.MessageBox(f"Error during search: {e}", "Search Error", wx.OK | wx.ICON_ERROR)
        
        self.SetTitle("Te_Tube - YouTube Search & Download")
        if self.result_list.GetCount() > 0:
            self.result_list.SetSelection(0)
            self.result_list.SetFocus()

    def on_play(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.results[selection]['url']
            self.play_url(video_url)

    def on_play_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a video link first.", "Error", wx.OK | wx.ICON_WARNING)
            return
        self.play_url(url)

    def play_url(self, url):
        try:
            play_video(url)
        except Exception as e:
            wx.MessageBox(f"Error playing video: {e}", "Playback Error", wx.OK | wx.ICON_ERROR)

    def on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            # Trigger play only if search box is NOT focused
            # OR if focus is in result_list
            focused = wx.Window.FindFocus()
            if focused != self.search_input:
                self.on_play(None)
                return # Don't Skip() if we handle it
        
        event.Skip()

    def on_check_clipboard(self, event):
        if not wx.TheClipboard.Open():
            return

        text_data = wx.TextDataObject()
        success = wx.TheClipboard.GetData(text_data)
        wx.TheClipboard.Close()

        if success:
            clipboard_text = text_data.GetText().strip()
            if clipboard_text and clipboard_text != self.last_clipboard_text:
                # Suppress dialog if user is currently typing/pasting into a text field
                focused = wx.Window.FindFocus()
                if isinstance(focused, wx.TextCtrl):
                    self.last_clipboard_text = clipboard_text
                    return

                # Improved regex to catch m.youtube, music.youtube, and various path formats
                youtube_regex = r'(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?([a-zA-Z0-9_-]{11})'
                if re.search(youtube_regex, clipboard_text):
                    self.last_clipboard_text = clipboard_text
                    # Show detection dialog
                    self.show_link_detected_dialog(clipboard_text)
                else:
                    # Update even if it's not a link to avoid checking again
                    self.last_clipboard_text = clipboard_text

    def show_link_detected_dialog(self, url):
        # We need to make sure we don't open multiple dialogs if one is already open
        # Since it's a modal dialog, it blocks the timer if shown as ShowModal
        
        dialog = LinkDetectedDialog(self, url)
        result = dialog.ShowModal()
        
        if result == wx.ID_YES: # Play
            self.play_url(url)
        elif result == wx.ID_SAVE: # Download (using ID_SAVE as a placeholder for Download)
            self.on_download_link_from_url(url)
        
        dialog.Destroy()

    def on_download_link_from_url(self, url):
        # Create a simple menu for format selection
        menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        
        for label, fmt in formats:
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.start_download(url, "Video from clipboard", f), item)
        
        self.PopupMenu(menu)
        menu.Destroy()

    def on_copy_link(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.results[selection]['url']
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(video_url))
                wx.TheClipboard.Close()
                # Update last_clipboard_text to prevent Te_Tube from detecting its own copy
                self.last_clipboard_text = video_url
                wx.MessageBox("Link copied to clipboard!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_context_menu(self, event):
        selection = self.result_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return

        menu = wx.Menu()
        play_item = menu.Append(wx.ID_ANY, "&Play\tEnter")
        self.Bind(wx.EVT_MENU, self.on_play, play_item)

        copy_item = menu.Append(wx.ID_ANY, "&Copy Link")
        self.Bind(wx.EVT_MENU, self.on_copy_link, copy_item)

        download_menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        
        for label, fmt in formats:
            item = download_menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.on_download(f), item)
            
        menu.AppendSubMenu(download_menu, "&Download")
        
        self.PopupMenu(menu)
        menu.Destroy()

    def on_download(self, fmt):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.results[selection]['url']
            title = self.results[selection]['title']
            self.start_download(video_url, title, fmt)

    def on_download_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a video link first.", "Error", wx.OK | wx.ICON_WARNING)
            return
        
        # Create a simple menu for format selection
        menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        
        for label, fmt in formats:
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.start_download(url, "Video from link", f), item)
        
        self.PopupMenu(menu)
        menu.Destroy()

    def start_download(self, url, title, fmt):
        dialog = DownloadProgressDialog(self, title, url, fmt)
        dialog.Show()

class DownloadThread(threading.Thread):
    def __init__(self, win, url, fmt):
        super().__init__()
        self.win = win
        self.url = url
        self.fmt = fmt
        self.daemon = True

    def run(self):
        try:
            def callback(p):
                wx.PostEvent(self.win, DownloadEvent(**p))
            
            final_path = download_media(self.url, self.fmt, callback)
            wx.PostEvent(self.win, DownloadEvent(status='finished', path=final_path))
        except Exception as e:
            wx.PostEvent(self.win, DownloadEvent(status='error', error=str(e)))

class DownloadProgressDialog(wx.Dialog):
    def __init__(self, parent, title, url, fmt):
        super().__init__(parent, title="Downloading...", size=(400, 180))
        self.video_title = title
        self.last_percent = -1
        
        panel = wx.Panel(self)
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.title_label = wx.StaticText(panel, label=f"Downloading: {title}")
        self.set_accessible_name(self.title_label, f"Downloading: {title}")
        
        self.gauge = wx.Gauge(panel, range=100, size=(350, 25))
        self.set_accessible_name(self.gauge, "Download progress")
        
        self.status_label = wx.StaticText(panel, label="Initializing...")
        self.set_accessible_name(self.status_label, "Status: Initializing")
        
        self.vbox.Add(self.title_label, 0, wx.ALL | wx.EXPAND, 10)
        self.vbox.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 10)
        self.vbox.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 10)
        
        panel.SetSizer(self.vbox)
        self.Centre()
        
        self.Bind(EVT_DOWNLOAD_UPDATE, self.on_update)
        
        self.thread = DownloadThread(self, url, fmt)
        self.thread.start()

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def on_update(self, event):
        status = event.status
        
        if status == 'downloading':
            percent = int(event.percent)
            if percent != self.last_percent:
                self.gauge.SetValue(percent)
                self.last_percent = percent
            
            # Clean up the status line (remove [download])
            clean_status = event.line.replace('[download]', '').strip()
            self.status_label.SetLabel(clean_status)
            # AVOID set_accessible_name on every tick as it's expensive and causes freeze
            
        elif status == 'finished':
            self.gauge.SetValue(100)
            self.status_label.SetLabel("Download Complete!")
            # Final accessibility update when finished is okay
            self.set_accessible_name(self.status_label, "Status: Download Complete")
            
            path = event.path or "Unknown location"
            wx.MessageBox(f"Download complete!\nFile saved at: {path}", "Success", wx.OK | wx.ICON_INFORMATION)
            self.Destroy()
            
        elif status == 'error':
            error_msg = event.error or "Unknown error"
            wx.MessageBox(f"Download failed: {error_msg}", "Error", wx.OK | wx.ICON_ERROR)
            self.Destroy()

class LinkDetectedDialog(wx.Dialog):
    def __init__(self, parent, url):
        super().__init__(parent, title="Link Detected", size=(500, 200))
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        label = wx.StaticText(panel, label=f"We detected a video link in your clipboard:\n\n{url}")
        label.Wrap(450)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        play_btn = wx.Button(panel, label="Play")
        play_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES))
        
        download_btn = wx.Button(panel, label="Download")
        download_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_SAVE))
        
        cancel_btn = wx.Button(panel, label="Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        
        hbox.Add(play_btn, 1, wx.ALL | wx.EXPAND, 5)
        hbox.Add(download_btn, 1, wx.ALL | wx.EXPAND, 5)
        hbox.Add(cancel_btn, 1, wx.ALL | wx.EXPAND, 5)
        
        vbox.Add(label, 1, wx.ALL | wx.EXPAND, 15)
        vbox.Add(hbox, 0, wx.ALL | wx.EXPAND, 10)
        
        panel.SetSizer(vbox)
        self.Centre()
        
        # Accessibility
        parent.set_accessible_name(play_btn, "Play video from clipboard")
        parent.set_accessible_name(download_btn, "Download video from clipboard")
        parent.set_accessible_name(cancel_btn, "Cancel and return to main interface")

def start_gui():
    app = wx.App()
    frame = TeTubeFrame()
    frame.Show()
    app.MainLoop()
