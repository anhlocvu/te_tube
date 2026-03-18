@echo off
title "start building"
uv run -m nuitka --standalone --windows-console-mode=disable --lto=yes --remove-output --include-package=pyaudio --include-package=speech_recognition --include-package-data=speech_recognition --company-name="technology entertainment" --product-name="te_tube" --file-version="1.3" --product-version="1.3" --file-description="download, search, and listen to multimedia on YouTube" -o "te_tube.exe" main.py
xcopy "lib" "main.dist/lib" /E /I /Y
xcopy "updater" "main.dist" /E /I /Y
cls
title "Build successful"
pause