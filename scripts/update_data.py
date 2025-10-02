#!/usr/bin/env python3
"""
Script para actualizar datos históricos de jugadores
Uso: python scripts/update_data.py --season 2025-26
"""

import argparse
import pandas as pd
from pathlib import Path
import shutil
from datetime import datetime

def update_historical_data(season: str = None):
    """
    Actualiza los datos históricos con nueva temporada
    
    Args:
        season: Nueva temporada a añadir (ej: "2025-26")
    """
    print("🔄 Actualizando datos históricos...")
    
    # Rutas
    scrapper_data = Path("notebooks/scrapper/data")
    processed_data = Path("data/processed")
    
    # Verificar que existe el archivo de datos históricos
    historical_file = scrapper_data / "all_players_plus_historic_data_v2.csv"
    if not historical_file.exists():
        print("❌ No se encontró el archivo de datos históricos")
        print(f"   Buscando en: {historical_file}")
        return False
    
    # Crear backup del archivo actual
    backup_file = processed_data / f"players_with_historical_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    current_file = processed_data / "players_with_historical_data.csv"
    
    if current_file.exists():
        shutil.copy2(current_file, backup_file)
        print(f"📁 Backup creado: {backup_file.name}")
    
    # Copiar archivo actualizado
    shutil.copy2(historical_file, current_file)
    print(f"✅ Datos actualizados: {current_file}")
    
    # Mostrar estadísticas
    df = pd.read_csv(current_file)
    print(f"\n📊 Estadísticas:")
    print(f"   Total jugadores: {len(df):,}")
    print(f"   Activos: {len(df[df.player_status == 'active']):,}")
    print(f"   Retirados: {len(df[df.player_status == 'retired or inactive']):,}")
    
    if season:
        print(f"   Nueva temporada añadida: {season}")
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Actualizar datos históricos de jugadores")
    parser.add_argument("--season", help="Nueva temporada a añadir (ej: 2025-26)")
    parser.add_argument("--force", action="store_true", help="Forzar actualización sin confirmación")
    
    args = parser.parse_args()
    
    if not args.force:
        response = input("¿Continuar con la actualización? (y/N): ")
        if response.lower() != 'y':
            print("❌ Actualización cancelada")
            return
    
    success = update_historical_data(args.season)
    
    if success:
        print("\n🎉 ¡Actualización completada exitosamente!")
        print("💡 Recuerda ejecutar la ingesta a la base de datos:")
        print("   python -m apps.ingestion.seed_and_ingest --players-csv data/processed/players_with_historical_data.csv --verbose --refresh-embs --replace")
    else:
        print("\n❌ Error en la actualización")

if __name__ == "__main__":
    main()
