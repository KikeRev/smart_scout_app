# ⚖️ Confidence Factors by Minutes Played

## Overview

The rating system uses tiered confidence factors to penalize small sample sizes and prevent random variance from inflating ratings.

---

## 📊 Confidence Tiers

| Minutes Range | Confidence | Player Weight | League Weight | Example |
|--------------|------------|---------------|---------------|---------|
| **≥ 1500** | 100% | 1.0 | 0.0 | Full season starter |
| **1200-1499** | 90% | 0.9 | 0.1 | Regular starter |
| **900-1199** | 80% | 0.8 | 0.2 | Frequent substitute |
| **600-899** | 70% | 0.7 | 0.3 | Rotation player |
| **300-599** | 60% | 0.6 | 0.4 | Occasional player |
| **< 300** | 50% | 0.5 | 0.5 | Youth/rarely used |

---

## 🎯 Real Examples

### Example 1: Tackles Per 90

**Scenario:**
- League average: 2.0 tackles/90
- Player A: 3.0 tackles/90, 2700 minutes (full season)
- Player B: 3.0 tackles/90, 270 minutes (3 games)

**Calculation:**

**Player A (2700 minutes):**
```
Confidence = 1.0 (≥1500 minutes)
Weighted = (3.0 × 1.0) + (2.0 × 0.0) = 3.0
```
✅ Full confidence - likely real skill

**Player B (270 minutes):**
```
Confidence = 0.5 (<300 minutes)
Weighted = (3.0 × 0.5) + (2.0 × 0.5) = 2.5
```
⚠️ Penalized - could be luck

---

### Example 2: Goals Per 90

**Scenario:**
- League average: 0.5 goals/90
- Player A: 1.2 goals/90, 2500 minutes
- Player B: 1.2 goals/90, 450 minutes

**Calculation:**

**Player A (2500 minutes):**
```
Confidence = 1.0 (≥1500 minutes)
Weighted = (1.2 × 1.0) + (0.5 × 0.0) = 1.2
```
✅ Elite striker - proven

**Player B (450 minutes):**
```
Confidence = 0.6 (300-599 minutes)
Weighted = (1.2 × 0.6) + (0.5 × 0.4) = 0.72 + 0.20 = 0.92
```
⚠️ Promising but unproven

---

## 📈 Impact on Ratings

### High-Minute Player (3000 min)
```
Raw tackles/90: 3.5
Weighted: 3.5 (no penalty)
Percentile: 85th
DEF contribution: High
```

### Low-Minute Player (400 min)
```
Raw tackles/90: 3.5 (same!)
Weighted: 2.7 (penalized 40%)
Percentile: 65th
DEF contribution: Medium
```

**Result:** Players with few minutes need **significantly better** raw stats to achieve the same rating.

---

## 🎮 Typical Season Minutes

| Role | Minutes | Confidence | Impact |
|------|---------|------------|--------|
| **Starter** | 2500-3400 | 100% | No penalty |
| **Regular** | 1500-2500 | 100% | No penalty |
| **Rotation** | 900-1500 | 80-90% | Mild penalty |
| **Substitute** | 400-900 | 60-80% | Moderate penalty |
| **Youth** | <400 | 50-60% | Heavy penalty |

---

## 🔬 Mathematical Formula

```python
def get_confidence_factor(minutes: int) -> float:
    """
    Tiered confidence based on sample size.
    """
    if minutes >= 1500: return 1.0
    elif minutes >= 1200: return 0.9
    elif minutes >= 900: return 0.8
    elif minutes >= 600: return 0.7
    elif minutes >= 300: return 0.6
    else: return 0.5

weighted_stat = (player_stat × confidence) + (league_avg × (1 - confidence))
```

---

## 🎯 Design Philosophy

### Why Tiered Instead of Continuous?

**Tiered Approach (Current):**
- ✅ Clear breakpoints easy to understand
- ✅ Predictable behavior
- ✅ Prevents edge cases (e.g., 1499 vs 1500 min)

**Continuous Approach (Alternative):**
- ❌ Harder to reason about
- ❌ Arbitrary cutoffs feel random
- ✅ Smoother transitions

### Why These Specific Tiers?

| Minutes | Represents | Reasoning |
|---------|-----------|-----------|
| 1500 | ~17 full games | Full confidence in statistics |
| 1200 | ~13 games | Most of season, small penalty |
| 900 | ~10 games | Meaningful sample |
| 600 | ~7 games | Limited but useful |
| 300 | ~3 games | Very small sample |
| <300 | <3 games | Maximum skepticism |

---

## 📊 Example: Sergi Cardona Case

**Before Confidence Factors:**
```
Minutes: 3200
Tackles: 128 (raw)
Tackles/90: 3.6
Rating: 99 DEF (overrated!)
```

**After Per-90 Normalization:**
```
Minutes: 3200
Tackles/90: 3.6
Confidence: 1.0 (full)
Weighted: 3.6
Rating: 85 DEF (still good)
```

**Comparison with Substitute:**
```
Minutes: 400
Tackles/90: 3.6 (same per-90!)
Confidence: 0.6
Weighted: (3.6 × 0.6) + (2.0 × 0.4) = 2.96
Rating: 78 DEF (appropriately lower)
```

---

## 🚀 Future Improvements

1. **Position-Specific Confidence**
   - GKs might need more games for reliable stats
   - Strikers might need fewer (goals are rarer events)

2. **Stat-Specific Confidence**
   - High-variance stats (goals) need more sample
   - Low-variance stats (pass %) stabilize faster

3. **Recency Weighting**
   - Last 10 games more important than first 10
   - Account for form and improvement

4. **Quality of Opposition**
   - 3 tackles/90 vs top teams ≠ 3 tackles/90 vs relegation teams

---

## 📝 Summary

The confidence factor system ensures:

- ✅ **Fairness**: Players judged on efficiency, not volume
- ✅ **Reliability**: Small samples appropriately skeptical
- ✅ **Transparency**: Clear, understandable rules
- ✅ **Balance**: Neither too harsh nor too lenient

