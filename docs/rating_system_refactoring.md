# 🔧 Rating System Refactoring

## Overview

Complete refactoring of the player rating calculation system to ensure consistency across all positions and proper handling of statistics normalization.

---

## 🎯 Problems Solved

### 1. **Goalkeeper Rating Inconsistency**

**Before:**
- All goalkeepers had identical ratings (GKP=70, OVR=79-82)
- Used absolute `gk_goals_against` instead of per-90 normalization
- No minute-based weighting applied

**After:**
- GK stats calculated per-90 minutes
- Minute-based weighting applied consistently
- Three GK metrics with proper weights:
  - Goals conceded per 90 (40%, inverse)
  - Post-shot xG per 90 (35%)
  - PSxG per shot on target (25%)

### 2. **Inconsistent Stat Normalization**

**Before:**
- Only offensive stats (goals, assists) had minute weighting
- Defensive/physical stats used **absolute values** (totals)
- Players with more minutes had unfair advantage
- Sergi Cardona rated 92 OVR just from playing many minutes

**After:**
- **ALL stats converted to per-90** (tackles, interceptions, clearances, etc.)
- Minute weighting applied to ALL per-90 stats
- Fair comparison: 30 tackles in 1000 min = 90 tackles in 3000 min
- Players rated on **efficiency**, not just volume

---

## 📊 Technical Changes

### Stat Processing Flow

```
1. Fetch League Stats (per-90 normalized)
   ↓
2. Calculate Player Stats per-90 (where applicable)
   ↓
3. Apply Minute-Based Weighting
   ↓
4. Normalize Using Percentiles by League
   ↓
5. Calculate Attribute Ratings
   ↓
6. Calculate Overall Rating
```

### Key Functions Modified

#### `fetch_league_stats()`
```python
# Now calculates GK stats per-90:
gk_goals_per90 = gk_goals_against / minutes_90s
gk_psxg_per90 = gk_psxg / minutes_90s
```

#### `calculate_player_rating()`

**Minute Weighting Section:**
```python
# Applied to all per-90 stats
weighted_stats['goals_per90'] = weighted_stat_by_minutes(
    raw_value, league_avg, minutes
)

# GK stats also weighted
weighted_stats['gk_goals_against_per90'] = weighted_stat_by_minutes(
    player_gk_goals_per90, league_avg, minutes
)
```

**GKP Calculation:**
```python
gkp_raw = (
    normalized['gk_goals_against_per90'] * 0.40 +  # Lower is better
    normalized['gk_psxg_per90'] * 0.35 +
    normalized['gk_psnpxg_per_shot'] * 0.25
)
gkp = max(60, gkp_raw)  # Floor at 60 instead of 70
```

---

## 🎮 Expected Results

### Goalkeeper Ratings

| Category | OVR Range | Example Players |
|----------|-----------|----------------|
| World Class | 85-92 | Oblak, Courtois, Ter Stegen |
| Elite | 80-84 | Alex Remiro, Unai Simón |
| Good | 75-79 | Most La Liga starters |
| Average | 70-74 | Backup goalkeepers |
| Limited Data | 60-69 | <300 minutes played |

### Outfield Players

All positions now have consistent:
- Minute-based weighting for per-90 stats
- Proper differentiation between regulars and substitutes
- League-adjusted percentiles

---

## 📈 Data Flow

### Input (from Database)
```python
player_stats = {
    # Per-90 stats (already normalized)
    'goals_per90': float,
    'assists_per90': float,
    
    # Absolute stats
    'progressive_carries': int,
    'tackles': int,
    
    # GK absolute stats
    'gk_goals_against': int,
    'gk_psxg': float,
    'minutes_90s': float,  # NEW: for GK calculations
    'gk_psnpxg_per_shot': float,  # NEW: quality metric
}
```

### Processing
1. **League Stats Fetched**: All players in league with >90 minutes
2. **GK Per-90 Calculated**: For each GK in league
3. **Percentile Ranking**: Player vs league distribution
4. **Minute Weighting**: Regression to mean for small samples
5. **Attribute Calculation**: Weighted combination of normalized stats

### Output
```python
{
    'overall_rating': int,  # 60-95 range
    'att': int,             # Attacking
    'ply': int,             # Playmaking
    'def_rating': int,      # Defending
    'ctr': int,             # Ball Control
    'phy': int,             # Physical
    'gkp': int | None,      # Goalkeeping (GK only)
}
```

---

## 🔬 Testing & Validation

### Test Cases

1. **Elite GK with 3000+ minutes**
   - Should have high GKP (80-90)
   - OVR should reflect league + performance

2. **Backup GK with 300 minutes**
   - GKP should regress toward league mean
   - Lower than starter despite potentially good stats

3. **Outfield player comparison**
   - Regular starter (2500 min) vs substitute (800 min)
   - Same per-90 stats should yield different ratings

### Validation Queries

```sql
-- Check GK rating distribution
SELECT 
    position,
    MIN(overall_rating) as min_ovr,
    AVG(overall_rating) as avg_ovr,
    MAX(overall_rating) as max_ovr,
    STDDEV(overall_rating) as std_ovr
FROM player_ratings
WHERE position = 'GK'
GROUP BY position;

-- Top 10 GKs by rating
SELECT 
    p.full_name,
    pr.overall_rating,
    pr.gkp,
    p.minutes,
    p.league
FROM player_ratings pr
JOIN players p ON pr.player_id = p.id
WHERE p.position = 'GK'
ORDER BY pr.overall_rating DESC
LIMIT 10;
```

---

## 🚀 Deployment

### Steps to Apply

1. **Code Updates**: Already applied to `apps/rating_system/calculator.py`
2. **Script Updates**: Updated `scripts/calculate_all_ratings.py`
3. **Recalculation**: Run `make ingest-players` or manual recalc
4. **Verification**: Check goalkeeper ratings via API

### Command

```bash
# Full recalculation
docker compose run --rm -t ingestion python scripts/calculate_all_ratings.py --replace --verbose

# Or via Makefile
make ingest-players
```

---

## 📝 Future Improvements

1. **More GK Metrics**
   - Add saves per 90
   - Add clean sheets percentage
   - Add distribution accuracy

2. **Position-Specific Floors**
   - Different minimum ratings per position
   - Account for role specificity

3. **Age Adjustment**
   - Potential vs current ability
   - Peak age considerations

4. **Form Weighting**
   - Recent performance vs historical
   - Last 5-10 games emphasis

---

## 🐛 Known Issues & Limitations

1. **Limited GK Data**
   - Only 3 GK-specific metrics available
   - FIFA uses 10+ metrics for GK ratings

2. **Absolute Stats**
   - Progressive carries, tackles not per-90
   - May favor players with more minutes

3. **League Comparison**
   - Percentiles only within league
   - No cross-league normalization yet

---

## 📚 References

- [FIFA Rating System](https://www.ea.com/games/fifa/fifa-22/ratings)
- [FBref Goalkeeper Stats](https://fbref.com/en/comps/Big5/keepers/players/Big-5-European-Leagues-Stats)
- [Statistical Normalization Methods](https://en.wikipedia.org/wiki/Percentile_rank)

