## TE_TUBE TROUBLESHOOTING

If you encounter issues while using Te_Tube, please check the following common solutions.

### 1. Video won't play or search fails

- Internet Connection: Ensure you have a stable internet connection.
- yt-dlp Update: YouTube frequently changes its internal structure. Te_Tube tries to update yt-dlp automatically, but you can try restarting the app to trigger a fresh check.
- Firewall and Antivirus: Ensure that te_tube.exe and lib/yt-dlp.exe are allowed to access the internet.

### 2. No Sound or Video

- Driver Issues: Ensure your audio and video drivers are up to date.
- Missing DLLs: Make sure all files in the lib folder (like avcodec-61.dll, libmpv-2.dll) are present. Do not move or delete the lib folder.

### 3. Screen Reader (NVDA) not reading lists

- Focus: Sometimes the focus might get lost. Press Tab or Shift + Tab to cycle through controls until you hear the list name.
- Compatibility: Te_Tube is optimized for NVDA. Ensure your screen reader is active before starting the software.

### 4. Download Fails

- Disk Space: Check if you have enough space on your drive.
- File Permissions: Ensure the download folder is not set to Read-Only.
- Filename Issues: Some video titles contain characters that Windows doesn't allow in filenames. The software tries to clean these, but extremely long titles might still cause issues.

### 5. Updater Error
- If the updater fails to launch, ensure updater.bat is present in the main directory. You can also manually download the latest version from the official repository.