@echo off
cd /d "%~dp0.."
del p12.log 2>nul
echo === PIP INSTALL NEW DEPS === > p12.log
.venv\Scripts\python.exe -m pip install -q "qdrant-client>=1.12.0" "fastembed>=0.4.0" "langgraph>=1.0" "langgraph-checkpoint-sqlite>=2.0" "langchain-core>=0.3" "fastapi-mcp>=0.3" >> p12.log 2>&1
echo PIP_EXIT_%ERRORLEVEL% >> p12.log
echo === IMPORT CHECK === >> p12.log
.venv\Scripts\python.exe -c "from app.main import app; import app.agents as A; print('app OK; agents available:', A.AGENTS_AVAILABLE)" >> p12.log 2>&1
echo IMPORT_EXIT_%ERRORLEVEL% >> p12.log
echo === PYTEST === >> p12.log
.venv\Scripts\python.exe -m pytest tests/ -q --no-header -p no:cacheprovider --tb=line >> p12.log 2>&1
echo PYTEST_EXIT_%ERRORLEVEL% >> p12.log
echo P12_DONE
