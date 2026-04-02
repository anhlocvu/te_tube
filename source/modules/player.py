import os
import mpv
import threading
import time

def _player_worker(url, audio_only, on_start_callback):
    """
    Worker thread for mpv playback.
    """
    player = None
    try:
        # Add 'lib' to PATH so MPV can easily find yt-dlp.exe
        lib_dir = os.path.abspath(os.path.join(os.getcwd(), "lib"))
        if lib_dir not in os.environ["PATH"]:
            os.environ["PATH"] = lib_dir + os.pathsep + os.environ["PATH"]

        # Create MPV instance with robust options for Windows
        player = mpv.MPV(
            ytdl=True,
            ytdl_format="best",
            input_default_bindings=True, # This handles 'f', 'Space', etc. automatically
            input_vo_keyboard=True,      # Crucial for Windows to receive keys
            osc=True,
            scripts=True
        )
        
        if audio_only:
            player['vid'] = 'no'         # Correct way to disable video
            player['force-window'] = 'yes'
        
        player['title'] = "Te_Tube Player"
        
        # Play the URL
        player.play(url)
        
        # Wait for MPV to get video metadata (duration)
        # This is the most reliable way to know yt-dlp has finished loading the stream info
        start_wait = time.time()
        while time.time() - start_wait < 15: # Max wait 15 seconds
            if player.duration is not None and player.duration > 0:
                break
            time.sleep(0.5)
            
        # Give the MPV window a moment to actually manifest on screen
        time.sleep(1.0)
        
        # Inform GUI that playback has successfully started
        if on_start_callback:
            on_start_callback()
        
        # Keep this thread alive as long as playback is active
        player.wait_for_playback()
        
    except Exception as e:
        print(f"Error in player thread: {e}")
        if on_start_callback:
            on_start_callback(error=str(e))
    finally:
        if player:
            try:
                player.terminate()
            except:
                pass

def play_video(url, audio_only=False, on_start_callback=None):
    """
    Plays a YouTube video URL using mpv in a separate thread.
    """
    thread = threading.Thread(target=_player_worker, args=(url, audio_only, on_start_callback), daemon=True)
    thread.start()

if __name__ == "__main__":
    pass
