import requests
import os

VERSION_URL = "https://raw.githubusercontent.com/anhlocvu/te_tube/main/updater/version.txt"

def get_latest_version():
    """
    Fetches the latest version number from the GitHub repository.
    Returns the version string or None if it fails.
    """
    try:
        response = requests.get(VERSION_URL, timeout=10)
        response.raise_for_status()
        return response.text.strip()
    except Exception as e:
        print(f"Error checking for app updates: {e}")
        return None

def run_updater():
    """
    Launches the updater.bat script and exits the current process.
    """
    updater_path = os.path.join(os.getcwd(), "updater.bat")
    if os.path.exists(updater_path):
        # Use os.startfile on Windows to run the batch file and decouple it
        os.startfile(updater_path)
        return True
    return False
