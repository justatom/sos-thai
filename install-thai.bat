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

rem ---------- 4. Back up the original disc (once) ----------
if not exist "!GAME!\disc.original" (
  echo Backing up the original disc to disc.original ...
  copy /y "!GAME!\disc" "!GAME!\disc.original" >nul || ( echo [X] Backup failed. & goto :fail )
)

rem ---------- 5. Unpack the ORIGINAL disc ----------
echo Unpacking the original game data (this takes a few minutes) ...
for %%D in (__disc-in __disc-out __extracted-files __raw-assets temp) do (
  if exist "!TK!\%%D" rmdir /s /q "!TK!\%%D"
  mkdir "!TK!\%%D"
)
copy /y "!GAME!\disc.original" "!TK!\__disc-in\disc" >nul || goto :fail
pushd "!TK!"
call unpack-encrypted-disc.bat >nul
call extract-assets.bat >nul
popd
if not exist "!TK!\__raw-assets\resource\message\ichigo_message_all_US.lzs.dcmp\msg_System.bin" (
  echo [X] Unpacking failed. Check that disc.original is the untouched game file.
  goto :fail
)

rem ---------- 6. Build the Thai patch ----------
%PY% "%REPO%tools\install_thai.py" --toolkit "!TK!" || goto :fail

rem ---------- 7. Rebuild the disc and install it ----------
rem Only 2 files are changed by the patch. full-rebuild would recompress every
rem asset in the game (animations, maps, ...), so instead we compress, keep just
rem the 2 patched files, restore all other files from the original disc, and pack.
echo Rebuilding the game disc (this takes a few minutes) ...
pushd "!TK!"
call compress-assets.bat >nul 2>&1
popd
if exist "!TK!\_thai_keep" rmdir /s /q "!TK!\_thai_keep"
mkdir "!TK!\_thai_keep"
copy /y "!TK!\__extracted-files\resource\message\ichigo_message_all_US.lzs" "!TK!\_thai_keep\" >nul || goto :fail
copy /y "!TK!\__extracted-files\resource\ui\font_data.lzs" "!TK!\_thai_keep\" >nul || goto :fail
pushd "!TK!"
call unpack-encrypted-disc.bat >nul 2>&1
popd
copy /y "!TK!\_thai_keep\ichigo_message_all_US.lzs" "!TK!\__extracted-files\resource\message\" >nul || goto :fail
copy /y "!TK!\_thai_keep\font_data.lzs" "!TK!\__extracted-files\resource\ui\" >nul || goto :fail
if exist "!TK!\__disc-out\disc" del /q "!TK!\__disc-out\disc"
pushd "!TK!"
call pack-disc.bat >nul 2>&1
popd
if not exist "!TK!\__disc-out\disc" ( echo [X] Rebuild failed. & goto :fail )
copy /y "!TK!\__disc-out\disc" "!GAME!\disc" >nul || ( echo [X] Could not copy the new disc into the game folder. & goto :fail )

echo.
echo ============================================================
echo  Done! Start the game with the language set to English.
echo  To remove the patch, run uninstall-thai.bat
echo ============================================================
pause
exit /b 0

:fail
echo.
echo Installation stopped. Nothing in the game folder was changed except disc.original (backup).
pause
exit /b 1
