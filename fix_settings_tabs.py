import os
import re

file_path = "C:/maya-ai/frontend/src/components/ui/SettingsModal.tsx"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Restore the deleted tabs block and add the new tab type
if "type Tab = 'providers' | 'voice' | 'permissions' | 'telegram' | 'whatsapp';" not in content:
    content = content.replace(
        "type Tab = 'providers' | 'voice' | 'permissions' | 'telegram';",
        "type Tab = 'providers' | 'voice' | 'permissions' | 'telegram' | 'whatsapp';"
    )

if "const tabs" not in content:
    content = content.replace(
        "  if (!isOpen) return null;\n\n        {/* Sidebar */}",
        "  if (!isOpen) return null;\n\n  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [\n    { id: 'providers', label: 'AI Providers', icon: <Key size={15} /> },\n    { id: 'voice',     label: 'Voice & TTS',  icon: <Volume2 size={15} /> },\n    { id: 'permissions', label: 'Permissions',  icon: <Shield size={15} /> },\n    { id: 'telegram',   label: 'Telegram Bot', icon: <Send size={15} /> },\n    { id: 'whatsapp',   label: 'WhatsApp',     icon: <Smartphone size={15} /> },\n  ];\n\n  return (\n    <div className=\"fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm\">\n      <div className=\"bg-slate-900 border border-slate-700/80 shadow-2xl rounded-2xl w-[660px] max-h-[540px] flex overflow-hidden\">\n\n        {/* Sidebar */}"
    )

# Add the render block for whatsapp
if "activeTab === 'whatsapp'" not in content:
    whatsapp_block = """
          {/* ── WhatsApp Integration ── */}
          {activeTab === 'whatsapp' && (
            <WhatsAppIntegration />
          )}
"""
    content = content.replace("        </div>\n      </div>\n    </div>\n  );\n};", whatsapp_block + "        </div>\n      </div>\n    </div>\n  );\n};")

# Fix the lucide-react import
if "Smartphone" not in content.split("from 'lucide-react';")[0]:
    content = content.replace("Volume2, Send,\n} from 'lucide-react';", "Volume2, Send, Smartphone,\n} from 'lucide-react';")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed SettingsModal.tsx")
