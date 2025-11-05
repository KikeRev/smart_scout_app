#!/usr/bin/env python3
"""
Test completo de Langfuse - envía un trace real y verifica que funciona.
"""

import os
import sys
import time
import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.agent_service.llm_provider import get_llm

def main():
    print("=" * 60)
    print("🚀 PRUEBA COMPLETA DE LANGFUSE")
    print("=" * 60)
    print()
    
    # Generate unique session ID
    session_id = f"test_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    user_id = "test_user_langfuse"
    
    print(f"📋 Configuración:")
    print(f"   User ID: {user_id}")
    print(f"   Session ID: {session_id}")
    print()
    
    # Initialize LLM with Langfuse
    print("🔧 Inicializando LLM con Langfuse...")
    try:
        llm = get_llm(
            stream=False,
            user_id=user_id,
            session_id=session_id
        )
        print("✅ LLM inicializado correctamente")
        print()
    except Exception as e:
        print(f"❌ Error al inicializar LLM: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Make a real LLM call
    print("📤 Enviando pregunta al LLM...")
    print("   Pregunta: '¿Cuál es el mejor jugador de fútbol del mundo? Responde en una frase corta.'")
    print()
    
    try:
        response = llm.invoke(
            "¿Cuál es el mejor jugador de fútbol del mundo? Responde en una frase corta."
        )
        print(f"✅ Respuesta recibida: {response.content}")
        print()
        
        # Check token usage if available
        if hasattr(response, 'response_metadata') and 'token_usage' in response.response_metadata:
            usage = response.response_metadata['token_usage']
            print("📊 Token usage:")
            print(f"   Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
            print(f"   Completion tokens: {usage.get('completion_tokens', 'N/A')}")
            print(f"   Total tokens: {usage.get('total_tokens', 'N/A')}")
            print()
        
    except Exception as e:
        print(f"❌ Error durante la llamada al LLM: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Wait for Langfuse to process
    print("⏳ Esperando 3 segundos para que Langfuse procese el trace...")
    time.sleep(3)
    print()
    
    # Summary
    print("=" * 60)
    print("✅ PRUEBA COMPLETADA")
    print("=" * 60)
    print()
    print("📊 Verifica el trace en Langfuse:")
    print("   URL: https://cloud.langfuse.com")
    print(f"   Busca por user_id: {user_id}")
    print(f"   Session ID: {session_id}")
    print()
    print("💡 El trace debería aparecer en:")
    print("   - Dashboard → Traces")
    print("   - Buscar por: user_id = test_user_langfuse")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

