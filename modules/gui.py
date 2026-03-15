import wx
import os
import threading
import re
import wx.lib.newevent
import json
import webbrowser
import configparser
import speech_recognition as sr
from modules.search_engine import search_youtube
from modules.player import play_video
from modules.app_updater import get_latest_version, run_updater
from modules.downloader import get_default_download_dir, download_media

version="1.1"

FAVORITES_FILE = "favorites.json"
WATCH_HISTORY_FILE = "watch_history.json"
SETTINGS_FILE = "setting.ini"

# Define a custom event for progress updates using the modern way
DownloadEvent, EVT_DOWNLOAD_UPDATE = wx.lib.newevent.NewEvent()

class SettingsDialog(wx.Dialog):
    def __init__(self, parent, current_settings):
        super().__init__(parent, title="Settings", size=(500, 350))
        self.settings = current_settings
        self.init_ui()
        self.Centre()

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Tab control for settings
        self.settings_notebook = wx.Notebook(panel)
        self.general_page = wx.Panel(self.settings_notebook)
        self.speech_page = wx.Panel(self.settings_notebook)
        
        self.settings_notebook.AddPage(self.general_page, "General")
        self.settings_notebook.AddPage(self.speech_page, "Speech Recognition")

        # --- General Page ---
        gen_vbox = wx.BoxSizer(wx.VERTICAL)
        sb_gen = wx.StaticBox(self.general_page, label="General Settings")
        sb_gen_sizer = wx.StaticBoxSizer(sb_gen, wx.VERTICAL)

        hbox_dir = wx.BoxSizer(wx.HORIZONTAL)
        dir_label = wx.StaticText(self.general_page, label="Download Directory:")
        self.dir_input = wx.TextCtrl(self.general_page, value=self.settings.get('General', 'download_dir'))
        browse_btn = wx.Button(self.general_page, label="Browse...")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)

        hbox_dir.Add(dir_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox_dir.Add(self.dir_input, 1, wx.EXPAND | wx.RIGHT, 5)
        hbox_dir.Add(browse_btn, 0)
        sb_gen_sizer.Add(hbox_dir, 0, wx.EXPAND | wx.ALL, 10)
        gen_vbox.Add(sb_gen_sizer, 1, wx.EXPAND | wx.ALL, 10)
        self.general_page.SetSizer(gen_vbox)

        # --- Speech Page ---
        speech_vbox = wx.BoxSizer(wx.VERTICAL)
        sb_speech = wx.StaticBox(self.speech_page, label="Voice Settings")
        sb_speech_sizer = wx.StaticBoxSizer(sb_speech, wx.VERTICAL)

        hbox_lang = wx.BoxSizer(wx.HORIZONTAL)
        lang_label = wx.StaticText(self.speech_page, label="Recognition Language:")
        self.lang_choices = {
            "Tiếng Việt (vi-VN)": "vi-VN",
            "English (en-US)": "en-US",
            "Japanese (ja-JP)": "ja-JP",
            "Korean (ko-KR)": "ko-KR",
            "French (fr-FR)": "fr-FR"
        }
        self.lang_list = list(self.lang_choices.keys())
        current_lang_code = self.settings.get('Speech', 'language', fallback='vi-VN')
        
        # Find index of current language
        current_idx = 0
        for i, code in enumerate(self.lang_choices.values()):
            if code == current_lang_code:
                current_idx = i
                break
        
        self.lang_combo = wx.ComboBox(self.speech_page, choices=self.lang_list, style=wx.CB_READONLY)
        self.lang_combo.SetSelection(current_idx)

        hbox_lang.Add(lang_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox_lang.Add(self.lang_combo, 1, wx.EXPAND | wx.ALL, 5)
        sb_speech_sizer.Add(hbox_lang, 0, wx.EXPAND | wx.ALL, 10)
        speech_vbox.Add(sb_speech_sizer, 1, wx.EXPAND | wx.ALL, 10)
        self.speech_page.SetSizer(speech_vbox)

        vbox.Add(self.settings_notebook, 1, wx.EXPAND | wx.ALL, 5)

        # Action Buttons
        hbox_btns = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(panel, id=wx.ID_OK, label="OK")
        ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        ok_btn.SetDefault()
        
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="Cancel")
        cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)

        hbox_btns.Add(ok_btn, 1, wx.RIGHT, 10)
        hbox_btns.Add(cancel_btn, 1)
        vbox.Add(hbox_btns, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        panel.SetSizer(vbox)

        # Accessibility
        self.set_accessible_name(self.dir_input, "Download Directory Path")
        self.set_accessible_name(browse_btn, "Browse for folder")
        self.set_accessible_name(self.lang_combo, "Recognition Language")
        self.set_accessible_name(ok_btn, "Save settings and close")
        self.set_accessible_name(cancel_btn, "Cancel changes and close")

    def set_accessible_name(self, control, name):
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def on_browse(self, event):
        default_dir = self.dir_input.GetValue()
        dlg = wx.DirDialog(self, "Choose Download Directory", default_dir, style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            self.dir_input.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_ok(self, event):
        new_dir = self.dir_input.GetValue().strip()
        if not os.path.exists(new_dir):
            try:
                os.makedirs(new_dir)
            except:
                wx.MessageBox("Could not create or access the selected directory. Please choose another one.", "Error", wx.OK | wx.ICON_ERROR)
                return
        
        selected_lang_name = self.lang_combo.GetStringSelection()
        selected_lang_code = self.lang_choices[selected_lang_name]
        
        self.settings['General']['download_dir'] = new_dir
        if 'Speech' not in self.settings:
            self.settings['Speech'] = {}
        self.settings['Speech']['language'] = selected_lang_code
        
        self.EndModal(wx.ID_OK)

    def on_cancel(self, event):
        self.EndModal(wx.ID_CANCEL)

class TeTubeFrame(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Te_Tube, version: "+version, size=(800, 600))
        
        self.results = []
        self.favorites = self.load_data(FAVORITES_FILE)
        self.history = self.load_data(WATCH_HISTORY_FILE)
        self.load_settings()
        self.last_clipboard_text = ""
        self.is_listening = False
        
        self.init_ui()
        self.Centre()
        
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_down)

        self.clipboard_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_check_clipboard, self.clipboard_timer)
        self.clipboard_timer.Start(1000)
        
        wx.CallAfter(self.check_for_app_updates)

    def load_settings(self):
        self.config = configparser.ConfigParser()
        if os.path.exists(SETTINGS_FILE):
            self.config.read(SETTINGS_FILE, encoding='utf-8')
        
        if 'General' not in self.config:
            self.config['General'] = {}
        if 'download_dir' not in self.config['General']:
            self.config['General']['download_dir'] = get_default_download_dir()
            
        if 'Speech' not in self.config:
            self.config['Speech'] = {}
        if 'language' not in self.config['Speech']:
            self.config['Speech']['language'] = 'vi-VN'
            
        self.save_settings()

    def save_settings(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def on_settings(self, event):
        dlg = SettingsDialog(self, self.config)
        if dlg.ShowModal() == wx.ID_OK:
            self.save_settings()
        dlg.Destroy()

    def set_accessible_name(self, control, name):
        control.SetName(name)
        acc = control.GetAccessible()
        if acc:
            acc.SetName(name)

    def check_for_app_updates(self):
        latest = get_latest_version()
        if latest and latest != version:
            msg = f"A new version is available!\n\nCurrent version: {version}\nLatest version: {latest}\n\nDo you want to update now?"
            dlg = wx.MessageDialog(self, msg, "Software Update", wx.YES_NO | wx.ICON_INFORMATION)
            if dlg.ShowModal() == wx.ID_YES:
                if run_updater():
                    self.Close()
                else:
                    wx.MessageBox("Failed to launch updater.bat.", "Error", wx.OK | wx.ICON_ERROR)
            dlg.Destroy()

    def init_ui(self):
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel)
        self.search_tab = wx.Panel(self.notebook)
        self.favorite_tab = wx.Panel(self.notebook)
        self.history_tab = wx.Panel(self.notebook)
        self.process_link_tab = wx.Panel(self.notebook)
        
        self.notebook.AddPage(self.search_tab, "Search")
        self.notebook.AddPage(self.favorite_tab, "Favorite Videos")
        self.notebook.AddPage(self.history_tab, "Watch History")
        self.notebook.AddPage(self.process_link_tab, "Process via link")
        self.help_tab = wx.Panel(self.notebook)
        self.notebook.AddPage(self.help_tab, "Help")

        self.setup_search_tab()
        self.setup_favorite_tab()
        self.setup_history_tab()
        self.setup_process_link_tab()
        self.setup_help_tab()

        vbox.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(vbox)
        self.setup_menu_bar()

    def setup_menu_bar(self):
        menubar = wx.MenuBar()
        main_menu = wx.Menu()
        
        open_dir_item = main_menu.Append(wx.ID_ANY, "&Open download folder\tCtrl+D")
        self.Bind(wx.EVT_MENU, self.on_open_download_folder, open_dir_item)
        
        settings_item = main_menu.Append(wx.ID_ANY, "&Settings\tF4")
        self.Bind(wx.EVT_MENU, self.on_settings, settings_item)
        
        voice_search_item = main_menu.Append(wx.ID_ANY, "&Voice Search\tCtrl+Shift+V")
        self.Bind(wx.EVT_MENU, self.on_voice_search, voice_search_item)
        
        check_update_item = main_menu.Append(wx.ID_ANY, "Check for &updates")
        self.Bind(wx.EVT_MENU, self.on_manual_check_updates, check_update_item)
        
        main_menu.AppendSeparator()
        help_item = main_menu.Append(wx.ID_ANY, "H&elp\tF1")
        self.Bind(wx.EVT_MENU, self.on_help_menu, help_item)
        main_menu.AppendSeparator()
        exit_item = main_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        
        menubar.Append(main_menu, "&Main")
        self.SetMenuBar(menubar)

    def on_open_download_folder(self, event):
        download_dir = self.config['General']['download_dir']
        if not os.path.exists(download_dir):
            try:
                os.makedirs(download_dir)
            except:
                wx.MessageBox("Could not access or create the download directory.", "Error", wx.OK | wx.ICON_ERROR)
                return
        os.startfile(download_dir)

    def on_manual_check_updates(self, event):
        self.SetTitle("Checking for updates...")
        latest = get_latest_version()
        self.SetTitle(f"Te_Tube, version: {version}")
        if latest:
            if latest != version:
                msg = f"A new version is available!\n\nCurrent version: {version}\nLatest version: {latest}\n\nDo you want to update now?"
                dlg = wx.MessageDialog(self, msg, "Software Update", wx.YES_NO | wx.ICON_INFORMATION)
                if dlg.ShowModal() == wx.ID_YES:
                    if run_updater(): self.Close()
                    else: wx.MessageBox("Failed to launch updater.bat.", "Error", wx.OK | wx.ICON_ERROR)
                dlg.Destroy()
            else:
                wx.MessageBox(f"You are using the latest version (v{version}).", "Software Update", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("Could not check for updates.", "Update Error", wx.OK | wx.ICON_ERROR)

    def on_exit(self, event):
        self.Close()

    def setup_search_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        search_label = wx.StaticText(self.search_tab, label="Search Query:")
        self.search_input = wx.TextCtrl(self.search_tab, style=wx.TE_PROCESS_ENTER)
        self.search_input.SetHint("Enter keywords here...")
        self.search_input.Bind(wx.EVT_TEXT_ENTER, self.on_search)
        self.set_accessible_name(self.search_input, "Search YouTube")
        
        search_button = wx.Button(self.search_tab, label="Search")
        search_button.Bind(wx.EVT_BUTTON, self.on_search)
        self.set_accessible_name(search_button, "Search")
        
        # Voice search button
        self.voice_button = wx.Button(self.search_tab, label="Voice Search")
        self.voice_button.Bind(wx.EVT_BUTTON, self.on_voice_search)
        self.set_accessible_name(self.voice_button, "Voice Search (Ctrl+Shift+V)")

        hbox1.Add(search_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox1.Add(self.search_input, 1, wx.EXPAND | wx.ALL, 5)
        hbox1.Add(search_button, 0, wx.ALL, 5)
        hbox1.Add(self.voice_button, 0, wx.ALL, 5)
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 5)

        self.result_list = wx.ListBox(self.search_tab, style=wx.LB_SINGLE)
        self.result_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play)
        self.result_list.Bind(wx.EVT_CONTEXT_MENU, self.on_context_menu)
        self.set_accessible_name(self.result_list, "Search Results")
        vbox.Add(self.result_list, 1, wx.EXPAND | wx.ALL, 5)
        self.search_tab.SetSizer(vbox)

    def on_voice_search(self, event):
        if self.is_listening:
            return
            
        self.is_listening = True
        self.voice_button.SetLabel("Listening...")
        self.SetTitle("Listening for voice search...")
        
        def do_speech():
            r = sr.Recognizer()
            lang = self.config.get('Speech', 'language', fallback='vi-VN')
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = r.listen(source, timeout=5, phrase_time_limit=10)
                    text = r.recognize_google(audio, language=lang)
                    
                    def update_ui():
                        self.search_input.SetValue(text)
                        self.on_search(None)
                    
                    wx.CallAfter(update_ui)
                except sr.UnknownValueError:
                    wx.CallAfter(lambda: wx.MessageBox("Google Speech Recognition could not understand audio", "Voice Error", wx.OK | wx.ICON_WARNING))
                except sr.RequestError as e:
                    wx.CallAfter(lambda: wx.MessageBox(f"Could not request results from Google Speech Recognition service; {e}", "Voice Error", wx.OK | wx.ICON_ERROR))
                except Exception as e:
                    wx.CallAfter(lambda: wx.MessageBox(f"Speech error: {e}", "Voice Error", wx.OK | wx.ICON_ERROR))
                finally:
                    def reset_ui():
                        self.is_listening = False
                        self.voice_button.SetLabel("Voice Search")
                        self.SetTitle(f"Te_Tube, version: {version}")
                    wx.CallAfter(reset_ui)
        
        threading.Thread(target=do_speech, daemon=True).start()

    def setup_process_link_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        link_label = wx.StaticText(self.process_link_tab, label="Enter link video:")
        self.link_input = wx.TextCtrl(self.process_link_tab, style=wx.TE_PROCESS_ENTER)
        self.link_input.SetHint("Paste YouTube link here...")
        self.set_accessible_name(self.link_input, "Enter link video")
        hbox1.Add(link_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        hbox1.Add(self.link_input, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(hbox1, 0, wx.EXPAND | wx.ALL, 10)
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

    def setup_help_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self.help_tab, label="Help Documentation")
        self.set_accessible_name(label, "Help Documentation")
        vbox.Add(label, 0, wx.ALL | wx.CENTER, 10)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        self.help_file_list = wx.ListBox(self.help_tab, style=wx.LB_SINGLE)
        self.help_file_list.Bind(wx.EVT_LISTBOX, self.on_help_file_select)
        self.set_accessible_name(self.help_file_list, "Documentation Files")
        hbox.Add(self.help_file_list, 1, wx.EXPAND | wx.ALL, 5)
        viewer_vbox = wx.BoxSizer(wx.VERTICAL)
        content_label = wx.StaticText(self.help_tab, label="Content:")
        self.set_accessible_name(content_label, "Content")
        viewer_vbox.Add(content_label, 0, wx.LEFT | wx.TOP, 5)
        self.help_viewer = wx.TextCtrl(self.help_tab, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH)
        self.set_accessible_name(self.help_viewer, "Content")
        viewer_vbox.Add(self.help_viewer, 1, wx.EXPAND | wx.ALL, 5)
        hbox.Add(viewer_vbox, 2, wx.EXPAND)
        vbox.Add(hbox, 1, wx.EXPAND)
        btn_hbox = wx.BoxSizer(wx.HORIZONTAL)
        return_btn = wx.Button(self.help_tab, label="&Return")
        return_btn.Bind(wx.EVT_BUTTON, self.on_help_return)
        self.set_accessible_name(return_btn, "Return to Search")
        close_file_btn = wx.Button(self.help_tab, label="&Close File")
        close_file_btn.Bind(wx.EVT_BUTTON, self.on_help_close_file)
        self.set_accessible_name(close_file_btn, "Clear text viewer")
        btn_hbox.Add(return_btn, 1, wx.ALL | wx.EXPAND, 5)
        btn_hbox.Add(close_file_btn, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(btn_hbox, 0, wx.EXPAND | wx.ALL, 5)
        self.help_tab.SetSizer(vbox)
        self.update_help_file_list()

    def update_help_file_list(self):
        self.help_file_list.Clear()
        docks_path = os.path.join(os.getcwd(), "docks")
        if not os.path.exists(docks_path): return
        files = [f for f in os.listdir(docks_path) if f.lower().endswith(".txt")]
        for f in sorted(files):
            display_name = f[:-4] if f.lower().endswith(".txt") else f
            self.help_file_list.Append(display_name)

    def on_help_menu(self, event):
        page_count = self.notebook.GetPageCount()
        for i in range(page_count):
            if self.notebook.GetPageText(i) == "Help":
                self.notebook.SetSelection(i)
                self.update_help_file_list()
                if self.help_file_list.GetCount() > 0: self.help_file_list.SetFocus()
                break

    def on_help_file_select(self, event):
        selection = self.help_file_list.GetSelection()
        if selection == wx.NOT_FOUND: return
        filename = self.help_file_list.GetString(selection)
        filepath = os.path.join(os.getcwd(), "docks", filename + ".txt")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                self.help_viewer.SetValue(content)
        except Exception as e: wx.MessageBox(f"Error reading file: {e}", "Error", wx.OK | wx.ICON_ERROR)

    def on_help_return(self, event): self.notebook.SetSelection(0)
    def on_help_close_file(self, event):
        self.help_viewer.Clear()
        self.help_file_list.SetFocus()

    def setup_favorite_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.favorite_list = wx.ListBox(self.favorite_tab, style=wx.LB_SINGLE)
        self.favorite_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play_favorite)
        self.favorite_list.Bind(wx.EVT_CONTEXT_MENU, self.on_favorite_context_menu)
        self.set_accessible_name(self.favorite_list, "Favorite Videos List")
        vbox.Add(self.favorite_list, 1, wx.EXPAND | wx.ALL, 5)
        self.clear_favorites_btn = wx.Button(self.favorite_tab, label="Clear All Favorites")
        self.clear_favorites_btn.Bind(wx.EVT_BUTTON, self.on_clear_favorites)
        self.set_accessible_name(self.clear_favorites_btn, "Clear all favorite videos")
        vbox.Add(self.clear_favorites_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.favorite_tab.SetSizer(vbox)
        self.update_favorite_listbox()

    def setup_history_tab(self):
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.history_list = wx.ListBox(self.history_tab, style=wx.LB_SINGLE)
        self.history_list.Bind(wx.EVT_LISTBOX_DCLICK, self.on_play_history)
        self.history_list.Bind(wx.EVT_CONTEXT_MENU, self.on_history_context_menu)
        self.set_accessible_name(self.history_list, "Watch History List")
        vbox.Add(self.history_list, 1, wx.EXPAND | wx.ALL, 5)
        self.clear_history_btn = wx.Button(self.history_tab, label="Clear All History")
        self.clear_history_btn.Bind(wx.EVT_BUTTON, self.on_clear_history)
        self.set_accessible_name(self.clear_history_btn, "Clear all watch history")
        vbox.Add(self.clear_history_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
        self.history_tab.SetSizer(vbox)
        self.update_history_listbox()

    def on_clear_favorites(self, event):
        if not self.favorites:
            wx.MessageBox("Your favorites list is already empty.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        dlg = wx.MessageDialog(self, "Are you sure you want to clear all favorite videos?", "Confirm Clear All", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.favorites = []
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()
        dlg.Destroy()

    def on_clear_history(self, event):
        if not self.history:
            wx.MessageBox("Your watch history is already empty.", "Info", wx.OK | wx.ICON_INFORMATION)
            return
        dlg = wx.MessageDialog(self, "Are you sure you want to clear all watch history?", "Confirm Clear All", wx.YES_NO | wx.ICON_QUESTION)
        if dlg.ShowModal() == wx.ID_YES:
            self.history = []
            self.save_data(WATCH_HISTORY_FILE, self.history)
            self.update_history_listbox()
        dlg.Destroy()

    def load_data(self, filename):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f: return json.load(f)
            except: return []
        return []

    def save_data(self, filename, data):
        with open(filename, "w", encoding="utf-8") as f: json.dump(data, f, indent=4, ensure_ascii=False)

    def update_favorite_listbox(self):
        self.favorite_list.Clear()
        for item in self.favorites:
            display_text = f"{item['title']} - {item.get('uploader', 'Unknown')}"
            self.favorite_list.Append(display_text)

    def update_history_listbox(self):
        self.history_list.Clear()
        for item in reversed(self.history):
            display_text = f"{item['title']} - {item.get('uploader', 'Unknown')}"
            self.history_list.Append(display_text)

    def add_to_history(self, video_data):
        self.history = [h for h in self.history if h['url'] != video_data['url']]
        self.history.append(video_data)
        if len(self.history) > 100: self.history.pop(0)
        self.save_data(WATCH_HISTORY_FILE, self.history)
        wx.CallAfter(self.update_history_listbox)

    def on_search(self, event):
        query = self.search_input.GetValue()
        if not query: return
        self.SetTitle(f"Searching for '{query}'...")
        self.result_list.Clear()
        try:
            self.results = search_youtube(query)
            for item in self.results:
                display_text = f"{item['title']} [{item['duration']}] - {item['uploader']}"
                self.result_list.Append(display_text)
        except Exception as e: wx.MessageBox(f"Error during search: {e}", "Search Error", wx.OK | wx.ICON_ERROR)
        self.SetTitle("Te_Tube, version: "+version)
        if self.result_list.GetCount() > 0:
            self.result_list.SetSelection(0)
            self.result_list.SetFocus()

    def on_play(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            self.play_url(video_data['url'])
            self.add_to_history(video_data)

    def on_play_audio(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            self.play_url(video_data['url'], audio_only=True)
            self.add_to_history(video_data)

    def on_play_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url: return
        self.play_url(url)
        self.add_to_history({'title': 'Video from link', 'url': url, 'uploader': 'Unknown'})

    def on_play_link_audio(self, event):
        url = self.link_input.GetValue().strip()
        if not url: return
        self.play_url(url, audio_only=True)
        self.add_to_history({'title': 'Video from link', 'url': url, 'uploader': 'Unknown'})

    def play_url(self, url, audio_only=False):
        try: play_video(url, audio_only=audio_only)
        except Exception as e: wx.MessageBox(f"Error playing video: {e}", "Playback Error", wx.OK | wx.ICON_ERROR)

    def on_key_down(self, event):
        keycode = event.GetKeyCode()
        if keycode in [wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER]:
            focused = wx.Window.FindFocus()
            if focused == self.result_list: self.on_play(None); return
            elif focused == self.favorite_list: self.on_play_favorite(None); return
            elif focused == self.history_list: self.on_play_history(None); return
            elif focused == self.search_input: event.Skip(); return
        event.Skip()

    def on_check_clipboard(self, event):
        if not wx.TheClipboard.Open(): return
        text_data = wx.TextDataObject()
        success = wx.TheClipboard.GetData(text_data)
        wx.TheClipboard.Close()
        if success:
            clipboard_text = text_data.GetText().strip()
            if clipboard_text and clipboard_text != self.last_clipboard_text:
                focused = wx.Window.FindFocus()
                if isinstance(focused, wx.TextCtrl): self.last_clipboard_text = clipboard_text; return
                youtube_regex = r'(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/)?([a-zA-Z0-9_-]{11})'
                if re.search(youtube_regex, clipboard_text):
                    self.last_clipboard_text = clipboard_text
                    self.show_link_detected_dialog(clipboard_text)
                else: self.last_clipboard_text = clipboard_text

    def show_link_detected_dialog(self, url):
        dialog = LinkDetectedDialog(self, url)
        result = dialog.ShowModal()
        if result == wx.ID_YES: self.play_url(url)
        elif result == wx.ID_SAVE: self.on_download_link_from_url(url)
        dialog.Destroy()

    def on_download_link_from_url(self, url):
        menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        for label, fmt in formats:
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.start_download(url, "Video from clipboard", f), item)
        self.PopupMenu(menu)
        menu.Destroy()

    def on_copy_link(self, event):
        focused = wx.Window.FindFocus()
        source_list = None
        source_data = []
        if focused == self.result_list: source_list = self.result_list; source_data = self.results
        elif focused == self.favorite_list: source_list = self.favorite_list; source_data = self.favorites
        elif focused == self.history_list: source_list = self.history_list; source_data = list(reversed(self.history))
        if not source_list: return
        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = source_data[selection]['url']
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(video_url))
                wx.TheClipboard.Close()
                self.last_clipboard_text = video_url
                wx.MessageBox("Link copied to clipboard!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_open_in_browser(self, event):
        focused = wx.Window.FindFocus()
        source_data = []
        if focused == self.result_list: source_data = self.results
        elif focused == self.favorite_list: source_data = self.favorites
        elif focused == self.history_list: source_data = list(reversed(self.history))
        if not source_data: return
        source_list = focused
        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = source_data[selection]['url']
            webbrowser.open(video_url)

    def on_go_to_channel(self, event):
        focused = wx.Window.FindFocus()
        source_data = []
        if focused == self.result_list: source_data = self.results
        elif focused == self.favorite_list: source_data = self.favorites
        elif focused == self.history_list: source_data = list(reversed(self.history))
        if not source_data: return
        source_list = focused
        selection = source_list.GetSelection()
        if selection != wx.NOT_FOUND:
            item = source_data[selection]
            uploader_url = item.get('uploader_url')
            if uploader_url: webbrowser.open(uploader_url)
            else: wx.MessageBox("Channel URL not available.", "Info", wx.OK | wx.ICON_INFORMATION)

    def on_add_favorite(self, event):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.results[selection]
            if any(f['url'] == video_data['url'] for f in self.favorites): return
            self.favorites.append(video_data)
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()

    def on_remove_favorite(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            del self.favorites[selection]
            self.save_data(FAVORITES_FILE, self.favorites)
            self.update_favorite_listbox()

    def on_remove_history(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            del self.history[actual_index]
            self.save_data(WATCH_HISTORY_FILE, self.history)
            self.update_history_listbox()

    def on_play_favorite(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.favorites[selection]
            self.play_url(video_data['url']); self.add_to_history(video_data)

    def on_play_favorite_audio(self, event):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_data = self.favorites[selection]
            self.play_url(video_data['url'], audio_only=True); self.add_to_history(video_data)

    def on_play_history(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            video_data = self.history[actual_index]
            self.play_url(video_data['url']); self.add_to_history(video_data)

    def on_play_history_audio(self, event):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            video_data = self.history[actual_index]
            self.play_url(video_data['url'], audio_only=True); self.add_to_history(video_data)

    def on_context_menu(self, event):
        selection = self.result_list.GetSelection()
        if selection == wx.NOT_FOUND: return
        menu = wx.Menu()
        menu.Append(wx.ID_ANY, "&Play\tEnter"); self.Bind(wx.EVT_MENU, self.on_play)
        menu.Append(wx.ID_ANY, "Play as &Audio"); self.Bind(wx.EVT_MENU, self.on_play_audio)
        menu.Append(wx.ID_ANY, "Open in &Browser"); self.Bind(wx.EVT_MENU, self.on_open_in_browser)
        menu.Append(wx.ID_ANY, "Go to &Channel"); self.Bind(wx.EVT_MENU, self.on_go_to_channel)
        menu.Append(wx.ID_ANY, "&Copy Link"); self.Bind(wx.EVT_MENU, self.on_copy_link)
        menu.Append(wx.ID_ANY, "&Add Favorite"); self.Bind(wx.EVT_MENU, self.on_add_favorite)
        download_menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        for label, fmt in formats:
            item = download_menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.on_download(f), item)
        menu.AppendSubMenu(download_menu, "&Download")
        self.PopupMenu(menu); menu.Destroy()

    def on_favorite_context_menu(self, event):
        selection = self.favorite_list.GetSelection()
        if selection == wx.NOT_FOUND: return
        menu = wx.Menu()
        menu.Append(wx.ID_ANY, "&Play"); self.Bind(wx.EVT_MENU, self.on_play_favorite)
        menu.Append(wx.ID_ANY, "Play as &Audio"); self.Bind(wx.EVT_MENU, self.on_play_favorite_audio)
        menu.Append(wx.ID_ANY, "Open in &Browser"); self.Bind(wx.EVT_MENU, self.on_open_in_browser)
        menu.Append(wx.ID_ANY, "Go to &Channel"); self.Bind(wx.EVT_MENU, self.on_go_to_channel)
        menu.Append(wx.ID_ANY, "&Copy Link"); self.Bind(wx.EVT_MENU, self.on_copy_link)
        menu.Append(wx.ID_ANY, "&Remove from favorite"); self.Bind(wx.EVT_MENU, self.on_remove_favorite)
        download_menu = wx.Menu()
        for label, fmt in formats: # Warning: formats not defined in this scope
            item = download_menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.on_download_favorite(f), item)
        menu.AppendSubMenu(download_menu, "&Download")
        self.PopupMenu(menu); menu.Destroy()

    def on_history_context_menu(self, event):
        selection = self.history_list.GetSelection()
        if selection == wx.NOT_FOUND: return
        menu = wx.Menu()
        menu.Append(wx.ID_ANY, "&Play"); self.Bind(wx.EVT_MENU, self.on_play_history)
        menu.Append(wx.ID_ANY, "Play as &Audio"); self.Bind(wx.EVT_MENU, self.on_play_history_audio)
        menu.Append(wx.ID_ANY, "Open in &Browser"); self.Bind(wx.EVT_MENU, self.on_open_in_browser)
        menu.Append(wx.ID_ANY, "Go to &Channel"); self.Bind(wx.EVT_MENU, self.on_go_to_channel)
        menu.Append(wx.ID_ANY, "&Copy Link"); self.Bind(wx.EVT_MENU, self.on_copy_link)
        menu.Append(wx.ID_ANY, "&Remove from history"); self.Bind(wx.EVT_MENU, self.on_remove_history)
        download_menu = wx.Menu()
        for label, fmt in formats:
            item = download_menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.on_download_history(f), item)
        menu.AppendSubMenu(download_menu, "&Download")
        self.PopupMenu(menu); menu.Destroy()

    def on_download_favorite(self, fmt):
        selection = self.favorite_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.favorites[selection]['url']; title = self.favorites[selection]['title']
            self.start_download(video_url, title, fmt)

    def on_download_history(self, fmt):
        selection = self.history_list.GetSelection()
        if selection != wx.NOT_FOUND:
            actual_index = len(self.history) - 1 - selection
            video_url = self.history[actual_index]['url']; title = self.history[actual_index]['title']
            self.start_download(video_url, title, fmt)

    def on_download(self, fmt):
        selection = self.result_list.GetSelection()
        if selection != wx.NOT_FOUND:
            video_url = self.results[selection]['url']; title = self.results[selection]['title']
            self.start_download(video_url, title, fmt)

    def on_download_link(self, event):
        url = self.link_input.GetValue().strip()
        if not url: return
        menu = wx.Menu()
        formats = [("MP4 Video", "mp4"), ("M4A Audio", "m4a"), ("MP3 Audio", "mp3"), ("WAV Audio", "wav")]
        for label, fmt in formats:
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda evt, f=fmt: self.start_download(url, "Video from link", f), item)
        self.PopupMenu(menu); menu.Destroy()

    def start_download(self, url, title, fmt):
        download_dir = self.config['General']['download_dir']
        dialog = DownloadProgressDialog(self, title, url, fmt, download_dir)
        dialog.Show()

class DownloadThread(threading.Thread):
    def __init__(self, win, url, fmt, download_dir):
        super().__init__()
        self.win = win; self.url = url; self.fmt = fmt; self.download_dir = download_dir; self.daemon = True
    def run(self):
        try:
            def callback(p): wx.PostEvent(self.win, DownloadEvent(**p))
            final_path = download_media(self.url, self.fmt, callback, self.download_dir)
            wx.PostEvent(self.win, DownloadEvent(status='finished', path=final_path))
        except Exception as e: wx.PostEvent(self.win, DownloadEvent(status='error', error=str(e)))

class DownloadProgressDialog(wx.Dialog):
    def __init__(self, parent, title, url, fmt, download_dir):
        super().__init__(parent, title="Downloading...", size=(400, 180))
        self.video_title = title; self.last_percent = -1
        panel = wx.Panel(self); self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.title_label = wx.StaticText(panel, label=f"Downloading: {title}")
        self.set_accessible_name(self.title_label, f"Downloading: {title}")
        self.gauge = wx.Gauge(panel, range=100, size=(350, 25))
        self.set_accessible_name(self.gauge, "Download progress")
        self.status_label = wx.StaticText(panel, label="Initializing...")
        self.set_accessible_name(self.status_label, "Status: Initializing")
        self.vbox.Add(self.title_label, 0, wx.ALL | wx.EXPAND, 10)
        self.vbox.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 10)
        self.vbox.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 10)
        panel.SetSizer(self.vbox); self.Centre()
        self.Bind(EVT_DOWNLOAD_UPDATE, self.on_update)
        self.thread = DownloadThread(self, url, fmt, download_dir); self.thread.start()
    def set_accessible_name(self, control, name):
        control.SetName(name); acc = control.GetAccessible()
        if acc: acc.SetName(name)
    def on_update(self, event):
        status = event.status
        if status == 'downloading':
            percent = int(event.percent)
            if percent != self.last_percent: self.gauge.SetValue(percent); self.last_percent = percent
            clean_status = event.line.replace('[download]', '').strip()
            self.status_label.SetLabel(clean_status)
        elif status == 'finished':
            self.gauge.SetValue(100); self.status_label.SetLabel("Download Complete!")
            self.set_accessible_name(self.status_label, "Status: Download Complete")
            path = event.path or "Unknown location"
            wx.MessageBox(f"Download complete!\nFile saved at: {path}", "Success", wx.OK | wx.ICON_INFORMATION)
            self.Destroy()
        elif status == 'error':
            error_msg = event.error or "Unknown error"
            wx.MessageBox(f"Download failed: {error_msg}", "Error", wx.OK | wx.ICON_ERROR); self.Destroy()

class LinkDetectedDialog(wx.Dialog):
    def __init__(self, parent, url):
        super().__init__(parent, title="Link Detected", size=(500, 200))
        panel = wx.Panel(self); vbox = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(panel, label=f"We detected a video link in your clipboard:\n\n{url}"); label.Wrap(450)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        play_btn = wx.Button(panel, label="Play"); play_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_YES))
        download_btn = wx.Button(panel, label="Download"); download_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_SAVE))
        cancel_btn = wx.Button(panel, label="Cancel"); cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        hbox.Add(play_btn, 1, wx.ALL | wx.EXPAND, 5); hbox.Add(download_btn, 1, wx.ALL | wx.EXPAND, 5); hbox.Add(cancel_btn, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(label, 1, wx.ALL | wx.EXPAND, 15); vbox.Add(hbox, 0, wx.ALL | wx.EXPAND, 10)
        panel.SetSizer(vbox); self.Centre()
        parent.set_accessible_name(play_btn, "Play video from clipboard")
        parent.set_accessible_name(download_btn, "Download video from clipboard")
        parent.set_accessible_name(cancel_btn, "Cancel and return to main interface")

def start_gui():
    app = wx.App(); frame = TeTubeFrame(); frame.Show(); app.MainLoop()
