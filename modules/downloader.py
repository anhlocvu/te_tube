import subprocess
import os
import re

YTDLP_PATH = os.path.join(os.getcwd(), "lib", "yt-dlp.exe")
DOWNLOAD_DIR = os.path.join(os.getcwd(), "download")

def download_media(url, format_type='mp4', progress_callback=None):
    """
    Downloads media from URL in specified format.
    progress_callback: function(data) where data is a dict with progress info.
    returns: The path to the downloaded file.
    """
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        
    output_template = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    
    cmd = [YTDLP_PATH, "-o", output_template, "--newline", "--progress"]
    
    if format_type == 'mp3':
        cmd += ["-f", "bestaudio", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"]
    elif format_type == 'm4a':
        cmd += ["-f", "bestaudio[ext=m4a]"]
    elif format_type == 'wav':
        cmd += ["-f", "bestaudio", "--extract-audio", "--audio-format", "wav"]
    elif format_type == 'mp4':
        cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"]
    
    # Add ffmpeg path from lib folder
    cmd += ["--ffmpeg-location", os.path.join(os.getcwd(), "lib")]
    cmd += [url]
    
    try:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        
        final_path = None
        
        for line in process.stdout:
            # Parse progress: [download]  10.0% of 100.00MiB at 1.00MiB/s ETA 01:30
            if '[download]' in line:
                percent_match = re.search(r'(\d+\.\d+)%', line)
                if percent_match:
                    percent = float(percent_match.group(1))
                    if progress_callback:
                        progress_callback({'status': 'downloading', 'percent': percent, 'line': line.strip()})
            
            # Look for the destination file
            if '[download] Destination:' in line:
                final_path = line.split('Destination:')[1].strip()
            elif 'has already been downloaded' in line:
                # [download] d:\python code\te_tube\download\Video Title.mp4 has already been downloaded
                match = re.search(r'\[download\] (.*) has already been downloaded', line)
                if match:
                    final_path = match.group(1).strip()
            elif '[ExtractAudio] Destination:' in line:
                final_path = line.split('Destination:')[1].strip()

        process.wait()
        
        if process.returncode == 0:
            return final_path
        else:
            raise Exception(f"yt-dlp exited with code {process.returncode}")
            
    except Exception as e:
        print(f"Error during download: {e}")
        raise e

if __name__ == "__main__":
    def my_callback(p):
        print(f"Progress: {p['percent']}%")
        
    # test_url = "https://www.youtube.com/watch?v=aqvZeN-r_t4"
    # path = download_media(test_url, 'mp3', my_callback)
    # print(f"Downloaded to: {path}")
    pass
