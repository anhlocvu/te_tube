import wx
import os
import threading
import re
import wx.lib.newevent
import json
import webbrowser
from modules.search_engine import search_youtube
from modules.player import play_video
from modules.app_updater import get_latest_version, run_updater
import speech_recognition as sr
from modules.settings_manager import load_settings, save_settings, get_download_dir, get_voice_language, get_voice_auto_search, DEFAULT_DOWNLOAD_DIR
from modules.downloader import download_media
version="1.3"

FAVORITES_FILE = "favorites.json"
WATCH_HISTORY_FILE = "watch_history.json"
# Define a custom event for progress updates using the modern way
DownloadEvent, EVT_DOWNLOAD_UPDATE = wx.lib.newevent.NewEvent()
SearchEvent, EVT_SEARCH_COMPLETE = wx.lib.newevent.NewEvent()
PlayEvent, EVT_PLAY_READY = wx.lib.newevent.NewEvent()

class TeTubeFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Te_Tube, version: "+version, size=(800, 600))
        
        self.results = []
        self.favorites = self.load_data(FAVORITES_FILE)
        self.history = self.load_data(WATCH_HISTORY_FILE)
        self.last_clipboard_text = ""
        self.is_listening = False # Flag to prevent multiple voice search triggers
        self.init_ui()
        self.Centre()
        
        # Use CHAR_HOOK for global hotkeys like Enter
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)
        
        # Search complete event
        self.Bind(EVT_SEARCH_COMPLETE, self.on_search_complete)

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
        self.favorite_tab = wx.Panel(self.notebook)
        self.history_tab = wx.Panel(self.notebook)
        self.process_link_tab = wx.Panel(self.notebook)
        
        self.notebook.AddPage(self.search_tab, "Search")
        self.notebook.AddPage(self.favorite_tab, "Favorite Videos")
        self.notebook.AddPage(self.history_tab, "Watch History")
        self.notebook.AddPage(self.process_link_tab, "Process via link")

        self.setup_search_tab()
        self.setup_favorite_tab()
        self.setup_history_tab()
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
        
        settings_item = main_menu.Append(wx.ID_ANY, "&Settings\tF4")
        self.Bind(wx.EVT_MENU, self.on_settings, settings_item)
        
        help_item = main_menu.Append(wx.ID_HELP, "&Help\tF1")
        self.Bind(wx.EVT_MENU, self.on_help, help_item)
        
        main_menu.AppendSeparator()
        
        exit_item = main_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        menubar.Append(main_menu, "&Main")
        self.SetMenuBar(menubar)

    def on_help(self, event):
        """Shows the help/documentation dialog."""
        dlg = HelpDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def on_settings(self, event):
        """Shows the settings dialog."""
        dlg = SettingsDialog(self)
        dlg.ShowModal()
        dlg.Destroy()

    def on_open_download_folder(self, event):
        """Opens the download directory in file explorer."""
        path = get_download_dir()
        if not os.path.exists(path):
            os.makedirs(path)
        os.startfile(path)

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

        self.voice_button = wx.Button(self.search_tab, label="Voice Search")
        self.voice_button.Bind(wx.EVT_BUTTON, self.on_voice_search)
        self.set_accessible_name(self.voice_button, "Search by voice")

        hbox1.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox1.Add(self.search_input, 1, wx.EXPAND | wx.ALL, 5)
        hbox1.Add(search_button, 0, wx.ALL, 5)
        hbox1.Add(self.voice_button, 0, wx.ALL, 5)
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
        
        play_audio_button = wx.Button(self.process_link_tab, label="Play as Audio")
        play_audio_button.Bind(wx.EVT_BUTTON, self.on_play_link_audio)
        self.set_accessible_name(play_audio_button, "Play as Audio")
        hbox2.Add(play_audio_button, 1, wx.ALL | wx.EXPAND, 5)

        hbox2.Add(download_button, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(hbox2, 0, wx.EXPAND | wx.ALL, 5)
        
        self.process_link_tab.SetSizer(vbox)

    def setup_favorite_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.favorite_list = wx.ListBox(self.favorite_tab, style=wx.LB_SINGLE)
        self.favorite_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play_favorite)
        self.favorite_list.Bind(wx.EVT_CONTEXT_MENU, self.on_favorite_context_menu)
        self.set_accessible_name(self.favorite_list, "Favorite Videos List")
        vbox.Add(self.favorite_list, 1, wx.EXPAND | wx.ALL, 5)
        
        clear_fav_btn = wx.Button(self.favorite_tab, label="Clear All Favorites")
        clear_fav_btn.Bind(wx.EVT_BUTTON, self.on_clear_favorites)
        self.set_accessible_name(clear_fav_btn, "Clear all favorite videos")
        vbox.Add(clear_fav_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

        self.favorite_tab.SetSizer(vbox)
        self.update_favorite_listbox()

    def setup_history_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.history_list = wx.ListBox(self.history_tab, style=wx.LB_SINGLE)
        self.history_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play_history)
        self.history_list.Bind(wx.EVT_CONTEXT_MENU, self.on_history_context_menu)
        self.set_accessible_name(self.history_list, "Watch History List")
        vbox.Add(self.history_list, 1, wx.EXPAND | wx.ALL, 5)
        
        clear_history_btn = wx.Button(self.history_tab, label="Clear All History")
        clear_history_btn.Bind(wx.EVT_BUTTON, self.on_clear_history)
        self.set_accessible_name(clear_history_btn, "Clear all watch history")
        vbox.Add(clear_history_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

        self.history_tab.SetSizer(vbox)
        self.update_history_listbox()

    def on_clear_favorites(self, event):
        """Clears all favorites after user confirmation."""
        if not self.favorites:
            wx.MessageBox("Your favorites list is already empty.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.MessageDialog(self, "Are you sure you want to clear all favorite videos?", "Confirm Clear", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.favorites = []
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()
            wx.MessageBox("All favorites have been cleared.", "Success", wx.OK | wx.ICON_INFORMATION)
        dlg.Destroy()

    def on_clear_history(self, event):
        """Clears all history after user confirmation."""
        if not self.history:
            wx.MessageBox("Your history is already empty.", "Info", wx.OK | wx.ICON_INFORMATION)
            return

        dlg = wx.MessageDialog(self, "Are you sure you want to clear all watch history?", "Confirm Clear", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.history = []
            self.save_data(WATCH_HISTORY_FILE, self.history)
            self.update_history_listbox()
            wx.MessageBox("Watch history has been cleared.", "Success", wx.OK | wx.ICON_INFORMATION)
        dlg.Destroy()

    def load_data(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_data(self, filename, data):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def update_favorite_listbox(self):
        self.favorite_list.Clear()
        for item in self.favorites:
            display_text = f"{item['title']} - {item.get('uploader', 'Unknown')}"
            self.favorite_list.Append(display_text)

    def update_history_listbox(self):
        self.history_list.Clear()
        for item in reversed(self.history): # Show newest first
            display_text = f"{item['title']} - {item.get('uploader', 'Unknown')}"
            self.history_list.Append(display_text)

    def add_to_history(self, video_data):
        # Check if already in history, remove old entry and add to top
        self.history = [h for h in self.history if h['url'] != video_data['url']]
        self.history.append(video_data)
        if len(self.history) > 100: # Limit history
            self.history.pop(0)
        self.save_data(WATCH_HISTORY_FILE, self.history)
        wx.CallAfter(self.update_history_listbox)

    def on_search(self, event):
        query = self.search_input.GetValue()
        if not query:
            return

        # Create and show the modal searching dialog
        dialog = SearchProgressDialog(self, query)
        dialog.ShowModal()
        dialog.Destroy()
        
        # Focus back to result list after search
        if self.result_list.GetCount() > 0:
            self.result_list.SetSelection(0)
            self.result_list.SetFocus()

    def on_search_complete(self, event):
        """Handles the completion of a search on the main thread."""
        results = event.results
        error = event.error
        
        # Clear previous results
        self.result_list.Clear()
        
        if error:
            wx.MessageBox(f"Error during search: {error}", "Search Error", wx.OK | wx.ICON_ERROR)
            return
            
        self.results = results
        for item in self.results:
            display_text = f"{item['title']} [{item['duration']}] - {item['uploader']}"
            self.result_list.Append(display_text)

    def on_play(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            self.play_url(video_data['url'], title=video_data['title'])
            self.add_to_history(video_data)

    def on_play_audio(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            self.play_url(video_data['url'], title=video_data['title'], audio_only=True)
            self.add_to_history(video_data)

    def on_play_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a video link first.", "Error", wx.OK | wx.ICON_WARNING)
            return
        # We don't have full info, but we can try to get it or just play
        self.play_url(url, title="Video from link")
        self.add_to_history({'title': 'Video from link', 'url': url, 'uploader': 'Unknown'})

    def on_play_link_audio(self, event):
        url = self.link_input.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a video link first.", "Error", wx.OK | wx.ICON_WARNING)
            return
        self.play_url(url, title="Video from link", audio_only=True)
        self.add_to_history({'title': 'Video from link', 'url': url, 'uploader': 'Unknown'})

    def play_url(self, url, title="Unknown Video", audio_only=False):
        # Create and show the modal preparing dialog
        dialog = PlayProgressDialog(self, url, title, audio_only)
        dialog.ShowModal()
        dialog.Destroy()

    def on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            focused = wx.Window.FindFocus()
            if focused == self.result_list:
                self.on_play(None)
                return
            elif focused == self.favorite_list:
                self.on_play_favorite(None)
                return
            elif focused == self.history_list:
                self.on_play_history(None)
                return
            elif focused == self.search_input:
                # Let the normal on_search handle it
                event.Skip()
                return
        elif keycode == wx.WXK_F1:
            self.on_help(None)
            return
        elif keycode == wx.WXK_F4 and not event.AltDown():
            self.on_settings(None)
            return
        
        event.Skip()

    def on_voice_search(self, event):
        """Performs voice recognition in a background thread."""
        if self.is_listening: # Avoid re-triggering while listening
            return
            
        self.is_listening = True
        lang = get_voice_language()
        
        # Change button state immediately to inform the user (and NVDA)
        self.voice_button.SetLabel("Listening...")
        # Keeping button enabled ensures the focus doesn't jump to the empty list
        self.set_accessible_name(self.voice_button, "Listening, please speak now")
        
        # Ensure UI updates so NVDA can speak the label change
        wx.GetApp().Yield()
        
        # Run recognition in a separate thread to keep UI responsive
        threading.Thread(target=self._do_voice_recognition, args=(lang,), daemon=True).start()

    def _do_voice_recognition(self, lang):
        """Worker function for voice recognition."""
        r = sr.Recognizer()
        query = None
        error_msg = None
        
        try:
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                # Listen with timeout
                audio = r.listen(source, timeout=5, phrase_time_limit=10)
            
            # Recognize using Google
            query = r.recognize_google(audio, language=lang)
        except sr.WaitTimeoutError:
            error_msg = "No speech detected. Please try again."
        except sr.UnknownValueError:
            error_msg = "Could not understand audio."
        except Exception as e:
            error_msg = f"Voice search error: {e}"
            
        # Update UI back on the main thread
        wx.CallAfter(self._on_voice_recognition_complete, query, error_msg)

    def _on_voice_recognition_complete(self, query, error_msg):
        """Handles the result of voice recognition on the main thread."""
        # Reset state
        self.is_listening = False
        self.voice_button.SetLabel("Voice Search")
        self.set_accessible_name(self.voice_button, "Search by voice")
        
        if query:
            self.search_input.SetValue(query)
            if get_voice_auto_search():
                self.on_search(None)
            else:
                # Just focus the input so user can review/edit
                self.search_input.SetFocus()
        elif error_msg:
            wx.MessageBox(error_msg, "Voice Search", wx.OK | wx.ICON_WARNING)

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
            self.play_url(url, title="Video from clipboard")
        elif result == wx.ID_SAVE: # Download (using ID_SAVE as a placeholder for Download)
            self.on_download_link_from_url(url)
        
        dialog.Destroy()

    def on_download_link_from_url(self, url):
        dlg = DownloadOptionsDialog(self, "Video from clipboard", url)
        dlg.ShowModal()
        dlg.Destroy()

    def on_copy_link(self, event):
        # Determine which list is active
        focused = wx.Window.FindFocus()
        source_list = None
        source_data = []
        
        if focused == self.result_list:
            source_list = self.result_list
            source_data = self.results
        elif focused == self.favorite_list:
            source_list = self.favorite_list
            source_data = self.favorites
        elif focused == self.history_list:
            source_list = self.history_list
            source_data = list(reversed(self.history))
        
        if not source_list: return

        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = source_data[selection]['url']
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(video_url))
                wx.TheClipboard.Close()
                # Update last_clipboard_text to prevent Te_Tube from detecting its own copy
                self.last_clipboard_text = video_url
                wx.MessageBox("Link copied to clipboard!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_open_in_browser(self, event):
        focused = wx.Window.FindFocus()
        source_data = []
        
        if focused == self.result_list:
            source_data = self.results
        elif focused == self.favorite_list:
            source_data = self.favorites
        elif focused == self.history_list:
            source_data = list(reversed(self.history))
        
        if not source_data: return

        source_list = focused # focused is the listbox
        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = source_data[selection]['url']
            webbrowser.open(video_url)

    def on_go_to_channel(self, event):
        focused = wx.Window.FindFocus()
        source_data = []
        
        if focused == self.result_list:
            source_data = self.results
        elif focused == self.favorite_list:
            source_data = self.favorites
        elif focused == self.history_list:
            source_data = list(reversed(self.history))
        
        if not source_data: return

        source_list = focused
        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            item = source_data[selection]
            uploader_url = item.get('uploader_url')
            if uploader_url:
                webbrowser.open(uploader_url)
            else:
                msg = "Channel URL not available for this entry.\n\nNote: Older history/favorite entries saved before the 'Go to Channel' feature was added do not have this information."
                wx.MessageBox(msg, "Info", wx.OK | wx.ICON_INFORMATION)

    def on_add_favorite(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            # Check if already in favorites
            if any(f['url'] == video_data['url'] for f in self.favorites):
                wx.MessageBox("This video is already in your favorites.", "Info", wx.OK | wx.ICON_INFORMATION)
                return
            
            self.favorites.append(video_data)
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()
            wx.MessageBox("Added to favorites!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_remove_favorite(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            del self.favorites[selection]
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()
            wx.MessageBox("Removed from favorites.", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_remove_history(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            # History is displayed reversed
            actual_index = len(self.history) - 1 - selection
            del self.history[actual_index]
            self.save_data(WATCH_HISTORY_FILE, self.history)
            self.update_history_listbox()
            wx.MessageBox("Removed from history.", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_play_favorite(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.favorites[selection]
            self.play_url(video_data['url'], title=video_data['title'])
            self.add_to_history(video_data)

    def on_play_favorite_audio(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.favorites[selection]
            self.play_url(video_data['url'], title=video_data['title'], audio_only=True)
            self.add_to_history(video_data)

    def on_play_history(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            # History is displayed reversed
            actual_index = len(self.history) - 1 - selection
            video_data = self.history[actual_index]
            self.play_url(video_data['url'], title=video_data['title'])
            # Re-adding to history will move it to top
            self.add_to_history(video_data)

    def on_play_history_audio(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            video_data = self.history[actual_index]
            self.play_url(video_data['url'], title=video_data['title'], audio_only=True)
            self.add_to_history(video_data)

    def on_context_menu(self, event):
        selection = self.result_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return

        menu = wx.Menu()
        play_item = menu.Append(wx.ID_ANY, "&Play\tEnter")
        self.Bind(wx.EVT_MENU, self.on_play, play_item)

        play_audio_item = menu.Append(wx.ID_ANY, "Play as &Audio")
        self.Bind(wx.EVT_MENU, self.on_play_audio, play_audio_item)

        open_browser_item = menu.Append(wx.ID_ANY, "Open in &Browser")
        self.Bind(wx.EVT_MENU, self.on_open_in_browser, open_browser_item)

        go_channel_item = menu.Append(wx.ID_ANY, "Go to &Channel")
        self.Bind(wx.EVT_MENU, self.on_go_to_channel, go_channel_item)

        copy_item = menu.Append(wx.ID_ANY, "&Copy Link")
        self.Bind(wx.EVT_MENU, self.on_copy_link, copy_item)

        favorite_item = menu.Append(wx.ID_ANY, "&Add Favorite")
        self.Bind(wx.EVT_MENU, self.on_add_favorite, favorite_item)

        download_item = menu.Append(wx.ID_ANY, "&Download")
        self.Bind(wx.EVT_MENU, self.on_download, download_item)
        
        self.PopupMenu(menu)
        menu.Destroy()

    def on_favorite_context_menu(self, event):
        selection = self.favorite_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return

        menu = wx.Menu()
        play_item = menu.Append(wx.ID_ANY, "&Play")
        self.Bind(wx.EVT_MENU, self.on_play_favorite, play_item)

        play_audio_item = menu.Append(wx.ID_ANY, "Play as &Audio")
        self.Bind(wx.EVT_MENU, self.on_play_favorite_audio, play_audio_item)

        open_browser_item = menu.Append(wx.ID_ANY, "Open in &Browser")
        self.Bind(wx.EVT_MENU, self.on_open_in_browser, open_browser_item)

        go_channel_item = menu.Append(wx.ID_ANY, "Go to &Channel")
        self.Bind(wx.EVT_MENU, self.on_go_to_channel, go_channel_item)

        copy_item = menu.Append(wx.ID_ANY, "&Copy Link")
        self.Bind(wx.EVT_MENU, self.on_copy_link, copy_item)

        remove_item = menu.Append(wx.ID_ANY, "&Remove from favorite")
        self.Bind(wx.EVT_MENU, self.on_remove_favorite, remove_item)

        download_item = menu.Append(wx.ID_ANY, "&Download")
        self.Bind(wx.EVT_MENU, self.on_download_favorite, download_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_history_context_menu(self, event):
        selection = self.history_list.GetSelection()
        if selection == wx.NOT_FOUND:
            return

        menu = wx.Menu()
        play_item = menu.Append(wx.ID_ANY, "&Play")
        self.Bind(wx.EVT_MENU, self.on_play_history, play_item)

        play_audio_item = menu.Append(wx.ID_ANY, "Play as &Audio")
        self.Bind(wx.EVT_MENU, self.on_play_history_audio, play_audio_item)

        open_browser_item = menu.Append(wx.ID_ANY, "Open in &Browser")
        self.Bind(wx.EVT_MENU, self.on_open_in_browser, open_browser_item)

        go_channel_item = menu.Append(wx.ID_ANY, "Go to &Channel")
        self.Bind(wx.EVT_MENU, self.on_go_to_channel, go_channel_item)

        copy_item = menu.Append(wx.ID_ANY, "&Copy Link")
        self.Bind(wx.EVT_MENU, self.on_copy_link, copy_item)

        remove_item = menu.Append(wx.ID_ANY, "&Remove from history")
        self.Bind(wx.EVT_MENU, self.on_remove_history, remove_item)

        download_item = menu.Append(wx.ID_ANY, "&Download")
        self.Bind(wx.EVT_MENU, self.on_download_history, download_item)

        self.PopupMenu(menu)
        menu.Destroy()

    def on_download_favorite(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.favorites[selection]['url']
            title = self.favorites[selection]['title']
            dlg = DownloadOptionsDialog(self, title, video_url)
            dlg.ShowModal()
            dlg.Destroy()

    def on_download_history(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            video_url = self.history[actual_index]['url']
            title = self.history[actual_index]['title']
            dlg = DownloadOptionsDialog(self, title, video_url)
            dlg.ShowModal()
            dlg.Destroy()

    def on_download(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.results[selection]['url']
            title = self.results[selection]['title']
            dlg = DownloadOptionsDialog(self, title, video_url)
            dlg.ShowModal()
            dlg.Destroy()

    def on_download_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url:
            wx.MessageBox("Please enter a video link first.", "Error", wx.OK | wx.ICON_WARNING)
            return
        
        dlg = DownloadOptionsDialog(self, "Video from link", url)
        dlg.ShowModal()
        dlg.Destroy()

    def start_download(self, url, title, fmt, start_time=None, end_time=None):
        dialog = DownloadProgressDialog(self, title, url, fmt, start_time, end_time)
        dialog.Show()

class DownloadThread(threading.Thread):
    def __init__(self, win, url, fmt, start_time=None, end_time=None):
        super().__init__()
        self.win = win
        self.url = url
        self.fmt = fmt
        self.start_time = start_time
        self.end_time = end_time
        self.daemon = True

    def run(self):
        try:
            def callback(p):
                wx.PostEvent(self.win, DownloadEvent(**p))
            
            final_path = download_media(self.url, self.fmt, callback, self.start_time, self.end_time)
            wx.PostEvent(self.win, DownloadEvent(status='finished', path=final_path))
        except Exception as e:
            wx.PostEvent(self.win, DownloadEvent(status='error', error=str(e)))

class DownloadProgressDialog(wx.Dialog):
    def __init__(self, parent, title, url, fmt, start_time=None, end_time=None):
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
        
        self.thread = DownloadThread(self, url, fmt, start_time, end_time)
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

class HelpViewerDialog(wx.Dialog):
    def __init__(self, parent, title, content):
        super().__init__(parent, title=f"Content: {title}", size=(800, 600), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX)
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.content_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.TE_NOHIDESEL)
        self.content_text.SetValue(content)
        self.set_accessible_name(self.content_text, f"Document Content for {title}")
        
        close_btn = wx.Button(panel, id=wx.ID_CANCEL, label="Close")
        self.set_accessible_name(close_btn, "Close document")
        
        vbox.Add(self.content_text, 1, wx.EXPAND | wx.ALL, 10)
        vbox.Add(close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        panel.SetSizer(vbox)
        self.Centre()
        
        # Set focus to text
        wx.CallAfter(self.content_text.SetFocus)
        wx.CallAfter(lambda: self.content_text.SetInsertionPoint(0))

    def set_accessible_name(self, control, name):
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

class HelpDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Help & Documentation", size=(600, 400))
        self.dock_dir = os.path.join(os.getcwd(), "docks")
        self.init_ui()
        self.Centre()
        
        # Bind global key hook for Escape
        self.Bind(wx.EVT_CHAR_HOOK, self.on_dialog_char_hook)

    def on_dialog_char_hook(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
        else:
            event.Skip()

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def init_ui(self):
        panel = wx.Panel(self)
        self.main_vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(panel, label="Select a topic to view (Press Enter or Space to open):")
        self.main_vbox.Add(lbl, 0, wx.ALL, 10)
        
        self.file_list = wx.ListBox(panel, style=wx.LB_SINGLE)
        self.file_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_item_selected)
        self.file_list.Bind(wx.EVT_KEY_DOWN, self.on_list_key)
        self.set_accessible_name(self.file_list, "Documentation Topics")
        
        self.main_vbox.Add(self.file_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        self.return_btn = wx.Button(panel, id=wx.ID_CANCEL, label="Return to Main Window (Esc)")
        self.set_accessible_name(self.return_btn, "Return to Main Window")
        
        self.main_vbox.Add(self.return_btn, 0, wx.ALIGN_CENTER | wx.ALL, 15)
        
        panel.SetSizer(self.main_vbox)
        self.populate_list()

    def populate_list(self):
        if not os.path.exists(self.dock_dir):
            return
        files = sorted([f for f in os.listdir(self.dock_dir) if f.endswith(".txt")])
        for f in files:
            self.file_list.Append(f[:-4]) # Hide .txt
        if self.file_list.GetCount() > 0:
            self.file_list.SetSelection(0)

    def on_list_key(self, event):
        keycode = event.GetKeyCode()
        # Support both Enter and Space to open document
        if keycode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER, wx.WXK_SPACE]:
            self.on_item_selected(None)
        else:
            event.Skip()

    def on_item_selected(self, event):
        selection = self.file_list.GetSelection()
        if selection != wx.NOT_FOUND:
            file_name = self.file_list.GetString(selection) + ".txt"
            file_path = os.path.join(self.dock_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Show in new dialog
                viewer = HelpViewerDialog(self, self.file_list.GetString(selection), content)
                viewer.ShowModal()
                viewer.Destroy()
                
                self.file_list.SetFocus()
            except Exception as e:
                wx.MessageBox(f"Error reading file: {e}", "Error", wx.OK | wx.ICON_ERROR)

class SettingsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="Settings", size=(500, 450))
        self.config = load_settings()
        
        # We need to get audio devices for the playback tab
        # Import here to avoid circular imports if player imports gui
        from modules.player import get_audio_devices
        self.audio_devices = get_audio_devices()
        
        self.init_ui()
        self.Centre()

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.notebook = wx.Notebook(panel)
        self.general_tab = wx.Panel(self.notebook)
        self.voice_tab = wx.Panel(self.notebook)
        self.playback_tab = wx.Panel(self.notebook)
        
        self.notebook.AddPage(self.general_tab, "General")
        self.notebook.AddPage(self.voice_tab, "Voice Search")
        self.notebook.AddPage(self.playback_tab, "Playback")
        
        self.setup_general_tab()
        self.setup_voice_tab()
        self.setup_playback_tab()
        
        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 10)
        
        # Bottom buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(panel, id=wx.ID_OK, label="OK")
        ok_btn.SetDefault() # Press Enter to trigger
        self.Bind(wx.EVT_BUTTON, self.on_save, id=wx.ID_OK)
        self.set_accessible_name(ok_btn, "Save settings and close")
        
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="Cancel")
        # wx.ID_CANCEL automatically handles Escape key
        self.set_accessible_name(cancel_btn, "Cancel changes and close")
        
        hbox.Add(ok_btn, 0, wx.ALL, 5)
        hbox.Add(cancel_btn, 0, wx.ALL, 5)
        vbox.Add(hbox, 0, wx.ALIGN_RIGHT | wx.RIGHT | wx.BOTTOM, 10)
        
        panel.SetSizer(vbox)

    def setup_general_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self.general_tab, label="Download Directory:")
        self.dir_input = wx.TextCtrl(self.general_tab, value=self.config.get('General', 'download_dir'))
        self.set_accessible_name(self.dir_input, "Download directory path")
        
        browse_btn = wx.Button(self.general_tab, label="Browse...")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.set_accessible_name(browse_btn, "Browse for download folder")
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add(self.dir_input, 1, wx.EXPAND | wx.RIGHT, 5)
        hbox.Add(browse_btn, 0)
        
        vbox.Add(lbl, 0, wx.ALL, 10)
        vbox.Add(hbox, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        reset_btn = wx.Button(self.general_tab, label="Reset to Default")
        reset_btn.Bind(wx.EVT_BUTTON, self.on_reset_dir)
        self.set_accessible_name(reset_btn, "Reset download directory to default")
        vbox.Add(reset_btn, 0, wx.ALL, 10)
        
        self.general_tab.SetSizer(vbox)

    def setup_voice_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(self.voice_tab, label="Voice Recognition Language:")
        
        # Common languages for the combo box
        self.languages = [
            ("Vietnamese", "vi-VN"),
            ("English (US)", "en-US"),
            ("English (UK)", "en-GB"),
            ("Japanese", "ja-JP"),
            ("Korean", "ko-KR"),
            ("Chinese", "zh-CN"),
            ("French", "fr-FR")
        ]
        
        lang_labels = [l[0] for l in self.languages]
        current_code = self.config.get('VoiceSearch', 'language')
        
        # Find index of current language code
        current_index = 0
        for i, (name, code) in enumerate(self.languages):
            if code == current_code:
                current_index = i
                break
                
        self.lang_combo = wx.ComboBox(self.voice_tab, choices=lang_labels, style=wx.CB_READONLY)
        self.lang_combo.SetSelection(current_index)
        self.set_accessible_name(self.lang_combo, "Select voice recognition language")
        
        vbox.Add(lbl, 0, wx.ALL, 10)
        vbox.Add(self.lang_combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # Auto-search Checkbox
        self.auto_search_cb = wx.CheckBox(self.voice_tab, label="Auto-search after voice input")
        current_auto_search = self.config.getboolean('VoiceSearch', 'auto_search', fallback=False)
        self.auto_search_cb.SetValue(current_auto_search)
        self.set_accessible_name(self.auto_search_cb, "Auto-search after voice input")
        
        vbox.Add(self.auto_search_cb, 0, wx.ALL | wx.LEFT, 10)
        
        self.voice_tab.SetSizer(vbox)

    def setup_playback_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        # Audio Device Selection
        lbl_dev = wx.StaticText(self.playback_tab, label="Output Device:")
        
        # Populate from self.audio_devices
        dev_labels = [d[1] for d in self.audio_devices]
        current_dev = self.config.get('Playback', 'output_device', fallback='default')
        
        current_dev_index = 0
        for i, d in enumerate(self.audio_devices):
            if d[0] == current_dev:
                current_dev_index = i
                break
                
        self.dev_combo = wx.ComboBox(self.playback_tab, choices=dev_labels, style=wx.CB_READONLY)
        self.dev_combo.SetSelection(current_dev_index)
        self.set_accessible_name(self.dev_combo, "Select output device")
        
        vbox.Add(lbl_dev, 0, wx.ALL, 10)
        vbox.Add(self.dev_combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # Seek Time Selection
        lbl_seek = wx.StaticText(self.playback_tab, label="Seek Time:")
        
        self.seek_times = [("5 seconds", 5), ("10 seconds", 10), ("15 seconds", 15), ("30 seconds", 30)]
        seek_labels = [s[0] for s in self.seek_times]
        current_seek = self.config.getint('Playback', 'seek_time', fallback=10)
        
        current_seek_index = 1 # default 10s
        for i, s in enumerate(self.seek_times):
            if s[1] == current_seek:
                current_seek_index = i
                break
                
        self.seek_combo = wx.ComboBox(self.playback_tab, choices=seek_labels, style=wx.CB_READONLY)
        self.seek_combo.SetSelection(current_seek_index)
        self.set_accessible_name(self.seek_combo, "Select seek time")
        
        vbox.Add(lbl_seek, 0, wx.ALL, 10)
        vbox.Add(self.seek_combo, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        self.playback_tab.SetSizer(vbox)

    def on_browse(self, event):
        default_path = self.dir_input.GetValue()
        dlg = wx.DirDialog(self, "Choose Download Directory", defaultPath=default_path, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.dir_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_reset_dir(self, event):
        self.dir_input.SetValue(DEFAULT_DOWNLOAD_DIR)

    def on_save(self, event):
        # Update config object
        self.config['General']['download_dir'] = self.dir_input.GetValue()
        
        lang_index = self.lang_combo.GetSelection()
        if lang_index != wx.NOT_FOUND:
            self.config['VoiceSearch']['language'] = self.languages[lang_index][1]
            
        self.config['VoiceSearch']['auto_search'] = str(self.auto_search_cb.GetValue())
        
        dev_index = self.dev_combo.GetSelection()
        if dev_index != wx.NOT_FOUND:
            self.config['Playback']['output_device'] = self.audio_devices[dev_index][0]
            
        seek_index = self.seek_combo.GetSelection()
        if seek_index != wx.NOT_FOUND:
            self.config['Playback']['seek_time'] = str(self.seek_times[seek_index][1])
            
        save_settings(self.config)
        self.EndModal(wx.ID_OK)

class SearchThread(threading.Thread):
    def __init__(self, parent, query):
        super().__init__()
        self.parent = parent
        self.query = query
        self.daemon = True

    def run(self):
        try:
            results = search_youtube(self.query)
            wx.PostEvent(self.parent, SearchEvent(results=results, error=None))
        except Exception as e:
            wx.PostEvent(self.parent, SearchEvent(results=[], error=str(e)))

class SearchProgressDialog(wx.Dialog):
    def __init__(self, parent, query):
        super().__init__(parent, title="Searching", size=(350, 150), style=wx.CAPTION)
        self.parent = parent
        self.query = query
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.status_label = wx.StaticText(panel, label=f"Searching for: {query}")
        self.set_accessible_name(self.status_label, f"Searching for {query}, please wait...")
        
        # Pulsing gauge to show activity
        self.gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.set_accessible_name(self.gauge, "Search in progress")
        
        vbox.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 15)
        vbox.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 15)
        
        panel.SetSizer(vbox)
        self.Centre()
        
        # Timer to pulse the gauge
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)
        
        # Start the search thread
        self.thread = SearchThread(self.parent, self.query)
        self.thread.start()
        
        # Bind the search complete event to this dialog so it can close itself
        self.parent.Bind(EVT_SEARCH_COMPLETE, self.on_search_finished)

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def on_timer(self, event):
        self.gauge.Pulse()

    def on_search_finished(self, event):
        self.timer.Stop()
        # Unbind from parent to avoid multiple triggers if not cleaned up
        self.parent.Unbind(EVT_SEARCH_COMPLETE)
        # Re-post the event to parent so parent's handler can also run
        wx.PostEvent(self.parent, event)
        self.EndModal(wx.ID_OK)

class PlayProgressDialog(wx.Dialog):
    def __init__(self, parent, url, title, audio_only):
        super().__init__(parent, title="Playing", size=(350, 150), style=wx.CAPTION)
        self.parent = parent
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.status_label = wx.StaticText(panel, label=f"Preparing playback for: {title}...")
        self.set_accessible_name(self.status_label, f"Preparing playback for {title}, please wait...")
        
        self.gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.set_accessible_name(self.gauge, "Preparation in progress")
        
        vbox.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 15)
        vbox.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 15)
        
        panel.SetSizer(vbox)
        self.Centre()
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(50)
        
        # Start playback in background via the player module
        def on_start(error=None):
            wx.PostEvent(self, PlayEvent(error=error))
            
        play_video(url, title=title, audio_only=audio_only, on_start_callback=on_start)
        
        self.Bind(EVT_PLAY_READY, self.on_ready)

    def set_accessible_name(self, control, name):
        """Safely sets the accessible name for a control."""
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def on_timer(self, event):
        self.gauge.Pulse()

    def on_ready(self, event):
        self.timer.Stop()
        if event.error:
            wx.MessageBox(f"Error starting playback: {event.error}", "Playback Error", wx.OK | wx.ICON_ERROR)
        self.EndModal(wx.ID_OK)

class DownloadOptionsDialog(wx.Dialog):
    def __init__(self, parent, title, url):
        super().__init__(parent, title="Download Options", size=(400, 300))
        self.parent = parent
        self.video_title = title
        self.url = url
        self.init_ui()
        self.Centre()

    def set_accessible_name(self, control, name):
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        lbl = wx.StaticText(panel, label=f"Download: {self.video_title}")
        lbl.Wrap(380)
        vbox.Add(lbl, 0, wx.ALL | wx.EXPAND, 10)
        
        # Format Selection
        format_lbl = wx.StaticText(panel, label="Select Format:")
        vbox.Add(format_lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        self.formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        format_labels = [f[0] for f in self.formats]
        self.format_combo = wx.ComboBox(panel, choices=format_labels, style=wx.CB_READONLY)
        self.format_combo.SetSelection(0)
        self.set_accessible_name(self.format_combo, "Select download format")
        vbox.Add(self.format_combo, 0, wx.ALL | wx.EXPAND, 10)
        
        # Time Range
        self.time_checkbox = wx.CheckBox(panel, label="Download specific time range")
        self.time_checkbox.Bind(wx.EVT_CHECKBOX, self.on_checkbox)
        self.set_accessible_name(self.time_checkbox, "Download specific time range")
        vbox.Add(self.time_checkbox, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        time_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        start_lbl = wx.StaticText(panel, label="Start (HH:MM:SS):")
        self.start_input = wx.TextCtrl(panel)
        self.start_input.Disable()
        self.set_accessible_name(self.start_input, "Start time in hours, minutes, seconds")
        
        end_lbl = wx.StaticText(panel, label="End (HH:MM:SS):")
        self.end_input = wx.TextCtrl(panel)
        self.end_input.Disable()
        self.set_accessible_name(self.end_input, "End time in hours, minutes, seconds")
        
        time_vbox1 = wx.BoxSizer(wx.VERTICAL)
        time_vbox1.Add(start_lbl, 0, wx.BOTTOM, 5)
        time_vbox1.Add(self.start_input, 0, wx.EXPAND)
        
        time_vbox2 = wx.BoxSizer(wx.VERTICAL)
        time_vbox2.Add(end_lbl, 0, wx.BOTTOM, 5)
        time_vbox2.Add(self.end_input, 0, wx.EXPAND)
        
        time_hbox.Add(time_vbox1, 1, wx.RIGHT, 10)
        time_hbox.Add(time_vbox2, 1, wx.LEFT, 10)
        vbox.Add(time_hbox, 0, wx.ALL | wx.EXPAND, 10)
        
        # Buttons
        btn_hbox = wx.BoxSizer(wx.HORIZONTAL)
        download_btn = wx.Button(panel, id=wx.ID_OK, label="Download")
        download_btn.SetDefault()
        self.Bind(wx.EVT_BUTTON, self.on_download, id=wx.ID_OK)
        self.set_accessible_name(download_btn, "Start download")
        
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="Cancel")
        self.set_accessible_name(cancel_btn, "Cancel download")
        
        btn_hbox.Add(download_btn, 0, wx.RIGHT, 10)
        btn_hbox.Add(cancel_btn, 0)
        vbox.Add(btn_hbox, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        panel.SetSizer(vbox)

    def on_checkbox(self, event):
        is_checked = self.time_checkbox.GetValue()
        self.start_input.Enable(is_checked)
        self.end_input.Enable(is_checked)

    def on_download(self, event):
        fmt = self.formats[self.format_combo.GetSelection()][1]
        start_time = None
        end_time = None
        
        if self.time_checkbox.GetValue():
            start_time = self.start_input.GetValue().strip()
            end_time = self.end_input.GetValue().strip()
            
            # Simple validation to ensure format looks roughly like a time or at least isn't just spaces
            # Let yt-dlp handle strict parsing, but we shouldn't send empty strings if checked
            if not start_time and not end_time:
                wx.MessageBox("Please enter at least a start or end time.", "Error", wx.OK | wx.ICON_WARNING)
                return
                
        self.parent.start_download(self.url, self.video_title, fmt, start_time, end_time)
        self.EndModal(wx.ID_OK)

def start_gui():
    app = wx.App()
    frame = TeTubeFrame()
    frame.Show()
    app.MainLoop()
