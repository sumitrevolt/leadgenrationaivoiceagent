@echo off
set GIT_TERMINAL_PROMPT=0
cd /d "%~dp0.."
set GIT=C:\PROGRA~1\Git\cmd\git.exe
if exist ".git\index.lock" del /f /q ".git\index.lock" >nul 2>&1
call "%GIT%" add docs/Architecture_Research_RAG_Agents_MCP.md CLAUDE.md scripts/push_research.bat > push_res.log 2>&1
call "%GIT%" commit -m "docs: architecture research - LangGraph supervisor + Qdrant payload-partitioned per-niche RAG + Pipecat + MCP stack (adopt/skip verdicts, roadmap)" >> push_res.log 2>&1
call "%GIT%" push origin main >> push_res.log 2>&1
echo PUSH_EXIT_%ERRORLEVEL% >> push_res.log
echo PR_DONE
