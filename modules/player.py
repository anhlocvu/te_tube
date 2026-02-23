import subprocess
import os

FFPLAY_PATH = os.path.join(os.getcwd(), "lib", "ffplay.exe")
YTDLP_PATH = os.path.join(os.getcwd(), "lib", "yt-dlp.exe")

def play_video(url, audio_only=False):
    """
    Plays a YouTube video URL using ffplay and yt-dlp.
    """
    # Use yt-dlp to get the stream URL and pipe it to ffplay
    try:
        # For audio only, we might want bestaudio, otherwise best
        fmt = "bestaudio" if audio_only else "best"
        cmd_get_url = [YTDLP_PATH, "-g", "-f", fmt, url]
        stream_url = subprocess.check_output(cmd_get_url, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW).strip()
        
        # Now play with ffplay
        # Using -showmode 1 (waves) instead of -nodisp to allow keyboard controls
        ffplay_cmd = [FFPLAY_PATH, "-autoexit", "-window_title", f"Playing: {url}", stream_url]
        if audio_only:
            ffplay_cmd.extend(["-showmode", "1"])
            
        subprocess.Popen(ffplay_cmd, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        print(f"Error playing video: {e}")

if __name__ == "__main__":
    # Test play (requires a valid URL)
    # play_video("https://www.youtube.com/watch?v=aqvZeN-r_t4")
    pass
