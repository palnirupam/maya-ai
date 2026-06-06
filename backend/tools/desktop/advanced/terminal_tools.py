import subprocess
import os
from backend.system.process_manager import process_manager

def execute_powershell(command: str) -> str:
    """
    Executes a PowerShell command on the Windows system and returns the output.
    Useful for managing system settings, exploring directories, or checking configurations.
    """
    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process_manager.register_pid(proc.pid)
        
        try:
            output, error = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, error = proc.communicate()
            error += "\n(TIMEOUT EXPIRED)"
        finally:
            process_manager.unregister_pid(proc.pid)
        
        output = output if output else ""
        error = error if error else ""
        
        if proc.returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {proc.returncode}):\n{error}\n{output}"
    except Exception as e:
        return f"EXECUTION FAILED: {str(e)}"

def execute_python(code: str) -> str:
    """
    Executes arbitrary Python code and returns the output.
    Useful for complex calculations, API calls, or logic that isn't covered by other tools.
    The code runs in a temporary file.
    """
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
            
        proc = subprocess.Popen(
            ["python", temp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process_manager.register_pid(proc.pid)
        
        try:
            output, error = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, error = proc.communicate()
            error += "\n(TIMEOUT EXPIRED)"
        finally:
            process_manager.unregister_pid(proc.pid)
        
        try:
            os.remove(temp_path)
        except:
            pass
            
        output = output if output else ""
        error = error if error else ""
        
        if proc.returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {proc.returncode}):\n{error}\n{output}"
            
    except Exception as e:
        return f"PYTHON EXECUTION FAILED: {str(e)}"
