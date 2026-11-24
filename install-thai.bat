@echo off
setlocal EnableExtensions EnableDelayedExpansion
title STORY OF SEASONS: Friends of Mineral Town - Thai patch
cd /d "%~dp0"
set "REPO=%~dp0"
echo ============================================================
echo  STORY OF SEASONS: Friends of Mineral Town - Thai patch
echo ============================================================
echo.

rem ---------- 1. Python + Pillow ----------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY ( where python >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo [X] Python 3 was not found. Install it from https://www.python.org/downloads/
  echo     and tick "Add python.exe to PATH" during setup, then run this file again.
  goto :fail
)
%PY% -c "import PIL" >nul 2>&1 || (
  echo Installing Pillow ...
  %PY% -m pip install --user pillow || ( echo [X] Could not install Pillow. & goto :fail )
)

rem ---------- 2. Game folder ----------
set "GAME=%~1"
if not defined GAME for %%G in (
  "C:\Program Files (x86)\Steam\steamapps\common\STORY OF SEASONS Friends of Mineral Town"
  "C:\Program Files\Steam\steamapps\common\STORY OF SEASONS Friends of Mineral Town"
  "C:\Program Files\Epic Games\STORYOFSEASONSFriendsofMineralTown"
  "C:\Program Files\Epic Games\STORY OF SEASONS Friends of Mineral Town"
) do if not defined GAME if exist "%%~G\disc" set "GAME=%%~G"
if not defined GAME (
  echo Game folder not found automatically.
  echo Drag the game folder ^(the one that contains the file "disc"^) into this window, then press Enter:
  set /p "GAME="
)
set "GAME=!GAME:"=!"
if "!GAME:~-1!"=="\" set "GAME=!GAME:~0,-1!"
if not exist "!GAME!\disc" ( echo [X] "!GAME!\disc" not found. & goto :fail )
echo Game folder : !GAME!

rem ---------- 3. Toolkit folder ----------
set "TK=%~2"
if not defined TK for /d %%T in ("!GAME!\sos-fomt_disc-toolkit*" "%REPO%sos-fomt_disc-toolkit*" "%REPO%..\sos-fomt_disc-toolkit*") do if not defined TK if exist "%%~fT\unpack-encrypted-disc.bat" set "TK=%%~fT"
if not defined TK (
  echo Toolkit folder not found automatically.
  echo Drag the "sos-fomt_disc-toolkit" folder into this window, then press Enter:
  set /p "TK="
)
set "TK=!TK:"=!"
if "!TK:~-1!"=="\" set "TK=!TK:~0,-1!"
if not exist "!TK!\unpack-encrypted-disc.bat" ( echo [X] "!TK!" is not the disc toolkit folder. & goto :fail )
echo Toolkit     : !TK!
echo.

rem ---------- 4. Original disc (backed up once) ----------
rem Uses disc.original in the game folder. If it is missing, the toolkit's
rem __disc-in\disc is used when present, otherwise the current game disc.
if not exist "!GAME!\disc.original" (
  set "SRC=!GAME!\disc"
  if exist "!TK!\__disc-in\disc" set "SRC=!TK!\__disc-in\disc"
  echo Backing up the original disc to disc.original ...
  copy /y "!SRC!" "!GAME!\disc.original" >nul || ( echo [X] Backup failed. & goto :fail )
)

rem ---------- 5. Build the Thai disc ----------
rem Only the 2 files the mod changes are unpacked and rebuilt; every other
rem file is copied unchanged from disc.original. See tools\build_disc.py
%PY% "%REPO%tools\build_disc.py" --toolkit "!TK!" --original "!GAME!\disc.original" --out "!GAME!\disc" || goto :fail

echo.
echo ============================================================
echo  Done! Start the game with the language set to English.
echo  To remove the patch, run uninstall-thai.bat
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Installation stopped. The game disc was not changed ^(only disc.original may have been created^).
pause
exit /b 1
