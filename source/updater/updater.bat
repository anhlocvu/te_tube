@echo off
title "The update is in progress, please do not close this window, otherwise the update will not complete properly."
curl -L -O https://github.com/anhlocvu/te_tube/releases/latest/download/te_tube.zip
powershell Expand-Archive -Path "te_tube.zip" -DestinationPath "."
del te_tube.zip
y
start te_tube.exe