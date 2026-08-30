import subprocess

cmd = "docker exec leadgen-freeswitch fs_cli -x 'originate {origination_caller_id_number=+911171366938,originate_timeout=15}sofia/gateway/vobiz/918459012607 &park'"
try:
    out = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True, timeout=20)
    print("Originate output:", out)
except subprocess.CalledProcessError as e:
    print("Originate error code:", e.returncode)
    print("Output:", e.output)
except Exception as e:
    print("Exception:", e)
