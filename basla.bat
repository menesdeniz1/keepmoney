@echo off
REM ===================================================================
REM  KeepMoney - CIFT TIKLA CALISTIR
REM ===================================================================
REM
REM  Ne yapar: ortami dogrular, API'yi ve tarama worker'ini AYRI
REM  pencerelerde baslatir, API cevap verince tarayiciyi acar.
REM  Mantik betikler\kurulum.py icinde (bkz. kur.bat basindaki not).
REM
REM  SANAL ORTAM ETKINLESTIRILMIYOR. `.venv\Scripts\Activate.ps1`
REM  PowerShell calistirma politikasina takiliyor ve bu tuzaga iki kez
REM  dusuldu. Etkinlestirmenin tek yaptigi PATH'i degistirmek; biz zaten
REM  python.exe'yi tam yoluyla cagiriyoruz.
REM ===================================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" goto :kurulumyok

".venv\Scripts\python.exe" betikler\kurulum.py basla
set "KOD=%ERRORLEVEL%"
REM Basarili oldugunda pencere kapansin (tarayici zaten acildi); hata
REM varsa DURSUN, yoksa kullanici mesaji okuyamadan pencere kapanir.
if not "%KOD%"=="0" pause
exit /b %KOD%

:kurulumyok
echo.
echo   Sanal ortam yok: .venv\Scripts\python.exe bulunamadi.
echo.
echo   Once kur.bat dosyasina cift tikla (ilk kurulum).
echo.
pause
exit /b 1
