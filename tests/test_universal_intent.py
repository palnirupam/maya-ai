"""
Test suite for Universal Intent Classification System
Run: pytest tests/test_universal_intent.py -v
"""
import pytest
import asyncio
from backend.brain.agents.universal_intent_classifier import (
    classify_universal_intent,
    clear_intent_cache,
    get_cache_stats,
    IntentResult
)


class TestCommunicationIntents:
    """Test WhatsApp and Email intent detection."""
    
    @pytest.mark.asyncio
    async def test_whatsapp_send(self):
        test_cases = [
            "Maa ke msg pathao hi",
            "WhatsApp e Som ke bolo dinner ready",
            "Ankita te text koro ami late hobe",
            "Baba ke WhatsApp koro phone nao",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.whatsapp_send, f"Failed for: {text}"
            assert intent.primary_agent == "OS_EXECUTOR"
    
    @pytest.mark.asyncio
    async def test_email_send(self):
        test_cases = [
            "Gmail e mail pathao",
            "nirupam@gmail.com ke email koro",
            "resume attach kore mail pathao boss ke",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.email_send, f"Failed for: {text}"
    
    @pytest.mark.asyncio
    async def test_email_read(self):
        test_cases = [
            "email check koro",
            "inbox dekho",
            "latest mail ki ache",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.email_read, f"Failed for: {text}"


class TestVisualIntents:
    """Test camera and wallpaper intent detection."""
    
    @pytest.mark.asyncio
    async def test_camera_outfit(self):
        test_cases = [
            "ami kemon lagchi",
            "outfit kemon lagche",
            "dress ta bhalo lagche ki",
            "je kapor pore elam ta kemon",  # Creative phrasing
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.camera_outfit, f"Failed for: {text}"
            assert not intent.wallpaper_change, f"False positive wallpaper for: {text}"
    
    @pytest.mark.asyncio
    async def test_wallpaper_change(self):
        """CRITICAL: Wallpaper should NEVER trigger camera."""
        test_cases = [
            "wallpaper lagiye dao",
            "Srikrishna er wallpaper dao",
            "background change koro",
            "desktop theme set koro",
            "wallpaper ta valo lagche na",  # Has "lagche" but still wallpaper
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.wallpaper_change, f"Failed to detect wallpaper: {text}"
            assert not intent.camera_outfit, f"False positive camera_outfit for: {text}"
            assert not intent.camera_review, f"False positive camera_review for: {text}"
    
    @pytest.mark.asyncio
    async def test_camera_review(self):
        test_cases = [
            "eta ki dekho",
            "ei flower review koro",
            "ye mouse kaisa hai",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.camera_review, f"Failed for: {text}"


class TestMediaIntents:
    """Test YouTube and media control."""
    
    @pytest.mark.asyncio
    async def test_youtube_play(self):
        test_cases = [
            "gaana chalao",
            "song play koro",
            "YouTube e video dekho",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.youtube_play, f"Failed for: {text}"
    
    @pytest.mark.asyncio
    async def test_youtube_data(self):
        test_cases = [
            "ei video te like koto",
            "subscriber count dekho",
            "comment gulo dekha",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.youtube_data, f"Failed for: {text}"
            assert not intent.youtube_play, f"Confused youtube_data with play: {text}"
    
    @pytest.mark.asyncio
    async def test_media_control(self):
        test_cases = [
            "pause koro",
            "stop music",
            "gaana bondho koro",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.media_control, f"Failed for: {text}"


class TestSystemControl:
    """Test system control intents."""
    
    @pytest.mark.asyncio
    async def test_volume_control(self):
        test_cases = [
            "volume 50 koro",
            "awaz badao",
            "mute koro",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.volume_control, f"Failed for: {text}"
    
    @pytest.mark.asyncio
    async def test_power_actions(self):
        test_cases = [
            "shutdown koro",
            "PC restart koro",
            "sleep mode e jao",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.power_action, f"Failed for: {text}"


class TestMultiIntent:
    """Test multi-intent detection."""
    
    @pytest.mark.asyncio
    async def test_app_and_youtube(self):
        text = "Chrome kholo and YouTube e gaana chalao"
        intent = await classify_universal_intent(text)
        assert intent.app_open, "Failed to detect app_open"
        assert intent.youtube_play, "Failed to detect youtube_play"
    
    @pytest.mark.asyncio
    async def test_whatsapp_and_volume(self):
        text = "Maa ke msg pathao and volume 70 koro"
        intent = await classify_universal_intent(text)
        assert intent.whatsapp_send, "Failed to detect whatsapp_send"
        assert intent.volume_control, "Failed to detect volume_control"


class TestEntityExtraction:
    """Test entity extraction."""
    
    @pytest.mark.asyncio
    async def test_contact_extraction(self):
        text = "Maa ke WhatsApp e bolo dinner ready"
        intent = await classify_universal_intent(text)
        assert "contact_names" in intent.entities
        assert "Maa" in intent.entities["contact_names"]
    
    @pytest.mark.asyncio
    async def test_number_extraction(self):
        text = "volume 70 koro"
        intent = await classify_universal_intent(text)
        assert "numbers" in intent.entities
        assert 70 in intent.entities["numbers"]
    
    @pytest.mark.asyncio
    async def test_chrome_profile_extraction(self):
        text = "Chrome kholo Nirupam profile e"
        intent = await classify_universal_intent(text)
        assert intent.chrome_profile == "Nirupam"


class TestConversation:
    """Test conversational intents."""
    
    @pytest.mark.asyncio
    async def test_greetings(self):
        test_cases = [
            "hello",
            "hi Maya",
            "kemon acho",
            "good morning",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.is_greeting, f"Failed for: {text}"
            assert intent.primary_agent == "CHAT"
    
    @pytest.mark.asyncio
    async def test_questions(self):
        test_cases = [
            "time koto",
            "Python ki",
            "how does async work",
        ]
        for text in test_cases:
            intent = await classify_universal_intent(text)
            assert intent.is_question, f"Failed for: {text}"


class TestCaching:
    """Test cache functionality."""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        clear_intent_cache()
        
        text = "hello"
        
        # First call - cache miss
        await classify_universal_intent(text, use_cache=True)
        stats1 = get_cache_stats()
        
        # Second call - cache hit
        await classify_universal_intent(text, use_cache=True)
        stats2 = get_cache_stats()
        
        assert stats2["hits"] > stats1["hits"], "Cache not working"
        assert stats2["size"] > 0, "Cache not storing"


class TestEdgeCases:
    """Test edge cases and ambiguous queries."""
    
    @pytest.mark.asyncio
    async def test_wallpaper_with_lagche(self):
        """Critical: 'lagche' in wallpaper context should NOT trigger camera."""
        text = "wallpaper ta valo lagche na"
        intent = await classify_universal_intent(text)
        assert intent.wallpaper_change or intent.is_casual_chat
        assert not intent.camera_outfit
        assert not intent.camera_review
    
    @pytest.mark.asyncio
    async def test_chrome_wallpaper_download(self):
        """Complex: Chrome to download wallpaper, then set it."""
        text = "chrome e wallpaper download kore lagao"
        intent = await classify_universal_intent(text)
        assert intent.app_open, "Failed to detect Chrome open"
        assert intent.wallpaper_change, "Failed to detect wallpaper change"


if __name__ == "__main__":
    # Run specific test
    asyncio.run(TestVisualIntents().test_wallpaper_change())
    print("✅ All wallpaper tests passed!")
