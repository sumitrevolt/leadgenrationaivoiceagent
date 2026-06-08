@echo off
cd /d "%~dp0.."
del nichk.log 2>nul
.venv\Scripts\python.exe -c "from app.niches import NICHES; from collections import Counter; print('TOTAL', len(NICHES)); print('TIERS', dict(Counter(v.get('tier') for v in NICHES.values()))); print('CATS', dict(Counter(v.get('category','NONE') for v in NICHES.values()))); print('NOCAT', [k for k,v in NICHES.items() if 'category' not in v])" > nichk.log 2>&1
echo PARSE_EXIT_%ERRORLEVEL% >> nichk.log
.venv\Scripts\python.exe -c "from app.niche_knowledge import NICHE_KNOWLEDGE if False else 1" 2>nul
.venv\Scripts\python.exe -c "import app.niche_knowledge as nk; d=getattr(nk,'NICHE_KNOWLEDGE',{}) or getattr(nk,'KNOWLEDGE',{}); print('KB_KEYS', len(d)); new=['restaurant_cafe','jewellery_store','salon_spa','boutique_fashion','gym_fitness','bakery_sweets','mobile_electronics','hotel_resort','automobile_service','photography_studio','pharmacy_medical','furniture_decor','kirana_supermarket','travel_agency','gift_stationery','hardware_paint']; print('KB_NEW_PRESENT', sum(1 for k in new if k in d))" >> nichk.log 2>&1
echo KB_EXIT_%ERRORLEVEL% >> nichk.log
.venv\Scripts\python.exe -m pytest tests/test_provisioning.py -q --no-header -p no:cacheprovider --tb=line >> nichk.log 2>&1
echo PROV_EXIT_%ERRORLEVEL% >> nichk.log
echo NICHK_DONE
