"""
Test User Skills Loading and Functionality
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

def test_skills_exist():
    """Test that all user skills are present"""
    skills_dir = Path("backend/skills/user_skills")
    
    expected_skills = [
        "code_reviewer",
        "bug_hunter",
        "productivity_coach",
        "meeting_assistant",
        "learning_tutor",
        "health_reminder",
        "file_organizer",
        "system_optimizer"
    ]
    
    print("\n" + "="*50)
    print("🎯 TESTING USER SKILLS")
    print("="*50 + "\n")
    
    found_skills = []
    missing_skills = []
    
    for skill in expected_skills:
        skill_path = skills_dir / skill / "skill.md"
        if skill_path.exists():
            found_skills.append(skill)
            
            # Read and validate skill file
            content = skill_path.read_text(encoding='utf-8')
            
            # Check for required sections
            has_name = "name:" in content
            has_description = "description:" in content
            has_emoji = "emoji:" in content
            has_instructions = "## Instructions" in content
            
            status = "✅" if all([has_name, has_description, has_emoji, has_instructions]) else "⚠️"
            
            # Get file size
            size_kb = skill_path.stat().st_size / 1024
            
            print(f"{status} {skill.replace('_', ' ').title()}")
            print(f"   📄 File: {skill_path.name}")
            print(f"   📊 Size: {size_kb:.1f} KB")
            
            if not all([has_name, has_description, has_emoji, has_instructions]):
                print(f"   ⚠️  Missing sections:")
                if not has_name: print("      - name")
                if not has_description: print("      - description")
                if not has_emoji: print("      - emoji")
                if not has_instructions: print("      - instructions")
            print()
        else:
            missing_skills.append(skill)
            print(f"❌ {skill.replace('_', ' ').title()}")
            print(f"   Missing: {skill_path}")
            print()
    
    print("="*50)
    print(f"📊 SUMMARY")
    print("="*50)
    print(f"✅ Found: {len(found_skills)}/{len(expected_skills)}")
    print(f"❌ Missing: {len(missing_skills)}/{len(expected_skills)}")
    print()
    
    if found_skills:
        print("✅ Working Skills:")
        for skill in found_skills:
            print(f"   • {skill.replace('_', ' ').title()}")
    
    if missing_skills:
        print("\n❌ Missing Skills:")
        for skill in missing_skills:
            print(f"   • {skill.replace('_', ' ').title()}")
    
    print("\n" + "="*50)
    
    return len(found_skills) == len(expected_skills)


def test_skill_loader():
    """Test skill loader module"""
    print("\n" + "="*50)
    print("🔧 TESTING SKILL LOADER")
    print("="*50 + "\n")
    
    try:
        from backend.skills.loader import load_registry, verify_and_load_plugin
        
        print("✅ Skill loader imported successfully")
        
        # Test registry loading
        registry = load_registry()
        print(f"✅ Registry loaded: {len(registry)} entries")
        
        print("\n📋 Registry Contents:")
        if registry:
            for name, hash_val in registry.items():
                print(f"   • {name}: {hash_val[:16]}...")
        else:
            print("   (Empty - no registered plugins yet)")
        
        print("\n" + "="*50)
        return True
        
    except Exception as e:
        print(f"❌ Error loading skill loader: {e}")
        print("="*50)
        return False


def test_builtin_skills():
    """Test built-in skills"""
    print("\n" + "="*50)
    print("📚 TESTING BUILT-IN SKILLS")
    print("="*50 + "\n")
    
    builtin_dir = Path("backend/skills/builtin")
    
    expected_builtin = ["screen_reader", "skill_creator", "summarize"]
    
    for skill in expected_builtin:
        skill_path = builtin_dir / skill / "skill.md"
        if skill_path.exists():
            size_kb = skill_path.stat().st_size / 1024
            print(f"✅ {skill.replace('_', ' ').title()}")
            print(f"   📊 Size: {size_kb:.1f} KB")
        else:
            print(f"❌ {skill.replace('_', ' ').title()} - Missing")
        print()
    
    print("="*50)
    return True


def test_skill_content_quality():
    """Test quality of skill content"""
    print("\n" + "="*50)
    print("✨ SKILL QUALITY ANALYSIS")
    print("="*50 + "\n")
    
    skills_dir = Path("backend/skills/user_skills")
    
    total_lines = 0
    total_chars = 0
    skill_stats = []
    
    for skill_folder in skills_dir.iterdir():
        if skill_folder.is_dir() and skill_folder.name != "__pycache__":
            skill_md = skill_folder / "skill.md"
            if skill_md.exists():
                content = skill_md.read_text(encoding='utf-8')
                lines = content.count('\n')
                chars = len(content)
                
                total_lines += lines
                total_chars += chars
                
                # Count examples in content
                examples = content.lower().count('example')
                code_blocks = content.count('```')
                
                skill_stats.append({
                    'name': skill_folder.name,
                    'lines': lines,
                    'chars': chars,
                    'examples': examples,
                    'code_blocks': code_blocks
                })
    
    # Sort by lines (largest first)
    skill_stats.sort(key=lambda x: x['lines'], reverse=True)
    
    print("📊 Skill Content Statistics:\n")
    
    for stat in skill_stats:
        print(f"📝 {stat['name'].replace('_', ' ').title()}")
        print(f"   Lines: {stat['lines']}")
        print(f"   Characters: {stat['chars']:,}")
        print(f"   Examples: {stat['examples']}")
        print(f"   Code blocks: {stat['code_blocks']}")
        print()
    
    print("="*50)
    print(f"📊 TOTAL STATISTICS")
    print("="*50)
    print(f"Total Skills: {len(skill_stats)}")
    print(f"Total Lines: {total_lines:,}")
    print(f"Total Characters: {total_chars:,}")
    print(f"Average Lines per Skill: {total_lines // max(len(skill_stats), 1)}")
    print("="*50)
    
    return True


if __name__ == "__main__":
    print("\n" + "🚀 " * 20)
    print("MAYA AI - USER SKILLS COMPREHENSIVE TEST")
    print("🚀 " * 20)
    
    results = []
    
    # Run tests
    results.append(("Skills Exist", test_skills_exist()))
    results.append(("Skill Loader", test_skill_loader()))
    results.append(("Built-in Skills", test_builtin_skills()))
    results.append(("Content Quality", test_skill_content_quality()))
    
    # Final report
    print("\n" + "="*50)
    print("🎯 FINAL TEST REPORT")
    print("="*50 + "\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "="*50)
    print(f"Score: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Skills are ready to use!")
    else:
        print(f"⚠️  {total - passed} test(s) failed. Check output above.")
    
    print("="*50 + "\n")
