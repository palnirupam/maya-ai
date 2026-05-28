import difflib
import logging
from .sandbox import sandbox

logger = logging.getLogger(__name__)

class CodeWriter:
    """
    Generates unified diffs for file modifications instead of silent overwrites.
    """
    @staticmethod
    def propose_edit(file_path: str, new_content: str) -> dict:
        if not sandbox.is_path_allowed(file_path):
            return {"status": "error", "message": "Path access denied by sandbox."}
            
        try:
            original_content = ""
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                    
            # Generate a unified diff
            diff = list(difflib.unified_diff(
                original_content.splitlines(keepends=True),
                new_content.splitlines(keepends=True),
                fromfile="original",
                tofile="modified"
            ))
            
            return {
                "status": "success",
                "diff": "".join(diff),
                "full_new_content": new_content
            }
        except Exception as e:
            logger.error(f"Code writer error: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    def apply_edit(file_path: str, new_content: str) -> bool:
        """Only called AFTER user clicks [Approve] on the frontend."""
        if not sandbox.is_path_allowed(file_path):
            return False
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True
        except Exception as e:
            logger.error(f"Failed to apply edit: {e}")
            return False

code_writer = CodeWriter()
