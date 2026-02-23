import subprocess
import json
import os

YTDLP_PATH = os.path.join(os.getcwd(), "lib", "yt-dlp.exe")

def search_youtube(query, max_results=20):
    """
    Searches YouTube for the given query using yt-dlp.
    Returns a list of dictionaries containing video info.
    """
    cmd = [
        YTDLP_PATH,
        f"ytsearch{max_results}:{query}",
        "--dump-json",
        "--flat-playlist",
        "--quiet"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        videos = []
        for line in result.stdout.splitlines():
            if line.strip():
                data = json.loads(line)
                videos.append({
                    'title': data.get('title', 'Unknown Title'),
                    'url': data.get('url') or f"https://www.youtube.com/watch?v={data.get('id')}",
                    'duration': data.get('duration_string', 'N/A'),
                    'uploader': data.get('uploader', 'Unknown'),
                    'uploader_url': data.get('uploader_url') or data.get('channel_url'),
                    'id': data.get('id')
                })
        return videos
    except Exception as e:
        print(f"Error searching YouTube: {e}")
        return []

if __name__ == "__main__":
    # Test search
    results = search_youtube("Python tutorial", max_results=5)
    for r in results:
        print(f"{r['title']} - {r['url']} ({r['duration']})")
