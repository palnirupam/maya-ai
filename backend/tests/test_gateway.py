"""Unit tests for the channel gateway (backend/brain/gateway.py)."""
import sys, os
sys.path.insert(0, os.path.abspath("."))

import unittest
from unittest.mock import patch

from backend.brain import gateway


def _make_stream(chunks):
    async def _gen(session_id, text, image_base64=None):
        for c in chunks:
            yield c
    return _gen


class TestGateway(unittest.IsolatedAsyncioTestCase):

    async def _run(self, chunks, **kw):
        with patch.object(gateway.orchestrator, "process_user_input_stream",
                          _make_stream(chunks)):
            return await gateway.run_turn("s1", "hi", **kw)

    async def test_plain_text_accumulates_and_cleans(self):
        res = await self._run(["Hello ", "world"])
        self.assertEqual(res.final_text, "Hello world")

    async def test_reasoning_leak_stripped_from_final(self):
        # Plain-text 👤 thought-process leak with a Bengali answer after it.
        leak = ("\U0001f464 My thought process:\n1. do X\nLet's do it."
                "আপনার কাজ হয়েগেছে।")
        res = await self._run([leak])
        self.assertEqual(res.final_text, "আপনার কাজ হয়েগেছে।")
        self.assertNotIn("thought process", res.final_text.lower())

    async def test_think_tags_stripped_in_live_stream(self):
        streamed = []
        chunks = ["Hi <thi", "nk>secret</think> there"]
        res = await self._run(chunks, on_text=lambda c: streamed.append(c))
        self.assertNotIn("secret", "".join(streamed))
        self.assertIn("there", "".join(streamed))

    async def test_events_collected_and_forwarded(self):
        seen = []
        chunks = ["ok ", {"type": "agent_status", "data": {"x": 1}}, "done"]
        res = await self._run(chunks, on_event=lambda e: seen.append(e))
        self.assertEqual(len(res.events), 1)
        self.assertEqual(seen[0]["type"], "agent_status")
        self.assertEqual(res.final_text, "ok done")

    async def test_mode_change_token_extracted_and_hidden(self):
        res = await self._run(["Switching now. MODE_CHANGE_TRIGGERED:coding"])
        self.assertEqual(res.mode_change, "coding")
        self.assertNotIn("MODE_CHANGE_TRIGGERED", res.final_text)

    async def test_system_state_token_extracted(self):
        res = await self._run(["SYSTEM_STATE_TRIGGERED:mic_lock done"])
        self.assertEqual(res.system_state, "mic_lock")

    async def test_should_stop_aborts_stream(self):
        # should_stop flips True after the first chunk is seen; the second chunk
        # must never reach on_text and result.stopped must be set.
        seen = []
        flag = {"stop": False}
        chunks = ["first ", "second"]

        def _stop():
            # Stop once we've already emitted the first visible chunk.
            return flag["stop"]

        async def _on_text(c):
            seen.append(c)
            flag["stop"] = True  # next iteration's should_stop() returns True

        res = await self._run(chunks, on_text=_on_text, should_stop=_stop)
        self.assertTrue(res.stopped)
        self.assertIn("first", "".join(seen))
        self.assertNotIn("second", "".join(seen))

    async def test_tail_not_flushed_when_stopped(self):
        # An unclosed tag would normally be flushed as tail text at stream end;
        # when stopped, that tail must be suppressed.
        seen = []
        res = await self._run(["hello <think>partial"],
                              on_text=lambda c: seen.append(c),
                              should_stop=lambda: True)
        self.assertTrue(res.stopped)
        self.assertNotIn("partial", "".join(seen))


if __name__ == "__main__":
    unittest.main()
