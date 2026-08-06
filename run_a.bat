@echo off
echo === A1: MAYA_TESTING ===
echo %MAYA_TESTING%

echo === A2: Pytest TestFix1_DPAPI ===
set MAYA_TESTING=
python -m pytest backend/tests/test_audit_fixes_deep.py -k TestFix1_DPAPI -v

echo === A3: DPAPI Usage ===
findstr /C:"crypt32.dll" backend\database\crypto.py

echo === A4: Read .salt manually ===
python -c "from backend.database.crypto import crypto_manager; crypto_manager.encrypt('test'); import os; p=os.path.join(os.environ.get('LOCALAPPDATA',''), 'MayaAI', '.salt'); print(open(p, 'rb').read()[:50] if os.path.exists(p) else 'No .salt file found')"
