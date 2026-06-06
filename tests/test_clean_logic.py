import os
import subprocess
import json
import traceback

def test_clean():
    try:
        current_pid = os.getpid()
        print("Current PID:", current_pid)
        if os.name == 'nt':
            cmd = 'powershell -Command "Get-CimInstance Win32_Process -Filter \\"Name = \'python.exe\'\\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"'
            output = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')
            print("Powershell output length:", len(output))
            if output.strip():
                processes = json.loads(output)
                if not isinstance(processes, list):
                    processes = [processes]
                print(f"Loaded {len(processes)} processes from JSON.")
                for p in processes:
                    if not p:
                        continue
                    pid = p.get("ProcessId")
                    cmdline = p.get("CommandLine") or ""
                    if pid and pid != current_pid:
                        if "uvicorn" in cmdline or "spawn_main" in cmdline:
                            print(f"Would kill conflicting Telegram process with PID {pid}: {cmdline[:60]}...")
            else:
                print("PowerShell returned empty string.")
    except Exception as e:
        print("Error during clean:")
        traceback.print_exc()

if __name__ == "__main__":
    test_clean()
