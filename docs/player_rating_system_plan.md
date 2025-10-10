# Plan: Sistema de Rating de Jugadores (Estilo FIFA 25-26)

## 📊 Análisis de Datos Disponibles

### Datos Actuales en la BD
Basado en el modelo `Player` y `PlayerHistory`, tenemos las siguientes categorías de datos:

#### 1. **Información Básica**
- `full_name`, `age`, `nationality`, `position`, `club`, `league`
- `minutes`, `minutes_90s`, `games`, `games_starts`

#### 2. **Métricas Ofensivas**
- `goals`, `assists`
- `expected_goals` (xG), `expected_assists` (xA)
- `no_penalty_expected_goals_plus_expected_assists`
- Per 90: `goals_per90`, `assists_per90`, `goals_assists_per90`
- Per 90 xG: `expected_goals_per90`, `expected_assists_per90`, `expected_goals_assists_per90`

#### 3. **Métricas de Progresión**
- `progressive_carries`: Conducciones progresivas
- `progressive_passes`: Pases progresivos
- `progressive_passes_received`: Pases progresivos recibidos

#### 4. **Métricas de Pase**
- `passes_completed`, `passes`, `passes_pct`
- `passes_progressive_distance`
- `passes_completed_long`, `passes_long`, `passes_pct_long`

#### 5. **Métricas Defensivas**
- `tackles`, `tackles_won`, `challenge_tackles`, `challenges`, `challenge_tackles_pct`, `challenges_lost`
- `interceptions`, `blocks`, `blocked_shots`, `blocked_passes`
- `clearances`, `errors`
- `tackles_interceptions`

#### 6. **Métricas de Portero**
- `gk_goals_against`, `gk_pens_allowed`
- `gk_free_kick_goals_against`, `gk_corner_kick_goals_against`, `gk_own_goals_against`
- `gk_psxg`: Post-Shot Expected Goals
- `gk_psnpxg_per_shot_on_target_against`

---

## 🎯 Sistema de Rating FIFA: Análisis Conceptual

### Estructura de Rating FIFA
FIFA utiliza un sistema de **6 atributos principales** que se combinan para calcular el OVR (Overall Rating):

1. **PAC (Pace)** - Velocidad
2. **SHO (Shooting)** - Tiro/Finalización
3. **PAS (Passing)** - Pase
4. **DRI (Dribbling)** - Regate/Control
5. **DEF (Defending)** - Defensa
6. **PHY (Physical)** - Físico

Cada atributo principal se calcula a partir de sub-atributos específicos.

### Limitaciones de Nuestros Datos
❌ **NO tenemos datos directos de:**
- Velocidad (Sprint Speed, Acceleration)
- Físico (Strength, Stamina, Aggression)
- Regate/Control (Dribbling, Ball Control, Agility)
- Tiro específico (Shot Power, Long Shots, Finishing)

✅ **SÍ tenemos datos que podemos usar como PROXIES:**
- **Shooting**: `goals`, `expected_goals`, `goals_per90` → Indica capacidad de finalización
- **Passing**: `passes_pct`, `passes_completed`, `progressive_passes` → Indica calidad de pase
- **Defending**: `tackles`, `interceptions`, `blocks`, `clearances` → Indica capacidad defensiva
- **Physical (proxy)**: `progressive_carries`, `challenges_won` → Indica fuerza en duelos
- **Pace (proxy limitado)**: `progressive_carries` → Jugadores rápidos hacen más conducciones progresivas
- **Dribbling (proxy)**: `progressive_carries`, `progressive_passes_received` → Indica control del balón

---

## 🧮 Propuesta de Sistema de Rating

### Enfoque: Rating Basado en Performance Stats

En lugar de replicar exactamente FIFA (que usa atributos físicos que no tenemos), crearemos un **sistema de rating basado en performance real** con 6 categorías similares:

#### 1. **ATTACKING (ATT)** - Capacidad Ofensiva
**Sub-métricas:**
- Goals per 90
- Expected Goals (xG) per 90
- Expected Assists (xA) per 90
- Assists per 90

**Fórmula:**
```
ATT = (
    goals_per90 * 30 +
    expected_goals_per90 * 25 +
    expected_assists_per90 * 25 +
    assists_per90 * 20
) / 100 * 100
```

**Normalización:** Escala 0-100 basada en percentiles de la liga

---

#### 2. **PLAYMAKING (PLY)** - Capacidad de Creación
**Sub-métricas:**
- Passes %
- Progressive Passes per 90
- Expected Assists per 90
- Passes Completed Long %

**Fórmula:**
```
PLY = (
    passes_pct * 30 +
    (progressive_passes / minutes_90s) * 30 +
    expected_assists_per90 * 25 +
    passes_pct_long * 15
) / 100 * 100
```

---

#### 3. **DEFENDING (DEF)** - Capacidad Defensiva
**Sub-métricas:**
- Tackles Won per 90
- Interceptions per 90
- Blocks per 90
- Challenge Success %

**Fórmula:**
```
DEF = (
    (tackles_won / minutes_90s) * 35 +
    (interceptions / minutes_90s) * 30 +
    (blocks / minutes_90s) * 20 +
    challenge_tackles_pct * 15
) / 100 * 100
```

---

#### 4. **BALL CONTROL (CTR)** - Control y Progresión
**Sub-métricas:**
- Progressive Carries per 90
- Progressive Passes Received per 90
- Progressive Passes per 90
- Passes %

**Fórmula:**
```
CTR = (
    (progressive_carries / minutes_90s) * 35 +
    (progressive_passes_received / minutes_90s) * 25 +
    (progressive_passes / minutes_90s) * 25 +
    passes_pct * 15
) / 100 * 100
```

---

#### 5. **PHYSICAL (PHY)** - Físico (Proxy)
**Sub-métricas:**
- Challenges Won per 90
- Progressive Carries per 90
- Tackles Won per 90

**Fórmula:**
```
PHY = (
    (challenges - challenges_lost) / minutes_90s * 40 +
    (progressive_carries / minutes_90s) * 35 +
    (tackles_won / minutes_90s) * 25
) / 100 * 100
```

---

#### 6. **GOALKEEPING (GKP)** - Portería (Solo GK)
**Sub-métricas:**
- PSxG (Post-Shot xG) - Positivo: Goles evitados vs esperados
- PSxG per Shot on Target Against - Mayor es mejor
- Goals Against per 90 - **INVERSA: Menos es mejor** ⚠️

**Fórmula (solo para GK):**
```
# Para Goals Against, invertimos: comparamos con el PEOR de la liga
GKP = (
    gk_psxg_normalized * 40 +
    gk_psnpxg_per_shot_normalized * 35 +
    goals_against_inverted_normalized * 25
) / 100 * 100

# Donde goals_against_inverted se calcula como:
# - Mejor portero (menos goles): 100 puntos
# - Peor portero (más goles): 0 puntos
```

**Nota sobre métricas inversas:** Ver sección de Normalización más abajo.

---

## 🔄 Cálculo del Overall Rating (OVR)

### Paso 1: Rating Base por Nivel de Liga

**Concepto:** Todos los jugadores profesionales tienen un nivel mínimo según la liga donde juegan.

#### Coeficientes de Liga (Base Rating)
Basado en ranking UEFA y nivel competitivo:

| Liga | País | Base Rating | Descripción |
|------|------|-------------|-------------|
| **Premier League** | Inglaterra | 60 | Top mundial |
| **La Liga** | España | 60 | Top mundial |
| **Serie A** | Italia | 58 | Elite europea |
| **Bundesliga** | Alemania | 58 | Elite europea |
| **Ligue 1** | Francia | 56 | Top 5 europea |
| **Eredivisie** | Países Bajos | 52 | Liga competitiva |
| **Liga NOS** | Portugal | 52 | Liga competitiva |
| **Championship** | Inglaterra | 50 | 2ª división top |
| **Ligas menores europeas** | Varios | 45-48 | Profesional estándar |
| **Ligas emergentes** | Varios | 40-44 | Profesional básico |

**Justificación:** Un jugador promedio en la Premier League ya es mejor que uno promedio en una liga menor, independientemente de las stats.

### Paso 2: Pesos por Posición

Cada posición tendrá pesos diferentes para los 6 atributos:

| Posición | ATT | PLY | DEF | CTR | PHY | GKP |
|----------|-----|-----|-----|-----|-----|-----|
| **GK**   | 0%  | 0%  | 10% | 0%  | 10% | 80% |
| **CB**   | 5%  | 10% | 50% | 10% | 25% | 0%  |
| **FB/WB**| 10% | 20% | 35% | 20% | 15% | 0%  |
| **DM**   | 10% | 25% | 40% | 15% | 10% | 0%  |
| **CM**   | 15% | 35% | 25% | 20% | 5%  | 0%  |
| **AM**   | 30% | 35% | 10% | 20% | 5%  | 0%  |
| **W**    | 35% | 25% | 5%  | 30% | 5%  | 0%  |
| **FW**   | 50% | 20% | 0%  | 25% | 5%  | 0%  |

### Paso 3: Cálculo del Performance Rating (solo stats)
```python
performance_rating = (
    ATT * weight_att +
    PLY * weight_ply +
    DEF * weight_def +
    CTR * weight_ctr +
    PHY * weight_phy +
    GKP * weight_gkp
) / 100
```

### Paso 4: Fórmula Final OVR (Base + Performance)
**Combinación ponderada** entre el nivel de liga y el rendimiento individual:

```python
def calculate_overall_rating(performance_rating, league_base_rating, minutes_played):
    """
    Combina el rating base de la liga con el performance rating.
    
    A más minutos → más peso al performance
    A menos minutos → más peso al base de liga
    """
    # Minutos de referencia
    FULL_SEASON = 3000
    
    # Calcular pesos (ajustable)
    LEAGUE_WEIGHT_MAX = 0.35  # Máximo 35% de peso para la liga
    PERF_WEIGHT_MAX = 0.65    # Mínimo 65% de peso para performance
    
    # Ajustar según minutos jugados
    minutes_factor = min(minutes_played / FULL_SEASON, 1.0)
    
    # Con pocos minutos, la liga pesa más
    league_weight = LEAGUE_WEIGHT_MAX * (1 - minutes_factor * 0.5)
    perf_weight = 1 - league_weight
    
    # Fórmula final
    overall = (league_base_rating * league_weight) + (performance_rating * perf_weight)
    
    return round(overall)
```

**Ejemplos:**

1. **Jugador Premier con 3000 min y performance 75:**
   - `OVR = (60 * 0.175) + (75 * 0.825) = 10.5 + 61.875 = 72` ✅
   
2. **Jugador Premier con 200 min y performance 80 (muestra pequeña):**
   - `OVR = (60 * 0.327) + (80 * 0.673) = 19.6 + 53.8 = 73` ✅ Regresión a base

3. **Jugador liga menor con 3000 min y performance 75:**
   - `OVR = (48 * 0.175) + (75 * 0.825) = 8.4 + 61.875 = 70` ✅ Penalizado por liga

4. **Estrella liga menor con 3000 min y performance 88:**
   - `OVR = (48 * 0.175) + (88 * 0.825) = 8.4 + 72.6 = 81` ✅ Puede destacar

---

## 📈 Normalización de Datos

### Paso 0: Identificar Tipo de Métrica

**Métricas Positivas** (más es mejor): 
- Goals, Assists, xG, xA, Tackles, Interceptions, Passes %, etc.

**Métricas Inversas** (menos es mejor): ⚠️
- `gk_goals_against` per 90
- `errors` per 90
- `challenges_lost` per 90
- `gk_pens_allowed` per 90

### Paso 1: Calcular Percentiles por Liga

#### A) Para Métricas Positivas (normal)
Para cada métrica, calculamos el percentil del jugador dentro de su liga:
- P99 → 100 puntos
- P90 → 90 puntos
- P50 → 50 puntos
- P10 → 10 puntos

**Fórmula:**
```python
normalized = (value - min_value) / (max_value - min_value) * 100
```

#### B) Para Métricas Inversas (invertida) ⚠️
Para métricas donde **menos es mejor**, invertimos el cálculo:

**Fórmula:**
```python
# Invertir: el mínimo se convierte en 100, el máximo en 0
normalized = (max_value - value) / (max_value - min_value) * 100
```

**Ejemplo - Goals Against per 90:**
```python
# Datos de la liga:
# - Mejor portero: 0.5 goles contra per 90 → 100 puntos
# - Peor portero: 2.0 goles contra per 90 → 0 puntos
# - Portero X: 0.8 goles contra per 90

normalized = (2.0 - 0.8) / (2.0 - 0.5) * 100
           = 1.2 / 1.5 * 100
           = 80 puntos ✅
```

### Paso 2: Ponderación por Minutos Jugados (Regresión a la Media)
**Problema:** Un jugador con 2 goles en 90 minutos tendría mejor ratio que Messi, pero es una muestra pequeña.

**Solución:** Usar **regresión a la media de la liga** basada en minutos:

```python
def weighted_stat_by_minutes(raw_stat_per90, league_avg_per90, minutes_played, is_inverse=False):
    """
    Pondera la estadística del jugador con la media de la liga
    según los minutos jugados.
    
    A más minutos → más peso a la stat real del jugador
    A menos minutos → más peso a la media de la liga
    
    Args:
        raw_stat_per90: Estadística del jugador per 90
        league_avg_per90: Media de la liga per 90
        minutes_played: Minutos jugados por el jugador
        is_inverse: True si menos es mejor (ej: goles en contra)
    """
    # Minutos de referencia (1 temporada completa ≈ 3000 min)
    FULL_SEASON_MINUTES = 3000
    
    # Minutos mínimos para considerar la muestra
    MIN_MINUTES = 90  # Al menos 1 partido
    
    if minutes_played < MIN_MINUTES:
        # Muy pocos minutos → usar solo la media de la liga
        return league_avg_per90
    
    # Calcular peso del jugador (0 a 1)
    player_weight = min(minutes_played / FULL_SEASON_MINUTES, 1.0)
    league_weight = 1.0 - player_weight
    
    # Regresión a la media
    weighted_stat = (raw_stat_per90 * player_weight) + (league_avg_per90 * league_weight)
    
    return weighted_stat
```

**Ejemplos - Métricas Positivas:**
- Jugador A: 2 goles en 90 min (2.0 per90), media liga: 0.5
  - `weighted = (2.0 * 0.03) + (0.5 * 0.97) = 0.54` ✅ Realista
  
- Messi: 35 goles en 3000 min (1.05 per90), media liga: 0.5
  - `weighted = (1.05 * 1.0) + (0.5 * 0.0) = 1.05` ✅ Sin penalización

**Ejemplos - Métricas Inversas (Porteros):**
- Portero novato: 0 goles en 90 min (0.0 per90), media liga: 1.2
  - `weighted = (0.0 * 0.03) + (1.2 * 0.97) = 1.16` ✅ No parece perfecto
  
- Portero titular: 30 goles en 3000 min (0.9 per90), media liga: 1.2
  - `weighted = (0.9 * 1.0) + (1.2 * 0.0) = 0.9` ✅ Confía en su rendimiento

**Caso especial - Porteros sin minutos:**
```python
# Si un portero tiene 0 minutos jugados:
# → Asignar la media de la liga (ni bueno ni malo)
# → Rating neutral basado en el nivel de la liga
```

### Paso 3: Aplicar Escalado Global
Escalar todas las métricas a rango 0-100 usando:
```python
scaled_value = (value - min_value) / (max_value - min_value) * 100
```

---

## 🛠️ Implementación Técnica

### Estructura de Archivos Propuesta

```
apps/
└── rating_system/
    ├── __init__.py
    ├── models.py              # PlayerRating model
    ├── calculator.py          # Core rating calculation logic
    ├── normalizers.py         # Data normalization functions
    ├── position_weights.py    # Position-specific weights
    ├── league_coefficients.py # League base ratings map
    ├── metrics_config.py      # Metrics definitions (positive/inverse)
    ├── management/
    │   └── commands/
    │       └── calculate_ratings.py  # Django command
    └── api/
        ├── serializers.py
        └── views.py           # API endpoints
```

### Configuración de Métricas (metrics_config.py)

```python
# Diccionario de métricas con sus propiedades
METRICS_CONFIG = {
    # Métricas positivas (más es mejor)
    'goals_per90': {'type': 'positive', 'category': 'attacking'},
    'assists_per90': {'type': 'positive', 'category': 'attacking'},
    'expected_goals_per90': {'type': 'positive', 'category': 'attacking'},
    'expected_assists_per90': {'type': 'positive', 'category': 'playmaking'},
    'passes_pct': {'type': 'positive', 'category': 'playmaking'},
    'progressive_passes_per90': {'type': 'positive', 'category': 'playmaking'},
    'progressive_carries_per90': {'type': 'positive', 'category': 'ball_control'},
    'tackles_won_per90': {'type': 'positive', 'category': 'defending'},
    'interceptions_per90': {'type': 'positive', 'category': 'defending'},
    'blocks_per90': {'type': 'positive', 'category': 'defending'},
    'gk_psxg': {'type': 'positive', 'category': 'goalkeeping'},
    
    # Métricas inversas (menos es mejor)
    'gk_goals_against_per90': {'type': 'inverse', 'category': 'goalkeeping'},
    'errors_per90': {'type': 'inverse', 'category': 'general'},
    'gk_pens_allowed_per90': {'type': 'inverse', 'category': 'goalkeeping'},
}
```

### Mapeo de Ligas (league_coefficients.py)

```python
# Basado en las ligas disponibles en nuestra BD
LEAGUE_BASE_RATINGS = {
    # Top 5 Ligas Europeas
    'Premier League': 60,
    'La Liga': 60,
    'Serie A': 58,
    'Bundesliga': 58,
    'Ligue 1': 56,
    
    # Segunda División Top
    'Premier Championship England': 50,
    'Liga Hipermotion': 48,  # Segunda de España
    'Serie B': 48,
    
    # Ligas Competitivas Europeas
    'Eredivisie': 52,
    'Primeira Liga': 52,
    'Belgian Pro League': 50,
    'Scottish Premier League': 48,
    
    # Ligas Escandinavas/Este Europa
    'Danish Superliga': 47,
    'Eliteserien': 46,  # Noruega
    'Croatian League': 47,
    'Czech First League': 46,
    'Bulgarian First League': 45,
    'Roumanian League I': 45,
    
    # Ligas Asiáticas
    'J1 League': 48,  # Japón
    'Korean League 1': 47,
    'Chinese Super League': 46,
    
    # Ligas Americanas
    'Major League Soccer Eastern Conf': 48,
    'Major League Soccer Western Conf': 48,
    'Liga MX': 49,  # México
    'Brasileirao': 52,  # Brasil top
    'Brasileirao B': 46,
    'Liga Argentina': 50,
    
    # Ligas Emergentes
    'Saudi Pro League': 47,
    
    # Default para ligas no listadas
    'default': 45,
}
```

### Modelo de Base de Datos

```python
class PlayerRating(models.Model):
    player_id = models.IntegerField(db_index=True)
    player_name = models.CharField(max_length=255)
    season = models.CharField(max_length=10, default='2024-25')
    
    # Atributos principales
    attacking = models.IntegerField()      # ATT
    playmaking = models.IntegerField()     # PLY
    defending = models.IntegerField()      # DEF
    ball_control = models.IntegerField()   # CTR
    physical = models.IntegerField()       # PHY
    goalkeeping = models.IntegerField(null=True)  # GKP
    
    # Overall rating
    overall_rating = models.IntegerField()  # OVR
    
    # Metadata
    position = models.CharField(max_length=32)
    league = models.CharField(max_length=64)
    minutes_played = models.IntegerField()
    confidence_factor = models.FloatField()
    
    # Timestamps
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('player_id', 'season')
        indexes = [
            models.Index(fields=['overall_rating']),
            models.Index(fields=['position', 'overall_rating']),
        ]
```

### API Endpoints

```
GET  /api/ratings/{player_id}/           # Get player rating
GET  /api/ratings/top/?position=FW       # Top rated by position
GET  /api/ratings/league/{league}/       # Ratings by league
POST /api/ratings/calculate/             # Trigger calculation
```

---

## 📋 Plan de Implementación

### Fase 1: Configuración & Modelos (Día 1)
- [ ] Crear app `rating_system`
- [ ] Definir `metrics_config.py` (positivas/inversas)
- [ ] Definir `league_coefficients.py` (base ratings)
- [ ] Definir `position_weights.py` (pesos por posición)
- [ ] Definir modelo `PlayerRating` con migraciones

### Fase 2: Core Calculation Engine (Día 1-2)
- [ ] Implementar `normalizers.py`:
  - [ ] Función para métricas positivas
  - [ ] Función para métricas inversas
  - [ ] Regresión a la media por minutos
  - [ ] Cálculo de percentiles por liga
- [ ] Implementar `calculator.py`:
  - [ ] Cálculo de 6 atributos (ATT, PLY, DEF, CTR, PHY, GKP)
  - [ ] Performance rating por posición
  - [ ] Overall rating (base liga + performance)

### Fase 3: Django Command & Testing (Día 2-3)
- [ ] Crear `calculate_ratings` management command
- [ ] Ejecutar cálculo para todos los jugadores
- [ ] Validar resultados con casos conocidos:
  - [ ] Portero con pocos minutos (regresión a media)
  - [ ] Delantero estrella (rating alto)
  - [ ] Jugador liga menor vs top liga
- [ ] Ajustar pesos y coeficientes si es necesario

### Fase 4: API & Frontend (Día 3-4)
- [ ] Crear serializers y viewsets
- [ ] Crear endpoints REST:
  - [ ] `GET /api/ratings/{player_id}/`
  - [ ] `GET /api/ratings/top/?position=FW&league=La Liga`
  - [ ] `POST /api/ratings/calculate/`
- [ ] Integrar ratings en dashboard de jugador
- [ ] Mostrar radar chart con 6 atributos (Chart.js)
- [ ] Player card con OVR y atributos
- [ ] Añadir filtros por rating en búsqueda

### Fase 5: Agent Integration (Día 4-5)
- [ ] Crear tool `get_player_rating`
- [ ] Crear tool `compare_player_ratings`
- [ ] Actualizar prompts del agente
- [ ] Testing end-to-end con agente

---

## 🎨 Visualización en Frontend

### 1. Player Card con Rating
```
┌─────────────────────────────┐
│  Lionel Messi       OVR: 91 │
│  FC Barcelona         (FW)  │
├─────────────────────────────┤
│  ATT: 95  │  PLY: 88        │
│  DEF: 35  │  CTR: 92        │
│  PHY: 65  │                 │
└─────────────────────────────┘
```

### 2. Radar Chart de Atributos
Mostrar los 6 atributos en un gráfico de radar (Chart.js)

### 3. Comparación de Ratings
Tabla lado a lado comparando ratings de múltiples jugadores

---

## 🔍 Consideraciones Importantes

### Ventajas del Sistema
✅ **Basado en datos reales** de performance, no subjetivo  
✅ **Actualizable automáticamente** con nuevos datos  
✅ **Regresión a la media** por minutos (evita sesgos de muestras pequeñas)  
✅ **Rating base por liga** (reconoce nivel profesional)  
✅ **Ajustado por contexto** de liga y posición  
✅ **Transparente y explicable** (no "caja negra")  

### Mejoras Clave Implementadas
🎯 **Ponderación por minutos:** Regresión a la media de liga  
🎯 **Rating base de liga:** 35-65% de peso según minutos  
🎯 **Normalización por percentiles:** Comparación justa dentro de la liga  

### Limitaciones
❌ No captura atributos físicos reales (velocidad, fuerza)  
❌ No considera calidad de rival o contexto de partido  
❌ Dependiente de la calidad de datos de FBRef  

### Mejoras Futuras
- Incorporar datos de tracking físico (si se obtienen)
- Ajustar por dificultad de rivales enfrentados
- Rating histórico con evolución temporal
- Machine Learning para predecir rating futuro
- Factor de edad (potencial vs experiencia)

---

## 📊 Ejemplo de Cálculo Completo

### Caso: Delantero en La Liga (Base Rating: 60)
**Stats raw:**
- Minutes: 2400 (26.7 partidos de 90 min)
- Goals: 22
- xG: 19.2
- Assists: 7
- xA: 7.5
- Progressive Carries: 112
- Passes Completed: 520 / 680 (76.5%)

**Paso 1: Calcular per 90**
- Goals per90: 22 / 26.7 = 0.82
- xG per90: 19.2 / 26.7 = 0.72
- Assists per90: 7 / 26.7 = 0.26
- xA per90: 7.5 / 26.7 = 0.28
- Progressive Carries per90: 112 / 26.7 = 4.2

**Paso 2: Ponderación por minutos (Regresión a media de liga)**
- Media de goles en La Liga para FW: 0.45 per90
- Player weight = min(2400/3000, 1.0) = 0.8
- Goals ponderados = (0.82 * 0.8) + (0.45 * 0.2) = 0.656 + 0.09 = **0.746**

*(Mismo proceso para cada stat...)*

**Paso 3: Normalizar por percentiles de La Liga**
Supongamos que después de normalizar:
- ATT: 78 (buen goleador)
- PLY: 62 (pases promedio)
- CTR: 71 (buena progresión)
- DEF: 25 (bajo para FW)
- PHY: 58 (promedio)

**Paso 4: Performance Rating (pesos FW: 50% ATT, 20% PLY, 25% CTR, 5% PHY)**
```
Performance = (78*0.5) + (62*0.2) + (25*0) + (71*0.25) + (58*0.05)
            = 39 + 12.4 + 0 + 17.75 + 2.9
            = 72.05
```

**Paso 5: Overall Rating (Base + Performance)**
```
Minutes factor = 2400/3000 = 0.8
League weight = 0.35 * (1 - 0.8*0.5) = 0.35 * 0.6 = 0.21
Perf weight = 1 - 0.21 = 0.79

OVR = (60 * 0.21) + (72.05 * 0.79)
    = 12.6 + 56.92
    = 69.52
    ≈ 70
```

### Resultado Final
**OVR: 70** - Delantero sólido en La Liga 🎯

### Comparación: Mismo jugador en liga menor (Base: 48)
```
OVR = (48 * 0.21) + (72.05 * 0.79)
    = 10.08 + 56.92
    = 67
```
**Diferencia:** -3 puntos por jugar en liga de menor nivel ✅ Lógico

---

## 🔄 Diagrama de Flujo del Cálculo

```
┌─────────────────────────────────────────────────────────────────┐
│  PASO 1: Extracción de Datos desde BD                          │
│  → Player stats: goals, assists, tackles, passes, etc.         │
│  → Player info: position, league, minutes                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 2: Calcular Per 90 & Identificar Tipo de Métrica        │
│  → stat_per90 = stat / (minutes / 90)                         │
│  → is_inverse? (goles contra, errores) → Flag                 │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 3: Regresión a la Media (por minutos)                   │
│  → weighted = (player_stat * player_weight)                    │
│               + (league_avg * league_weight)                   │
│  → Jugadores con pocos minutos → más peso a media liga        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 4: Normalización por Percentiles (0-100)                │
│  → Positivas: (value - min) / (max - min) * 100               │
│  → Inversas: (max - value) / (max - min) * 100                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 5: Calcular 6 Atributos                                 │
│  → ATT = (goals*30 + xG*25 + xA*25 + assists*20) / 100 * 100 │
│  → PLY = (passes%*30 + prog_passes*30 + ...)                  │
│  → DEF, CTR, PHY, GKP (similar)                               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 6: Performance Rating (pesos por posición)              │
│  → FW: 50% ATT + 20% PLY + 25% CTR + 5% PHY                  │
│  → CB: 5% ATT + 10% PLY + 50% DEF + 10% CTR + 25% PHY        │
│  → (cada posición tiene sus pesos)                            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  PASO 7: Overall Rating (Base Liga + Performance)             │
│  → league_base = LEAGUE_BASE_RATINGS[league]                  │
│  → league_weight = f(minutes) // Menos minutos → más peso     │
│  → OVR = (league_base * league_weight)                        │
│          + (performance * perf_weight)                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  RESULTADO FINAL                                               │
│  ✅ OVR: 75                                                    │
│  ✅ ATT: 82, PLY: 68, DEF: 55, CTR: 72, PHY: 60, GKP: N/A    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Resumen de Mejoras Clave

### 1. ⚖️ **Ponderación por Minutos (Regresión a la Media)**
**Problema resuelto:** Jugadores con pocos partidos aparecían con stats infladas.

**Solución:** 
- Jugador con 90 min → 97% peso a media liga, 3% peso a su stat
- Jugador con 3000 min → 100% peso a su stat

### 2. 🏆 **Rating Base por Nivel de Liga**
**Problema resuelto:** No se reconocía que jugar en top ligas ya implica cierto nivel.

**Solución:**
- Premier/La Liga: Base 60
- Ligas menores: Base 45-48
- Peso: 17-35% según minutos jugados

### 3. 🔄 **Métricas Inversas (Menos es Mejor)**
**Problema resuelto:** Porteros con 0 goles en contra en 90 min parecían perfectos.

**Solución:**
- Normalización invertida: max → 0 puntos, min → 100 puntos
- Regresión a media también aplicada
- Caso especial para 0 minutos → media de liga

---

## ✅ Próximos Pasos

1. ✅ **Plan aprobado** con mejoras de ponderación y métricas inversas
2. **Comenzar implementación** de Fase 1 (Configuración & Modelos)
3. **Validar con casos reales** de jugadores conocidos:
   - Portero novato con pocos minutos
   - Delantero estrella en La Liga
   - Mismo jugador en diferentes ligas
4. **Iterar** basado en resultados y feedback

---

**Fecha:** 2025-10-10  
**Versión:** 2.0 (actualizado con métricas inversas y ponderaciones)  
**Autor:** AI Assistant + Usuario

