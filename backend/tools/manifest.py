from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

# Risk tiers determine if the Intent Sentinel blocks the action in certain modes
RiskTier = Literal["safe", "unsafe", "requires_approval"]

@dataclass
class ToolManifest:
    name: str
    description: str
    category: str
    risk_tier: RiskTier
    output_schema: Dict[str, Any]
    needs_semantic_verify: bool = False
    fallback_tool: Optional[str] = None
    
    def adapt_args_for_fallback(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Override this method if the tool has a fallback tool and args need translation."""
        return args

# ---------------------------------------------------------------------------
# Core Unified Tools (Low token, high power)
# ---------------------------------------------------------------------------

file_manifest = ToolManifest(
    name="file",
    description="All file operations in one tool: copy, move, rename, delete, read, open browser-supported local files, write, ls, mkdir, search, organize.",
    category="filesystem",
    risk_tier="unsafe", # Because it can delete/overwrite, inherently unsafe for non-professional modes
    needs_semantic_verify=False,
    output_schema={"type": "string"} # usually returns a status string or file content
)

pc_manifest = ToolManifest(
    name="pc",
    description="System control: volume, brightness, lock, mute, screenshot, camera photo, sleep, shutdown, restart, clipboard, processes, battery, wifi, bluetooth.",
    category="system",
    risk_tier="requires_approval", # Shutdown/restart need approval. The Intent Sentinel / Agent Team logic will handle granular action-level blocks.
    needs_semantic_verify=False,
    output_schema={"type": "string"}
)

channel_manifest = ToolManifest(
    name="channel",
    description="Messaging (Telegram/WhatsApp). Send messages, read chats.",
    category="communication",
    risk_tier="safe",
    needs_semantic_verify=True, # Semantic verify helps check if the message looks correct before sending
    output_schema={"type": "string"}
)

browser_manifest = ToolManifest(
    name="browser",
    description="Web actions: search, open url.",
    category="web",
    risk_tier="safe",
    needs_semantic_verify=False,
    output_schema={"type": "string"}
)

# ---------------------------------------------------------------------------
# Standard Tools
# ---------------------------------------------------------------------------

open_app_manifest = ToolManifest(
    name="open_app",
    description="Open any installed application by name.",
    category="system",
    risk_tier="safe",
    needs_semantic_verify=False,
    output_schema={"type": "string"}
)

execute_powershell_manifest = ToolManifest(
    name="execute_powershell",
    description="Run arbitrary powershell commands.",
    category="terminal",
    risk_tier="unsafe",
    needs_semantic_verify=False,
    output_schema={"type": "string"}
)

execute_python_manifest = ToolManifest(
    name="execute_python",
    description="Run arbitrary python scripts.",
    category="terminal",
    risk_tier="unsafe",
    needs_semantic_verify=True, # Semantic verify to check if execution trace looks successful
    output_schema={"type": "string"}
)

gmail_action_manifest = ToolManifest(
    name="gmail_action",
    description="Gmail actions: search, draft, send, read, trash.",
    category="communication",
    risk_tier="safe",
    needs_semantic_verify=True, # High cost of mistakes in email
    output_schema={"type": "string"}
)

playwright_navigate_manifest = ToolManifest(
    name="playwright_navigate",
    description="Navigate the playwright browser to a URL.",
    category="web",
    risk_tier="safe",
    needs_semantic_verify=False,
    output_schema={"type": "string"}
)

update_canvas_manifest = ToolManifest(
    name="update_canvas",
    description="Update the visual canvas widget with custom HTML/CSS/JS.",
    category="ui",
    risk_tier="safe",
    needs_semantic_verify=True, # Verify the code looks like valid HTML/JS widget
    output_schema={"type": "string"}
)

create_pdf_manifest = ToolManifest(
    name="create_pdf",
    description="Create a polished PDF report in the background without opening an app.",
    category="filesystem",
    risk_tier="safe",
    needs_semantic_verify=False,
    output_schema={"type": "string"},
)

# A registry of all tool manifests
TOOL_MANIFESTS: Dict[str, ToolManifest] = {
    "file": file_manifest,
    "pc": pc_manifest,
    "channel": channel_manifest,
    "browser": browser_manifest,
    "open_app": open_app_manifest,
    "execute_powershell": execute_powershell_manifest,
    "execute_python": execute_python_manifest,
    "gmail_action": gmail_action_manifest,
    "playwright_navigate": playwright_navigate_manifest,
    "update_canvas": update_canvas_manifest,
    "create_pdf": create_pdf_manifest,
}

def get_manifest(tool_name: str) -> Optional[ToolManifest]:
    """Retrieve the manifest for a specific tool. Generates a default if not found."""
    if tool_name in TOOL_MANIFESTS:
        return TOOL_MANIFESTS[tool_name]
    
    # Default fallback for un-migrated tools
    return ToolManifest(
        name=tool_name,
        description=f"Auto-generated manifest for {tool_name}",
        category="general",
        risk_tier="safe",
        needs_semantic_verify=False,
        output_schema={"type": "string"}
    )
