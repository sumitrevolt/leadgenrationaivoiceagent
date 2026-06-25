@echo off
cd /d "C:\Users\Ratanshila\Documents\leadgenrationaiagent"
set GIT="C:\PROGRA~1\Git\cmd\git.exe"
set SSH="C:\PROGRA~1\Git\usr\bin\ssh.exe"

%GIT% add -A
%GIT% commit -m "voice: fix _clean mid-sentence truncation + fake ? append; expand acks; env defaults for TTS rate + Gemini primary"
%GIT% push origin main

echo Done.
