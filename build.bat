@echo off
title "start building"
uv run -m nuitka --standalone --windows-disable-console --lto=yes --remove-output --company-name="technology entertainment" --product-name="te_tube" --file-version="1.0.0.0" --product-version="1.0.0.0" --file-description="download, search, and listen to multimedia on YouTube" -o "te_tube.exe" main.py
xcopy "lib" "main.dist/lib" /E /I /Y
xcopy "updater.bat" "main.dist/updater.bat" /E /I /Y
cls
title "Build successful"
pause