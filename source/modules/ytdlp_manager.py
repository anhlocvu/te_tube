import os
import subprocess
import requests
import sys

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
YTDLP_PATH = os.path.join(os.getcwd(), "lib", "yt-dlp.exe")

def ensure_ytdlp():
    """
    Ensures yt-dlp.exe exists and is updated.
    """
    if not os.path.exists(YTDLP_PATH):
        print("yt-dlp.exe not found. Downloading the latest version...")
        download_ytdlp()
    else:
        print("yt-dlp.exe found. Checking for updates...")
        update_ytdlp()

def download_ytdlp():
    try:
        response = requests.get(YTDLP_URL, stream=True)
        response.raise_for_status()
        with open(YTDLP_PATH, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print("yt-dlp.exe downloaded successfully.")
    except Exception as e:
        print(f"Error downloading yt-dlp.exe: {e}")
        sys.exit(1)

def update_ytdlp():
    try:
        # Run yt-dlp -U to update itself
        subprocess.run([YTDLP_PATH, "-U"], check=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        print("yt-dlp.exe is up to date.")
    except Exception as e:
        print(f"Error updating yt-dlp.exe: {e}")

if __name__ == "__main__":
    ensure_ytdlp()
