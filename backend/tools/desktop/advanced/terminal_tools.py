import subprocess
import os

def execute_powershell(command: str) -> str:
    """
    Executes a PowerShell command on the Windows system and returns the output.
    Useful for managing system settings, exploring directories, or checking configurations.
    """
    try:
        result = subprocess.run(
            ["powershell.exe", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout if result.stdout else ""
        error = result.stderr if result.stderr else ""
        
        if result.returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {result.returncode}):\n{error}\n{output}"
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
            
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        try:
            os.remove(temp_path)
        except:
            pass
            
        output = result.stdout if result.stdout else ""
        error = result.stderr if result.stderr else ""
        
        if result.returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {result.returncode}):\n{error}\n{output}"
            
    except Exception as e:
        return f"PYTHON EXECUTION FAILED: {str(e)}"
