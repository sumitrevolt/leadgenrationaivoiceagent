@echo off
cd /d "%~dp0.."
del xlsx_build.log 2>nul
.venv\Scripts\python.exe -m pip install openpyxl -q > xlsx_build.log 2>&1
.venv\Scripts\python.exe scripts\build_pricing_xlsx.py >> xlsx_build.log 2>&1
echo BUILD_EXIT_%ERRORLEVEL% >> xlsx_build.log
.venv\Scripts\python.exe -c "from openpyxl import load_workbook; wb=load_workbook(r'Niche_Pricing_Research.xlsx'); print('sheets:', wb.sheetnames); ws=wb['Top 25 Niches']; print('rows:', ws.max_row, 'cols:', ws.max_column)" >> xlsx_build.log 2>&1
echo VERIFY_EXIT_%ERRORLEVEL% >> xlsx_build.log
echo XLSX_DONE
