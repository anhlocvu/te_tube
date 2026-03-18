import configparser
import os

SETTINGS_FILE = "settings.ini"

# Default download folder: C:\Users\<Username>\Downloads\te_tube
DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "te_tube")

def get_default_settings():
    config = configparser.ConfigParser()
    config['General'] = {
        'download_dir': DEFAULT_DOWNLOAD_DIR
    }
    config['VoiceSearch'] = {
        'language': 'vi-VN' # Default to Vietnamese
    }
    return config

def load_settings():
    config = configparser.ConfigParser()
    if os.path.exists(SETTINGS_FILE):
        config.read(SETTINGS_FILE, encoding='utf-8')
        # Ensure all required sections/keys exist
        default = get_default_settings()
        for section in default.sections():
            if section not in config:
                config[section] = default[section]
            else:
                for key in default[section]:
                    if key not in config[section]:
                        config[section][key] = default[section][key]
    else:
        config = get_default_settings()
        save_settings(config)
    return config

def save_settings(config):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        config.write(f)

def get_download_dir():
    config = load_settings()
    path = config.get('General', 'download_dir', fallback=DEFAULT_DOWNLOAD_DIR)
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except:
            return DEFAULT_DOWNLOAD_DIR # Fallback to default if cannot create
    return path

def get_voice_language():
    config = load_settings()
    return config.get('VoiceSearch', 'language', fallback='vi-VN')
