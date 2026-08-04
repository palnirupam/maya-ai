#!/usr/bin/env python3
"""Test script to verify message formatting fixes work correctly."""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

def test_message_formatting():
    """Test that PARTIAL and OK results are handled correctly."""
    try:
        from backend.brain.agents._routing import _format_direct_app_response
        
        print("🧪 Testing message formatting fixes...")
        
        # Test PARTIAL result (should show as partial success)
        partial_result = _format_direct_app_response(
            'close_apps_except', 
            'Chrome', 
            'PARTIAL: Closed 8 app window(s): Notepad, WhatsApp. Could not close 1 window(s).', 
            'banglish'
        )
        print(f"✅ PARTIAL test: {partial_result}")
        assert "kaj korte parlam na" not in partial_result, "PARTIAL should not show as error"
        
        # Test OK result (should show as success)  
        ok_result = _format_direct_app_response(
            'close_app',
            'Notepad', 
            'OK: Closed Notepad successfully',
            'banglish'
        )
        print(f"✅ OK test: {ok_result}")
        assert "kaj korte parlam na" not in ok_result, "OK should not show as error"
        
        # Test SUCCESS result (should work as before)
        success_result = _format_direct_app_response(
            'close_app',
            'Notepad',
            'SUCCESS: Closed Notepad',
            'banglish'
        )
        print(f"✅ SUCCESS test: {success_result}")
        assert "close kore dilam" in success_result, "SUCCESS should show success message"
        
        # Test ERR result (should show error)
        err_result = _format_direct_app_response(
            'close_app',
            'Notepad',
            'ERR: Could not find Notepad',
            'banglish'
        )
        print(f"✅ ERR test: {err_result}")
        assert "kaj korte parlam na" in err_result, "ERR should show error message"
        
        print("🎉 All message formatting tests PASSED!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

def test_camera_timeout():
    """Test camera photo timeout increase."""
    try:
        from backend.tools.system.camera import take_camera_photo
        import inspect
        
        # Check default timeout changed from 5.0 to 15.0
        sig = inspect.signature(take_camera_photo)
        timeout_default = sig.parameters['timeout'].default
        
        print(f"🧪 Camera timeout test: {timeout_default}s")
        assert timeout_default == 15.0, f"Expected 15.0s timeout, got {timeout_default}s"
        print("✅ Camera timeout increased to 15s")
        return True
        
    except Exception as e:
        print(f"❌ Camera test failed: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing Maya bug fixes...\n")
    
    success = True
    success &= test_message_formatting()
    success &= test_camera_timeout()
    
    if success:
        print("\n🎉 ALL TESTS PASSED - Bug fixes working correctly!")
        exit(0)
    else:
        print("\n❌ Some tests failed")
        exit(1)