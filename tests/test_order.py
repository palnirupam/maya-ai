import sys, os, asyncio, re
sys.path.insert(0, '.')

from backend.tools.desktop.advanced.browser_tools import read_background_email

async def test():
    result = await read_background_email(limit=3, query='ALL')
    uids = re.findall(r'<EMAIL uid="(\d+)"', result)
    print('Latest 3 email UIDs (should be descending = newest first):')
    for i, uid in enumerate(uids):
        print(f'  Email {i+1}: UID={uid}')
    if uids and len(uids) > 1:
        if int(uids[0]) > int(uids[1]):
            print('ORDER: CORRECT (newest first) - First email = UID ' + uids[0])
        else:
            print('ORDER: WRONG (oldest first)')

asyncio.run(test())
