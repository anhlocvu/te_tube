import os
import mpv
import threading

def _player_worker(url, audio_only):
    """
    Worker thread for mpv playback.
    """
    try:
        # Create MPV instance with appropriate options
        player = mpv.MPV(
            ytdl=True,
            ytdl_format="best",
            input_default_bindings=True,
            input_vo_keyboard=True,
            osc=True
        )
        
        if audio_only:
            player.vid = False
            player['force-window'] = 'yes'
        
        player['title'] = f"Te_Tube: {url}"
        
        # Play the URL
        player.play(url)
        
        # Wait for playback to finish or window to be closed
        # This keeps the player object alive as long as necessary
        player.wait_for_playback()
        
        # Explicitly terminate to be safe
        player.terminate()
        
    except Exception as e:
        print(f"Error in player thread: {e}")

def play_video(url, audio_only=False):
    """
    Plays a YouTube video URL using mpv in a separate thread.
    """
    thread = threading.Thread(target=_player_worker, args=(url, audio_only), daemon=True)
    thread.start()

if __name__ == "__main__":
    pass
