import json
import hashlib
from pathlib import Path
from backend.skills.scanner import scan_plugin_code, SecurityError
from backend.utils.audit_logger import audit_logger

REGISTRY_FILE = Path("backend/skills/registry.json")

def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        audit_logger.error(f"Failed to read registry: {e}")
        return {}

def verify_and_load_plugin(plugin_path: Path) -> bool:
    """
    Verifies the SHA-256 hash of the plugin against the registry,
    runs AST static analysis, and returns True if safe.
    """
    if not plugin_path.exists():
        return False
        
    plugin_name = plugin_path.stem
    registry = load_registry()
    
    if plugin_name not in registry:
        audit_logger.warning(f"Plugin {plugin_name} not in registry. Blocked.")
        return False
        
    expected_hash = registry[plugin_name]
    
    try:
        code_str = plugin_path.read_text(encoding="utf-8")
        actual_hash = hashlib.sha256(code_str.encode("utf-8")).hexdigest()
        
        if actual_hash != expected_hash:
            audit_logger.warning(f"Hash mismatch for plugin {plugin_name}. Expected {expected_hash}, got {actual_hash}. Blocked.")
            return False
            
        # Run AST scanner
        scan_plugin_code(code_str)
        
        return True
    except SecurityError as e:
        audit_logger.warning(f"Security violation in plugin {plugin_name}: {e}. Blocked.")
        return False
    except Exception as e:
        audit_logger.error(f"Error loading plugin {plugin_name}: {e}")
        return False
