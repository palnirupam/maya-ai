import os
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

# Global semaphore to limit hook concurrency to 10
_concurrency_semaphore = None

def get_semaphore():
    global _concurrency_semaphore
    if _concurrency_semaphore is None:
        _concurrency_semaphore = asyncio.Semaphore(10)
    return _concurrency_semaphore

ROOT_DIR = os.path.abspath("c:/maya-ai")
HOOKS_DIR = os.path.abspath(os.path.join(ROOT_DIR, "hooks"))
CONFIG_PATH = os.path.abspath("c:/maya-ai/backend/config/hooks.json")
PYTHON_EXECUTABLE = os.path.abspath("c:/maya-ai/backend/.venv/Scripts/python.exe")

if not os.path.exists(PYTHON_EXECUTABLE):
    import sys
    PYTHON_EXECUTABLE = sys.executable

def validate_script_path(script_rel_path: str) -> str:
    """
    Validates that the script path resolves strictly within the hooks directory.
    Prevents path traversal attacks (e.g., ../../../Windows/System32/calc.exe).
    Returns the absolute path if valid, otherwise raises ValueError.
    """
    target_abs = os.path.abspath(os.path.join(ROOT_DIR, script_rel_path))
    
    try:
        common = os.path.commonpath([HOOKS_DIR, target_abs])
        # Verify target is exactly under HOOKS_DIR and NOT the HOOKS_DIR itself
        if common != HOOKS_DIR or target_abs == HOOKS_DIR:
            raise ValueError("Path traversal detected! Script must reside inside c:\\maya-ai\\hooks\\.")
    except Exception as e:
        raise ValueError(f"Invalid script path: {e}")
        
    if not os.path.isfile(target_abs):
        raise ValueError(f"Script file does not exist: {target_abs}")
        
    return target_abs

def load_hooks_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[Hooks] Failed to load hooks config: {e}")
        return {}

async def trigger_hook(event_name: str, payload: dict) -> None:
    """
    Triggers an event hook by executing the configured script with payload as JSON argument.
    Protects against command injection by using shell=False, limits concurrency using Semaphore,
    and enforces execution timeouts.
    """
    config = load_hooks_config()
    hook_config = config.get(event_name)
    if not hook_config or not hook_config.get("enabled"):
        return
        
    script_rel_path = hook_config.get("script")
    if not script_rel_path:
        logger.warning(f"[Hooks] Hook '{event_name}' enabled but no script path specified.")
        return
        
    try:
        script_path = validate_script_path(script_rel_path)
    except ValueError as e:
        logger.error(f"[Hooks] Script path validation failed for hook '{event_name}': {e}")
        return
        
    timeout = hook_config.get("timeout", 30)
    sem = get_semaphore()
    
    async with sem:
        logger.info(f"[Hooks] Triggering hook '{event_name}' with script '{script_path}'...")
        payload_str = json.dumps(payload)
        
        if script_path.endswith(".py"):
            cmd = [PYTHON_EXECUTABLE, script_path, payload_str]
        else:
            cmd = [script_path, payload_str]
            
        try:
            # Strict shell=False list invocation to prevent command injections
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                exit_code = proc.returncode
                
                if exit_code == 0:
                    logger.info(f"[Hooks] Hook '{event_name}' executed successfully.")
                    if stdout:
                        logger.debug(f"[Hooks] Stdout: {stdout.decode('utf-8', errors='ignore')}")
                else:
                    logger.error(
                        f"[Hooks] Hook '{event_name}' failed with exit code {exit_code}.\n"
                        f"Stderr: {stderr.decode('utf-8', errors='ignore')}"
                    )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception as kill_err:
                    logger.error(f"[Hooks] Failed to kill timed out process: {kill_err}")
                logger.error(f"[Hooks] Hook '{event_name}' timed out after {timeout} seconds and was killed.")
                
        except Exception as e:
            logger.error(f"[Hooks] Failed to start hook process '{event_name}': {e}")
