import subprocess
import os
import tempfile
import logging
from backend.system.process_manager import process_manager

logger = logging.getLogger(__name__)


def _run_subprocess_blocking(cmd_args: list[str], timeout: int) -> tuple[int, str, str]:
    """Execute a subprocess synchronously with PID tracking and timeout handling."""
    proc = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    process_manager.register_pid(proc.pid)

    output = ""
    error = ""
    try:
        output, error = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        output, error = proc.communicate()
        error = f"{(error or '')}\n(TIMEOUT EXPIRED after {timeout}s)"
    finally:
        process_manager.unregister_pid(proc.pid)

    return (proc.returncode, output or "", error or "")


def execute_powershell(command: str) -> str:
    """
    Executes a PowerShell command on the Windows system and returns the output.
    Useful for managing system settings, exploring directories, or checking configurations.
    """
    try:
        returncode, output, error = _run_subprocess_blocking(
            ["powershell.exe", "-Command", command],
            timeout=30
        )
        if returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {returncode}):\n{error}\n{output}"
    except Exception as e:
        return f"EXECUTION FAILED: {str(e)}"


def execute_python(code: str) -> str:
    """
    Executes arbitrary Python code and returns the output.
    Useful for complex calculations, API calls, or logic that isn't covered by other tools.
    The code runs in a temporary file.
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        returncode, output, error = _run_subprocess_blocking(
            ["python", temp_path],
            timeout=60
        )

        if returncode == 0:
            return f"SUCCESS:\n{output}"
        else:
            return f"ERROR (Code {returncode}):\n{error}\n{output}"

    except Exception as e:
        return f"PYTHON EXECUTION FAILED: {str(e)}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as cleanup_err:
                logger.warning(f"Could not remove temporary Python script {temp_path}: {cleanup_err}")

