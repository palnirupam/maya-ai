import unittest
from backend.brain.gemini.function_calls import get_maya_tools

class TestFunctionCalls(unittest.TestCase):
    def test_get_maya_tools(self):
        # Should not crash and should return a list of callable tools
        tools = get_maya_tools()
        self.assertTrue(len(tools) > 0)
        for tool in tools:
            self.assertTrue(callable(tool))

if __name__ == "__main__":
    unittest.main()
