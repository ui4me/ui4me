@echo off
rem Build a pinned LuaJIT 2.1 (MIT licence) into <repo>\build\luajit\ with MSVC.
rem Run from an "x64 Native Tools Command Prompt for VS" (cl.exe on PATH).
rem Result: build\luajit\src\luajit.exe
setlocal
set COMMIT=63c8f1a9b479ba5518cf6a170ff7729178bc3cfd
set SHA256=8cad76f444b76001b7123dc626c5d0bfc24f1f790333737443345f7e6b41bb5f
set ROOT=%~dp0..\..\..
set DEST=%ROOT%\build\luajit
if exist "%DEST%\src\luajit.exe" ( echo already built & exit /b 0 )
set WORK=%TEMP%\ui4me-luajit-%RANDOM%
mkdir "%WORK%" || exit /b 1
curl.exe -fsSL -o "%WORK%\luajit.tar.gz" "https://github.com/LuaJIT/LuaJIT/archive/%COMMIT%.tar.gz" || exit /b 1
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "%WORK%\luajit.tar.gz" SHA256') do ( set GOT=%%H & goto :hashed )
:hashed
set GOT=%GOT: =%
if /I not "%GOT%"=="%SHA256%" ( echo sha256 mismatch: %GOT% & exit /b 1 )
mkdir "%DEST%" || exit /b 1
tar.exe -xzf "%WORK%\luajit.tar.gz" -C "%DEST%" --strip-components=1 || exit /b 1
pushd "%DEST%\src"
call msvcbuild.bat amalg || ( popd & exit /b 1 )
popd
rmdir /s /q "%WORK%"
echo built: %DEST%\src\luajit.exe
"%DEST%\src\luajit.exe" -e "print(jit.version)"
