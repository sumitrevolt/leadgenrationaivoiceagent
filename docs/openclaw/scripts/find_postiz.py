import os
for root, dirs, files in os.walk('app'):
    for f in files:
        if 'postiz' in f.lower() or 'post' in f.lower():
            path = os.path.join(root, f)
            print(f'{path}: {os.path.getsize(path)} bytes')