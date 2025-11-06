#!/usr/bin/env python3
"""
Verifica que los traces se estén enviando correctamente a Langfuse.
"""

import os
import sys
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    print("=" * 60)
    print("🔍 VERIFICANDO TRACES EN LANGFUSE")
    print("=" * 60)
    print()
    
    # Get credentials
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    
    if not pk or not sk:
        print("❌ LANGFUSE_PUBLIC_KEY o LANGFUSE_SECRET_KEY no están configuradas")
        return 1
    
    # Query traces
    print(f"📡 Consultando API de Langfuse...")
    print(f"   Host: {host}")
    print()
    
    try:
        response = requests.get(
            f"{host}/api/public/traces",
            auth=(pk, sk),
            params={"limit": 10},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            traces = data.get("data", [])
            
            print(f"✅ Conexión exitosa con Langfuse")
            print(f"📊 Total de traces encontrados: {len(traces)}")
            print()
            
            if traces:
                print("📋 Últimos traces:")
                print("-" * 60)
                for i, trace in enumerate(traces[:5], 1):
                    trace_id = trace.get("id", "N/A")
                    user_id = trace.get("userId", "N/A")
                    session_id = trace.get("sessionId", "N/A")
                    timestamp = trace.get("timestamp", "N/A")
                    name = trace.get("name", "N/A")
                    
                    print(f"Trace {i}:")
                    print(f"   ID: {trace_id}")
                    print(f"   Name: {name}")
                    print(f"   User ID: {user_id}")
                    print(f"   Session ID: {session_id}")
                    print(f"   Timestamp: {timestamp}")
                    print()
                
                # Check for our test trace
                test_traces = [t for t in traces if t.get("userId") == "test_user_langfuse"]
                if test_traces:
                    print("✅ Trace de prueba encontrado!")
                    print(f"   Se encontraron {len(test_traces)} trace(s) con user_id='test_user_langfuse'")
                else:
                    print("⚠️  No se encontró el trace de prueba (user_id='test_user_langfuse')")
                    print("   Puede que aún esté procesándose. Intenta en unos segundos.")
            else:
                print("⚠️  No se encontraron traces")
                print("   Esto puede ser normal si es la primera vez que usas Langfuse")
            
        else:
            print(f"❌ Error al consultar API: Status {response.status_code}")
            print(f"   Respuesta: {response.text[:200]}")
            return 1
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error de conexión: {e}")
        return 1
    
    print()
    print("=" * 60)
    print("💡 Verifica también en el dashboard:")
    print(f"   {host}")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

