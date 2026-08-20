@echo off
REM ===================================================================
REM  KeepMoney - CIFT TIKLA DURDUR
REM ===================================================================
REM
REM  basla.bat ile acilan API ve tarama worker'ini kapatir.
REM
REM  NEDEN PENCERE BASLIGIYLA DEGIL PID ILE: ilk tasarim
REM  `taskkill /FI "WINDOWTITLE eq KeepMoney API"` idi. Windows 11'de
REM  OLCULDU ve YANLIS CIKTI: konsol penceresinin sahibi Windows Terminal,
REM  yani o baslik python.exe'ye degil WindowsTerminal.exe'ye ait. Komut,
REM  KeepMoney'i degil kullanicinin terminal uygulamasini (acik butun
REM  sekmeleriyle) kapatirdi. Bu yuzden basla.bat surecleri PID'leriyle
REM  data\calisan.json dosyasina yaziyor; kurulum.py oldurmeden once
REM  PID'in hala bizim python'umuz oldugunu dogruluyor.
REM ===================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto :kurulumyok

".venv\Scripts\python.exe" betikler\kurulum.py dur
echo.
pause
exit /b %ERRORLEVEL%

:kurulumyok
echo.
echo   Sanal ortam yok: .venv\Scripts\python.exe bulunamadi.
echo   Kapatilacak bir sey de yok gibi gorunuyor.
echo.
pause
exit /b 1
