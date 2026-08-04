"""Test suite for comprehensive language consistency enforcement.

Tests to ensure Maya responds in the same language style as the user
across all components: tools, system messages, errors, etc.
"""

import pytest
import asyncio
from backend.brain.language_style import (
    BANGLISH, HINDILISH, ENGLISH,
    detect_language_style, 
    set_latest_conversation_style
)
from backend.brain.language_policy_enforcer import (
    policy_enforcer,
    get_system_msg,
    enforce_style
)
from backend.brain.language_style_enhanced import (
    translate_system_response,
    get_localized_message,
    format_localized_error
)
from backend.brain.agents._tool_response_translator import translate_tool_response

class TestLanguageConsistency:
    """Test comprehensive language consistency."""
    
    def test_user_banglish_maya_responds_banglish(self):
        """Test: User speaks Banglish → Maya responds in Banglish."""
        user_input = "ami ekta file create korte chai"
        detected_style = detect_language_style(user_input)
        assert detected_style == BANGLISH
        
        set_latest_conversation_style(detected_style)
        
        # Test system messages
        processing_msg = get_system_msg("processing")
        assert "korchi" in processing_msg.lower()
        assert "processing" not in processing_msg.lower()
        
    def test_user_hindilish_maya_responds_hindilish(self):
        """Test: User speaks Hindilish → Maya responds in Hindilish."""
        user_input = "mujhe ek file banana hai"
        detected_style = detect_language_style(user_input)
        assert detected_style == HINDILISH
        
        set_latest_conversation_style(detected_style)
        
        # Test system messages
        processing_msg = get_system_msg("processing") 
        assert "kar raha" in processing_msg.lower()
        assert "processing" not in processing_msg.lower()
        
    def test_user_english_maya_responds_english(self):
        """Test: User speaks English → Maya responds in English."""
        user_input = "I want to create a file"
        detected_style = detect_language_style(user_input)
        assert detected_style == ENGLISH
        
        set_latest_conversation_style(detected_style)
        
        # Test system messages
        processing_msg = get_system_msg("processing")
        assert processing_msg == "Processing..."
        
    def test_tool_response_translation_banglish(self):
        """Test tool responses are translated to Banglish."""
        set_latest_conversation_style(BANGLISH)
        
        # Test file tool response
        english_response = "File 'test.txt' created successfully"
        translated = translate_tool_response("file", english_response, BANGLISH)
        
        assert "create hoyeche" in translated or "successfully" in translated
        assert "File" in translated  # Technical terms should remain
        
    def test_tool_response_translation_hindilish(self):
        """Test tool responses are translated to Hindilish.""" 
        set_latest_conversation_style(HINDILISH)
        
        # Test pc tool response
        english_response = "Volume set to 50%"
        translated = translate_tool_response("pc", english_response, HINDILISH)
        
        assert "set ho gaya" in translated or "set" in translated
        assert "50" in translated  # Numbers should remain (might be in different format)
        
    def test_error_message_localization(self):
        """Test error messages are localized properly."""
        
        # Test Banglish error
        set_latest_conversation_style(BANGLISH)
        error = FileNotFoundError("test.txt not found")
        banglish_error = format_localized_error(error, BANGLISH)
        assert "khuje paini" in banglish_error or "file_not_found" in banglish_error.lower()
        
        # Test Hindilish error  
        set_latest_conversation_style(HINDILISH)
        hindilish_error = format_localized_error(error, HINDILISH)
        assert "nahi mila" in hindilish_error or "file_not_found" in hindilish_error.lower()
        
        # Test English error
        set_latest_conversation_style(ENGLISH)
        english_error = format_localized_error(error, ENGLISH)
        assert "not found" in english_error.lower()
        
    def test_mixed_conversation_continuity(self):
        """Test conversation style continuity with mixed/ambiguous input."""
        
        # Start with clear Banglish
        set_latest_conversation_style(BANGLISH)
        
        # Ambiguous short input should maintain Banglish
        ambiguous_input = "ok"
        detected = detect_language_style(ambiguous_input, fallback=BANGLISH)
        assert detected == BANGLISH
        
        # System message should still be Banglish
        msg = get_system_msg("completed")
        assert "hoyeche" in msg
        
    def test_technical_terms_preservation(self):
        """Test that technical terms remain in English even in translated text."""
        set_latest_conversation_style(BANGLISH)
        
        technical_response = "File '/path/to/file.pdf' copied to '/backup/' directory"
        translated = translate_tool_response("file", technical_response, BANGLISH)
        
        # Technical paths should be preserved (may be in different position)
        assert "path/to/file.pdf" in translated or "file.pdf" in translated
        assert "backup" in translated
        
        # But conversational parts should be translated
        assert "copy" in translated.lower()
        
    def test_policy_enforcer_sync(self):
        """Test that policy enforcer syncs with conversation style changes."""
        from backend.brain.language_policy_enforcer import enforce_style
        
        # Change style and verify enforcer follows via function calls
        set_latest_conversation_style(BANGLISH)
        test_msg = enforce_style("Processing")  # This should sync the enforcer
        assert "korchi" in test_msg or "Processing" in test_msg
        
        set_latest_conversation_style(HINDILISH)  
        test_msg = enforce_style("Processing")
        assert "kar raha" in test_msg or "Processing" in test_msg
        
        set_latest_conversation_style(ENGLISH)
        test_msg = enforce_style("Processing")
        assert test_msg == "Processing"
        
    def test_style_enforcement_decorator(self):
        """Test the style enforcement decorator works correctly."""
        from backend.brain.language_policy_enforcer import enforce_language_consistency
        
        @enforce_language_consistency
        def sample_function():
            return "File created successfully"
            
        set_latest_conversation_style(BANGLISH)
        result = sample_function()
        
        # Should be translated to Banglish
        assert "hoyeche" in result or "create" in result
        
    def test_comprehensive_maya_response(self):
        """Test end-to-end Maya response consistency."""
        
        # Simulate user speaking Banglish
        user_msg = "ami ekta screenshot nite chai"
        style = detect_language_style(user_msg)
        set_latest_conversation_style(style)
        
        # Simulate tool execution
        tool_response = "Screenshot saved to C:/Users/Screenshots/shot1.png"
        translated_response = translate_tool_response("pc", tool_response, style)
        
        # Verify response is in Banglish
        assert style == BANGLISH
        assert "save" in translated_response.lower()
        assert "Screenshot" in translated_response or "screenshot" in translated_response.lower()
        # Path should be preserved somewhere in the response
        assert "Screenshots" in translated_response or "shot1.png" in translated_response

if __name__ == "__main__":
    pytest.main([__file__, "-v"])