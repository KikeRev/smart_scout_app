# DVC Implementation Guide

## ¿Qué es DVC?

DVC (Data Version Control) es una herramienta que permite versionar datos de la misma manera que Git versiona código. Es especialmente útil para proyectos de ML/Data Science.

## Ventajas para Smart Scout App

### 1. **Versionado de Datos**
- Diferentes versiones de datasets históricos
- Seguimiento de cambios en datos
- Rollback a versiones anteriores

### 2. **Colaboración**
- Compartir datasets entre desarrolladores
- Sincronización automática de datos
- Resolución de conflictos

### 3. **Reproducibilidad**
- Experimentos reproducibles
- Trazabilidad completa de datos
- Pipeline de datos versionado

## Implementación Recomendada

### Estructura de Datos con DVC
```
data/
├── raw/                    # Datos originales (no versionados)
│   ├── 2024-25/
│   ├── 2023-24/
│   └── historical/
├── processed/              # Datos procesados (versionados con DVC)
│   ├── players_2024-25.csv
│   ├── players_historical.csv
│   └── players_consolidated.csv
└── .dvc/                  # Metadatos de DVC
```

### Comandos Básicos

```bash
# Inicializar DVC
dvc init

# Añadir datos al control de versiones
dvc add data/processed/players_with_historical_data.csv

# Commit cambios
git add data/processed/players_with_historical_data.csv.dvc
git commit -m "Add historical players data v1.0"

# Push datos a storage remoto
dvc push

# Pull datos desde storage remoto
dvc pull
```

### Pipeline de Datos
```yaml
# dvc.yaml
stages:
  scrape_historical:
    cmd: python notebooks/scrapper/historical_fbref_scraper.py
    deps:
    - notebooks/scrapper/historical_fbref_scraper.py
    - notebooks/scrapper/historic_leagues_links.json
    outs:
    - data/raw/historical_players_raw.csv

  aggregate_data:
    cmd: python notebooks/scrapper/aggregate_final.py
    deps:
    - data/raw/historical_players_raw.csv
    - data/raw/all_players_cleaned.csv
    outs:
    - data/processed/players_with_historical_data.csv

  ingest_to_db:
    cmd: python -m apps.ingestion.seed_and_ingest --players-csv data/processed/players_with_historical_data.csv --verbose --refresh-embs --replace
    deps:
    - data/processed/players_with_historical_data.csv
```

## Configuración de Storage

### Opción 1: Google Drive
```bash
dvc remote add -d storage gdrive://your-folder-id
```

### Opción 2: AWS S3
```bash
dvc remote add -d storage s3://your-bucket-name
```

### Opción 3: Local Storage
```bash
dvc remote add -d storage /path/to/local/storage
```

## Workflow Recomendado

### 1. **Nueva Temporada**
```bash
# 1. Scrapear nuevos datos
python notebooks/scrapper/historical_fbref_scraper.py

# 2. Procesar y agregar
python notebooks/scrapper/aggregate_final.py

# 3. Añadir a DVC
dvc add data/processed/players_with_historical_data.csv

# 4. Commit cambios
git add .
git commit -m "Add 2025-26 season data"

# 5. Push datos
dvc push
git push
```

### 2. **Colaboración**
```bash
# Pull código
git pull

# Pull datos
dvc pull

# Ejecutar pipeline
dvc repro
```

## Migración desde Estado Actual

### Paso 1: Inicializar DVC
```bash
cd /path/to/smart_scout_app
dvc init
git add .dvc
git commit -m "Initialize DVC"
```

### Paso 2: Configurar Storage
```bash
# Ejemplo con Google Drive
dvc remote add -d storage gdrive://your-folder-id
```

### Paso 3: Añadir Datos Actuales
```bash
dvc add data/processed/players_with_historical_data.csv
git add data/processed/players_with_historical_data.csv.dvc
git commit -m "Add current historical data to DVC"
dvc push
```

### Paso 4: Crear Pipeline
```bash
# Crear dvc.yaml con pipeline completo
# Ejecutar pipeline
dvc repro
```

## Beneficios Inmediatos

1. **Trazabilidad**: Saber exactamente qué datos se usaron en cada versión
2. **Rollback**: Volver a versiones anteriores de datos
3. **Colaboración**: Compartir datos entre desarrolladores
4. **Storage Eficiente**: Solo almacenar diferencias
5. **Reproducibilidad**: Replicar exactamente el mismo entorno

## Consideraciones

### Pros
- ✅ Versionado profesional de datos
- ✅ Colaboración mejorada
- ✅ Reproducibilidad garantizada
- ✅ Integración con Git
- ✅ Storage eficiente

### Contras
- ❌ Curva de aprendizaje
- ❌ Configuración inicial compleja
- ❌ Dependencia de storage externo
- ❌ Overhead para proyectos pequeños

## Recomendación

**Para Smart Scout App**: Implementar DVC es recomendable si:
- Planeas añadir nuevas temporadas regularmente
- Trabajas en equipo
- Necesitas reproducibilidad estricta
- Quieres un pipeline de datos profesional

**Alternativa Simple**: Mantener el sistema actual con gitignore + documentación si:
- Es un proyecto personal/small team
- Los datos no cambian frecuentemente
- La simplicidad es prioritaria
