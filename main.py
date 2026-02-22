import os
import sys
from modules.ytdlp_manager import ensure_ytdlp
from modules.gui import start_gui



def main():
    # Ensure dependencies in lib folder are accessible
    lib_path = os.path.join(os.getcwd(), "lib")
    if lib_path not in os.environ["PATH"]:
        os.environ["PATH"] = lib_path + os.pathsep + os.environ["PATH"]

    print("--- Te_Tube Startup ---")
    
    # Check/Update yt-dlp first as requested
    try:
        ensure_ytdlp()
    except Exception as e:
        print(f"Error initializing yt-dlp: {e}")
        # We might still want to start the GUI, but downloads won't work.
        # However, the user said "sau đó mới vào phần mềm", implying it's required.

    # Start the GUI
    start_gui()

if __name__ == "__main__":
    main()
