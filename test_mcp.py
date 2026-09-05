import subprocess
import json

p = subprocess.Popen(["cua-driver", "manifest", "--json"], stdout=subprocess.PIPE, text=True)
stdout, _ = p.communicate()
print(stdout[:1000])
