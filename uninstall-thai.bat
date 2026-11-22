@echo off
setlocal EnableExtensions EnableDelayedExpansion
title STORY OF SEASONS: Friends of Mineral Town - remove Thai patch
set "GAME=%~1"
if not defined GAME for %%G in (
  "C:\Program Files (x86)\Steam\steamapps\common\STORY OF SEASONS Friends of Mineral Town"
  "C:\Program Files\Steam\steamapps\common\STORY OF SEASONS Friends of Mineral Town"
  "C:\Program Files\Epic Games\STORYOFSEASONSFriendsofMineralTown"
  "C:\Program Files\Epic Games\STORY OF SEASONS Friends of Mineral Town"
) do if not defined GAME if exist "%%~G\disc.original" set "GAME=%%~G"
if not defined GAME (
  echo Drag the game folder into this window, then press Enter:
  set /p "GAME="
)
set "GAME=!GAME:"=!"
if "!GAME:~-1!"=="\" set "GAME=!GAME:~0,-1!"
if not exist "!GAME!\disc.original" (
  echo [X] No backup ^(disc.original^) in "!GAME!".
  echo     Use Steam "Verify integrity of game files" or Epic "Verify" instead.
  pause & exit /b 1
)
copy /y "!GAME!\disc.original" "!GAME!\disc" >nul && echo The original English game has been restored.
pause
