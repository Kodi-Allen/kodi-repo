@echo off
REM DiscDB STRM Creator - Batch Wrapper
REM Doppelklick: interaktiver Modus
REM Drag & Drop einer Disc URL: python discdb_strm_creator.py <url> <pfad>

cd /d "%~dp0"

if "%~1"=="" (
    REM Interaktiver Modus
    python discdb_strm_creator.py
) else if "%~2"=="" (
    REM Nur URL angegeben - nach Pfad fragen
    python discdb_strm_creator.py "%~1"
) else (
    REM URL und Pfad angegeben
    python discdb_strm_creator.py "%~1" "%~2"
)
