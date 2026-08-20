@echo off
REM ===================================================================
REM  KeepMoney - CIFT TIKLA KURULUM  (ilk kurulum ve onarim)
REM ===================================================================
REM
REM  BU DOSYADA MANTIK YOKTUR. Isi betikler\kurulum.py yapiyor. Sebep:
REM  .bat test edilemez, Python edilebilir (tests/test_kurulum.py). Burada
REM  yalnizca "dogru klasore gec + calisir bir Python bul" adimlari var.
REM
REM  NEDEN TURKCE KARAKTER YOK: bu dosyanin metnini cmd.exe konsolun kod
REM  sayfasiyla okuyor (Turkce Windows'ta cp857). UTF-8 kaydedilmis "i, s,
REM  g" karakterleri hem ekranda bozuk cikar hem de satir ayristirmasini
REM  bozabilir. Turkce mesajlarin tamami Python tarafinda: orada cikti
REM  UTF-8'e sabitleniyor (kurulum.py::_cikti_utf8).
REM
REM  ILK SATIR `cd /d "%~dp0"` OLMAK ZORUNDA. Kullanicinin takildigi yer tam
REM  olarak buydu: yeni pencere C:\WINDOWS\system32 icinde aciliyor ve
REM  hicbir goreli yol tutmuyordu. %~dp0 = bu dosyanin bulundugu klasor.
REM ===================================================================

cd /d "%~dp0"

REM Sistem Python'u: once `py` baslaticisi (Windows'un dogru yolu), sonra
REM `python`. Microsoft Store kisayolu calismadigi icin hata kodu dondurur
REM ve asagidaki kontrole takilir - istedigimiz de bu.
set "PY="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto :calistir

python --version >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto :calistir
goto :pythonyok

:calistir
%PY% betikler\kurulum.py kur
set "KOD=%ERRORLEVEL%"
echo.
pause
exit /b %KOD%

:pythonyok
echo.
echo   Python bulunamadi.
echo.
echo   1^) https://www.python.org/downloads/ adresinden Python 3.12+ kur
echo   2^) Kurulum ekraninda "Add python.exe to PATH" kutusunu ISARETLE
echo   3^) Bu pencereyi kapat, kur.bat dosyasina tekrar cift tikla
echo.
pause
exit /b 1
