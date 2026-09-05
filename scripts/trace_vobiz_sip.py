import subprocess

cmd1 = "docker exec leadgen-freeswitch fs_cli -x 'sofia profile external siptrace on'"
cmd2 = "docker exec leadgen-freeswitch fs_cli -x 'originate {origination_caller_id_number=+911171366938,originate_timeout=10}sofia/gateway/vobiz/918459012607 &park'"
cmd3 = "docker logs --tail 40 leadgen-freeswitch"

try:
    subprocess.run(cmd1, shell=True, check=True)
    out2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
    print("Originate output:", out2.stdout, out2.stderr)
    out3 = subprocess.check_output(cmd3, shell=True, text=True)
    print("FreeSWITCH logs:\n", out3)
except Exception as e:
    print("Error:", e)
