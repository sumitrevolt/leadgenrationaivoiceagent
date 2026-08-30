import subprocess

cmd = "docker exec leadgen-freeswitch fs_cli -x 'status'"
try:
    out = subprocess.check_output(cmd, shell=True, text=True)
    print("FreeSWITCH status:\n", out)
except Exception as e:
    print("Error:", e)
