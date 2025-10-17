#!/usr/bin/env python3
"""
Test script to verify Langfuse integration.

Usage:
    python scripts/test_langfuse.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set environment variables for testing (optional)
os.environ.setdefault("LANGFUSE_ENABLED", "true")

def test_langfuse_config():
    """Test that Langfuse configuration is present."""
    print("🧪 Testing Langfuse Configuration...")
    print("-" * 60)
    
    required_vars = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
    optional_vars = ["LANGFUSE_HOST", "LANGFUSE_ENABLED"]
    
    all_ok = True
    
    # Check required variables
    for var in required_vars:
        value = os.getenv(var)
        if value:
            masked_value = value[:10] + "..." if len(value) > 10 else value
            print(f"✅ {var}: {masked_value}")
        else:
            print(f"❌ {var}: NOT SET")
            all_ok = False
    
    # Check optional variables
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            print(f"ℹ️  {var}: {value}")
        else:
            print(f"⚠️  {var}: NOT SET (using default)")
    
    print("-" * 60)
    return all_ok


def test_langfuse_import():
    """Test that Langfuse package can be imported."""
    print("\n🧪 Testing Langfuse Package...")
    print("-" * 60)
    
    try:
        # Try v3 API first
        try:
            from langfuse.langchain import CallbackHandler as LangfuseCallback
            api_version = "v3 (langchain)"
        except ImportError:
            # Fallback to v2 API
            from langfuse.callback import CallbackHandler as LangfuseCallback
            api_version = "v2 (callback)"
        
        print(f"✅ Langfuse package imported successfully ({api_version})")
        
        # Try to get version
        try:
            import langfuse
            if hasattr(langfuse, '__version__'):
                print(f"ℹ️  Langfuse version: {langfuse.__version__}")
        except:
            pass
        
        return True
    except ImportError as e:
        print(f"❌ Failed to import Langfuse: {e}")
        print("💡 Install with: pip install langfuse")
        return False


def test_llm_provider():
    """Test that LLM provider can initialize with Langfuse."""
    print("\n🧪 Testing LLM Provider with Langfuse...")
    print("-" * 60)
    
    try:
        from apps.agent_service.llm_provider import get_llm
        
        # Test with user_id and session_id
        llm = get_llm(
            stream=False,
            user_id="test_user",
            session_id="test_session_123"
        )
        
        print("✅ LLM provider initialized successfully")
        print(f"ℹ️  Model: {llm.model_name}")
        print(f"ℹ️  Callbacks: {len(llm.callbacks)} registered")
        
        # Check if Langfuse callback is present
        try:
            from langfuse.langchain import CallbackHandler as LangfuseCallback
        except ImportError:
            from langfuse.callback import CallbackHandler as LangfuseCallback
        has_langfuse = any(isinstance(cb, LangfuseCallback) for cb in llm.callbacks)
        
        if has_langfuse:
            print("✅ Langfuse callback is registered")
        else:
            print("⚠️  Langfuse callback NOT registered (check LANGFUSE_ENABLED and API keys)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error initializing LLM: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simple_call():
    """Test a simple LLM call with Langfuse tracking."""
    print("\n🧪 Testing Simple LLM Call...")
    print("-" * 60)
    
    try:
        from apps.agent_service.llm_provider import get_llm
        
        llm = get_llm(
            stream=False,
            user_id="test_user",
            session_id="test_session_simple_call"
        )
        
        print("📤 Sending test message to LLM...")
        response = llm.invoke("Say 'Hello from Smart Scout!' in Spanish")
        
        print(f"✅ Response received: {response.content}")
        print("\n💡 Check Langfuse Dashboard to see this trace:")
        print(f"   https://cloud.langfuse.com")
        print(f"   User ID: test_user")
        print(f"   Session ID: test_session_simple_call")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during LLM call: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🚀 LANGFUSE INTEGRATION TEST")
    print("=" * 60)
    
    results = []
    
    # Test 1: Configuration
    results.append(("Configuration", test_langfuse_config()))
    
    # Test 2: Package import
    results.append(("Package Import", test_langfuse_import()))
    
    # Only continue if package is installed
    if results[-1][1]:
        # Test 3: LLM Provider
        results.append(("LLM Provider", test_llm_provider()))
        
        # Test 4: Simple call (optional, requires API key)
        if os.getenv("OPENAI_API_KEY"):
            do_live_test = input("\n💡 Do you want to test a live LLM call? (y/n): ").lower()
            if do_live_test == 'y':
                results.append(("Live LLM Call", test_simple_call()))
        else:
            print("\n⚠️  Skipping live LLM call test (OPENAI_API_KEY not set)")
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n🎉 All tests passed! Langfuse integration is ready.")
        print("\n📝 Next steps:")
        print("   1. Make sure LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are in your .env")
        print("   2. Restart your Docker services: docker-compose restart api")
        print("   3. Use the app and check traces at https://cloud.langfuse.com")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
        print("\n📝 Troubleshooting:")
        print("   1. Install Langfuse: pip install langfuse")
        print("   2. Get API keys from: https://cloud.langfuse.com/auth/sign-up")
        print("   3. Add keys to your .env file")
    
    print("=" * 60 + "\n")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

