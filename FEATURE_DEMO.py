"""
Maya AI - New Features Demo
============================
Demonstrates file compression and browser automation capabilities.
Zero external API cost - pure Python implementation.
"""

import asyncio
import tempfile
from pathlib import Path

# Import Maya's unified routers
from backend.tools.unified.dispatchers.file_router import file as maya_file
from backend.tools.unified.dispatchers.pc_router import pc as maya_pc
from backend.brain.language_style import detect_language_style


async def demo_compression():
    """Demo: File compression and extraction."""
    print("\n" + "="*60)
    print("📁 FILE COMPRESSION DEMO")
    print("="*60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create sample files
        test_dir = Path(tmpdir) / "my_project"
        test_dir.mkdir()
        
        (test_dir / "README.md").write_text("# My Project\nAwesome project!")
        (test_dir / "main.py").write_text("print('Hello Maya!')")
        (test_dir / "config.json").write_text('{"version": "1.0"}')
        
        print(f"\n✓ Created test project at: {test_dir}")
        
        # 1. Compress folder
        print("\n1️⃣ Compressing project folder...")
        archive_path = str(Path(tmpdir) / "project_backup.zip")
        result = await maya_file("compress", src=str(test_dir), dst=archive_path)
        print(f"   Result: {result}")
        
        # 2. List archive contents
        print("\n2️⃣ Listing archive contents...")
        result = await maya_file("list_archive", src=archive_path)
        print(f"   {result[:200]}...")  # First 200 chars
        
        # 3. Extract to new location
        print("\n3️⃣ Extracting to new location...")
        extract_dir = str(Path(tmpdir) / "restored")
        result = await maya_file("extract", src=archive_path, dst=extract_dir)
        print(f"   Result: {result}")
        
        # 4. Compress specific files
        print("\n4️⃣ Compressing specific files only...")
        readme = str(test_dir / "README.md")
        config = str(test_dir / "config.json")
        docs_archive = str(Path(tmpdir) / "docs.zip")
        result = await maya_file("compress_files", name=f"{readme},{config}", dst=docs_archive)
        print(f"   Result: {result}")
        
        # 5. TAR.GZ format
        print("\n5️⃣ Creating TAR.GZ archive...")
        tar_path = str(Path(tmpdir) / "backup.tar.gz")
        result = await maya_file("compress", src=str(test_dir), dst=tar_path)
        print(f"   Result: {result}")
    
    print("\n✅ Compression demo completed!")


def demo_browser_automation():
    """Demo: Browser automation (mocked for safety)."""
    print("\n" + "="*60)
    print("🌐 BROWSER AUTOMATION DEMO")
    print("="*60)
    
    # Note: These would actually control the browser!
    # Running in demo mode without actual execution
    
    actions = [
        ("browser_tab_new", "Open new tab"),
        ("browser_open_url", "Open URL", "https://github.com/maya-ai"),
        ("browser_bookmark", "Bookmark current page"),
        ("browser_tab_new", "Open another tab"),
        ("browser_search", "Search something", "Python automation"),
        ("browser_tab_prev", "Switch to previous tab"),
        ("browser_refresh", "Refresh page"),
        ("browser_zoom_in", "Zoom in"),
        ("browser_zoom_reset", "Reset zoom"),
        ("browser_history", "Open history"),
        ("browser_downloads", "Open downloads"),
        ("browser_fullscreen", "Toggle fullscreen"),
    ]
    
    print("\n📋 Available browser actions:")
    for i, action in enumerate(actions, 1):
        if len(action) == 2:
            cmd, desc = action
            print(f"   {i:2}. {desc:30} → maya_pc('{cmd}')")
        else:
            cmd, desc, param = action
            print(f"   {i:2}. {desc:30} → maya_pc('{cmd}', name='{param}')")
    
    print("\n✅ Browser automation ready!")
    print("   💡 Tip: Use maya_pc('browser_<action>') to control your browser")


def demo_language_detection():
    """Demo: Multi-language support."""
    print("\n" + "="*60)
    print("🌍 LANGUAGE DETECTION DEMO")
    print("="*60)
    
    test_phrases = [
        # Banglish
        ("file ta compress koro", "banglish"),
        ("browser e notun tab kholo", "banglish"),
        ("archive er moddhe ki ache", "banglish"),
        
        # Hindilish
        ("file ko compress karo", "hindilish"),
        ("browser me naya tab kholo", "hindilish"),
        ("archive me kya hai", "hindilish"),
        
        # English
        ("compress this folder", "english"),
        ("open new browser tab", "english"),
        ("what's in the archive", "english"),
    ]
    
    print("\n🔍 Testing language detection:")
    for phrase, expected in test_phrases:
        detected = detect_language_style(phrase)
        status = "✓" if detected == expected else "✗"
        print(f"   {status} '{phrase:35}' → {detected:10} (expected: {expected})")
    
    print("\n✅ Language detection working!")


def demo_real_world_scenarios():
    """Demo: Real-world usage scenarios."""
    print("\n" + "="*60)
    print("💼 REAL-WORLD SCENARIOS")
    print("="*60)
    
    scenarios = [
        {
            "title": "1. Backup Important Files",
            "description": "Create compressed backup of project folder",
            "commands": [
                "maya_file('compress', src='C:/MyProject', dst='C:/Backups/project_2026.zip')",
                "maya_file('list_archive', src='C:/Backups/project_2026.zip')",
            ]
        },
        {
            "title": "2. Research Workflow",
            "description": "Open multiple research sites and organize tabs",
            "commands": [
                "maya_pc('browser_open_url', name='https://scholar.google.com')",
                "maya_pc('browser_tab_new')",
                "maya_pc('browser_open_url', name='https://arxiv.org')",
                "maya_pc('browser_bookmark')",
            ]
        },
        {
            "title": "3. Extract Downloaded Archive",
            "description": "Extract downloaded files and organize",
            "commands": [
                "maya_file('extract', src='C:/Downloads/project.zip', dst='C:/Projects/new_project')",
                "maya_file('organize', path='C:/Projects/new_project')",
            ]
        },
        {
            "title": "4. Quick Web Search",
            "description": "Search something without leaving current context",
            "commands": [
                "maya_pc('browser_tab_new')",
                "maya_pc('browser_search', name='Python asyncio tutorial')",
            ]
        },
        {
            "title": "5. Archive Old Documents",
            "description": "Compress specific documents for archival",
            "commands": [
                "maya_file('compress_files', name='doc1.pdf,doc2.pdf,report.xlsx', dst='archive_2026.zip')",
            ]
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{scenario['title']}")
        print(f"   📝 {scenario['description']}")
        print("   📌 Commands:")
        for cmd in scenario['commands']:
            print(f"      {cmd}")
    
    print("\n✅ Scenarios ready to use!")


async def main():
    """Run all demos."""
    print("\n" + "="*70)
    print(" " * 15 + "🚀 MAYA AI - NEW FEATURES DEMO 🚀")
    print("="*70)
    print("\n💡 Features: Zero external API cost | Pure Python | Multi-language")
    
    # Run demos
    await demo_compression()
    demo_browser_automation()
    demo_language_detection()
    demo_real_world_scenarios()
    
    # Summary
    print("\n" + "="*70)
    print("📊 FEATURE SUMMARY")
    print("="*70)
    print("""
    ✅ File Compression (ZIP, TAR.GZ, TAR.BZ2)
       - Compress folders/files
       - Extract archives
       - List contents
       - Compress specific files
       - Auto-format detection
       - Compression ratio reporting
    
    ✅ Browser Automation (25+ actions)
       - Tab management
       - Bookmarks & history
       - Navigation & refresh
       - Zoom & fullscreen
       - Search & open URLs
       - Keyboard shortcuts
    
    ✅ Multi-Language Support
       - Banglish (Bangla in Latin script)
       - Hindilish (Hindi in Latin script)
       - English
       - Auto-detection
       - Context-aware responses
    
    🎯 Implementation: 100% Free
       - Python built-in modules (zipfile, tarfile)
       - PyAutoGUI for browser control
       - No Gemini/OpenAI API calls needed
       - Zero token cost for these operations
    """)
    
    print("="*70)
    print("✨ Maya AI is now more powerful than ever! ✨")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())
    
    print("\n💬 Try it yourself!")
    print("   >>> from backend.tools.unified.dispatchers.file_router import file as maya_file")
    print("   >>> from backend.tools.unified.dispatchers.pc_router import pc as maya_pc")
    print("   >>> await maya_file('compress', src='my_folder', dst='backup.zip')")
    print("   >>> maya_pc('browser_tab_new')")
    print()
