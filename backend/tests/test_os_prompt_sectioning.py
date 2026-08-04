"""Unit tests for OS_EXECUTOR prompt sectioning (compose_os_prompt).

agent_defs is a light module (dataclass/typing/datetime/re), so these tests are
hermetic — no network, no heavy imports.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest

from backend.brain.agents.agent_defs import compose_os_prompt, OS_EXECUTOR_PROMPT


class TestComposeOsPrompt(unittest.TestCase):
    def test_core_always_present(self):
        for task in ("volume 50 koro", "baba ke email koro", "notepad e likho hi"):
            p = compose_os_prompt(task)
            self.assertIn("YOUR ONLY JOB", p)               # core header
            self.assertIn("ANTI-HALLUCINATION", p)          # appended block

    def test_volume_request_includes_only_volume(self):
        p = compose_os_prompt("volume 50 koro")
        self.assertIn("VOLUME CONTROL", p)
        self.assertNotIn("For WhatsApp", p)
        self.assertNotIn("For YouTube", p)
        self.assertLess(len(p), len(OS_EXECUTOR_PROMPT))    # genuinely smaller

    def test_email_request_includes_email_block(self):
        p = compose_os_prompt("baba ke email koro Pay.pdf attach kore")
        self.assertIn("attachment_path", p)
        self.assertIn("HONEST CONFIRMATION", p)
        self.assertIn("create_pdf", p)
        self.assertIn("create the PDF FIRST", p)

    def test_whatsapp_request_includes_whatsapp_block(self):
        p = compose_os_prompt("baba ke whatsapp e msg koro")
        self.assertIn("For WhatsApp", p)
        self.assertIn("whatsapp_send_message(contact_name, message)", p)
        self.assertIn("logged-in WhatsApp synced contact", p)

    def test_whatsapp_prompt_does_not_stop_after_contact_lookup(self):
        for p in (
            compose_os_prompt("Pintu ke hi send koro"),
            OS_EXECUTOR_PROMPT,
        ):
            self.assertIn("do not stop there", p)
            self.assertNotIn("To send: use whatsapp_send_message(phone_number, message)", p)

    def test_whatsapp_block_forbids_pywhatkit_terminal_escalation(self):
        # BUG-024 defense-in-depth: a WhatsApp failure must never be worked
        # around by installing pywhatkit or running scripts/terminal commands.
        for p in (
            compose_os_prompt("baba ke whatsapp e msg koro"),
            OS_EXECUTOR_PROMPT,
        ):
            self.assertIn("pywhatkit", p)
            # The guard itself must not name CODER-only terminal tools in the
            # file/whatsapp-gated prompt (that naming caused a past stall).
            self.assertNotIn("execute_powershell", p)
            self.assertNotIn("run_terminal_command", p)

    def test_send_intent_pulls_delivery_blocks_without_named_channel(self):
        # "X ke news pathao" names no channel, but is clearly a delivery — both
        # messaging blocks must be present so the send never half-completes.
        p = compose_os_prompt("baba ke ajker news pathao")
        self.assertIn("For WhatsApp", p)
        self.assertIn("send_background_email", p)

    def test_ambiguous_falls_back_to_full_prompt(self):
        # No capability gate matches → return the full manual (never drop rules).
        self.assertEqual(compose_os_prompt("kichu ekta koro to"), OS_EXECUTOR_PROMPT)
        self.assertEqual(compose_os_prompt(""), OS_EXECUTOR_PROMPT)


class TestFileBlock(unittest.TestCase):
    """Bug: OS_EXECUTOR has the `file` tool but its prompt never documented it and
    instead told it to use run_terminal_command/execute_powershell (which are NOT
    in its toolset). So "desktop e save koro new.txt" made it stall with
    "I cannot create the file directly via terminal ... wait for the next step."
    Fix: a FILE / FOLDER OPERATIONS block documenting the `file` tool, gated on
    real file signals, plus removal of the dead terminal-tool instruction."""

    def test_save_txt_request_pulls_file_block(self):
        p = compose_os_prompt("news summary desktop e save koro new.txt name e")
        self.assertIn("FILE / FOLDER OPERATIONS", p)
        self.assertIn('file(action="write"', p)

    def test_file_block_never_mentions_unavailable_terminal_tools(self):
        # These tools live on CODER, not OS_EXECUTOR — the prompt must not tell
        # OS_EXECUTOR to use them (that was the exact cause of the stall).
        for p in (
            compose_os_prompt("desktop e save koro report.txt"),
            OS_EXECUTOR_PROMPT,
        ):
            self.assertNotIn("run_terminal_command", p)
            self.assertNotIn("execute_powershell", p)

    def test_folder_and_extension_signals_match(self):
        for task in (
            "ei folder ta organize koro",
            "resume.pdf ta poro",
            "notes.md file e likhe rakho",
            "documents e save koro data.csv",
        ):
            self.assertIn("FILE / FOLDER OPERATIONS", compose_os_prompt(task))

    def test_save_contact_not_hijacked_by_file_gate(self):
        # "save contact" carries no file signal — must NOT collapse to the file
        # block; the save_contact guidance (whatsapp / full manual) must remain.
        p = compose_os_prompt("Rahul er contact save koro 98765")
        self.assertIn("save_contact", p)

    def test_monolith_documents_file_tool_too(self):
        # The fallback manual must also know the `file` tool exists.
        self.assertIn('file(action="write"', OS_EXECUTOR_PROMPT)

    def test_document_open_flow_requires_real_listing_and_tool_calls(self):
        for prompt in (compose_os_prompt("Document"), OS_EXECUTOR_PROMPT):
            self.assertIn("Never invent filenames", prompt)
            self.assertIn("once for EACH file", prompt)
            self.assertIn("NEVER pass the complaint to open_app", prompt)
            self.assertIn("result starts with OK", prompt)


if __name__ == "__main__":
    unittest.main()
