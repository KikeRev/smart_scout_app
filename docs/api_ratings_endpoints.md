# 🎯 Ratings API Endpoints

## Overview

The Ratings API provides FIFA-style player and team ratings with comprehensive filtering and visualization support.

Base URL: `http://localhost:8001/api/ratings`

---

## 📊 Endpoints

### 1. Get Player Rating

**GET** `/api/ratings/player/{player_id}`

Get complete FIFA-style rating for a specific player.

**Parameters:**
- `player_id` (path, required): Player ID in database
- `season` (query, optional): Season (default: "2024-25")

**Response:**
```json
{
  "player_id": 123,
  "player_name": "Bruno Fernandes",
  "position": "MF",
  "club": "Manchester Utd",
  "league": "Premier League",
  "season": "2024-25",
  "overall_rating": 91,
  "league_base_rating": 92.0,
  "performance_rating": 89.5,
  "att": 93,
  "ply": 90,
  "def_rating": 88,
  "ctr": 87,
  "phy": 82,
  "gkp": null,
  "minutes_played": 2850
}
```

**Example:**
```bash
curl http://localhost:8001/api/ratings/player/123?season=2024-25
```

---

### 2. Get Player Radar Chart Data

**GET** `/api/ratings/player/{player_id}/radar`

Get radar chart visualization data for a player.

**Parameters:**
- `player_id` (path, required): Player ID
- `season` (query, optional): Season (default: "2024-25")

**Response:**
```json
{
  "player_id": 123,
  "player_name": "Bruno Fernandes",
  "position": "MF",
  "overall_rating": 91,
  "attributes": {
    "ATT": 93,
    "PLY": 90,
    "DEF": 88,
    "CTR": 87,
    "PHY": 82
  },
  "percentiles": {
    "ATT": 93.0,
    "PLY": 90.0,
    "DEF": 88.0,
    "CTR": 87.0,
    "PHY": 82.0
  }
}
```

---

### 3. Get Top Players

**GET** `/api/ratings/top`

Get top N players by overall rating with powerful filtering options.

**Query Parameters:**
- `limit` (optional): Number of players (1-100, default: 50)
- `league` (optional): Filter by league (e.g., "Premier League", "La Liga")
- `nationality` (optional): Filter by nationality (e.g., "England", "Brazil")
- `position` (optional): Filter by position (GK, DF, MF, FW)
- `season` (optional): Season (default: "2024-25")
- `min_minutes` (optional): Minimum minutes played (default: 500)

**Response:**
```json
[
  {
    "rank": 1,
    "player_id": 456,
    "player_name": "Antonee Robinson",
    "position": "DF",
    "club": "Fulham",
    "league": "Premier League",
    "nationality": "United States",
    "overall_rating": 92,
    "att": 75,
    "ply": 81,
    "def_rating": 98,
    "ctr": 85,
    "phy": 88,
    "gkp": null
  },
  ...
]
```

**Examples:**

```bash
# Top 50 players globally
curl http://localhost:8001/api/ratings/top

# Top 20 Premier League players
curl "http://localhost:8001/api/ratings/top?limit=20&league=Premier%20League"

# Top 10 Brazilian players
curl "http://localhost:8001/api/ratings/top?limit=10&nationality=Brazil"

# Top 15 forwards in La Liga with at least 1000 minutes
curl "http://localhost:8001/api/ratings/top?limit=15&league=La%20Liga&position=FW&min_minutes=1000"
```

---

### 4. Get Team Rating

**GET** `/api/ratings/team/{team_name}`

Get team rating calculated on-the-fly from player ratings.

**Team Rating Formula:**
- **Starters** (≥1300 min): 70% weight
- **Substitutes** (300-1299 min): 25% weight
- **Youth** (<300 min): 5% weight

**Parameters:**
- `team_name` (path, required): Team/club name (e.g., "Liverpool", "Real Madrid")
- `season` (query, optional): Season (default: "2024-25")

**Response:**
```json
{
  "team_name": "Liverpool",
  "season": "2024-25",
  "overall_rating": 87.3,
  "num_players": 28,
  "starters": [
    {
      "name": "Mohamed Salah",
      "position": "FW",
      "rating": 91,
      "minutes": 2850,
      "att": 94,
      "ply": 88,
      "def": 75,
      "ctr": 89,
      "phy": 85
    },
    ...
  ],
  "substitutes": [...],
  "youth": [...],
  "breakdown": {
    "starters_avg": 88.5,
    "starters_count": 14,
    "substitutes_avg": 82.3,
    "substitutes_count": 10,
    "youth_avg": 75.1,
    "youth_count": 4
  }
}
```

**Example:**
```bash
curl "http://localhost:8001/api/ratings/team/Liverpool?season=2024-25"
```

---

### 5. Get Available Leagues

**GET** `/api/ratings/leagues`

Get list of available leagues for filtering.

**Parameters:**
- `season` (query, optional): Season (default: "2024-25")

**Response:**
```json
[
  "Bundesliga",
  "La Liga",
  "Ligue 1",
  "Premier League",
  "Serie A",
  ...
]
```

---

### 6. Get Available Nationalities

**GET** `/api/ratings/nationalities`

Get list of available nationalities for filtering.

**Parameters:**
- `season` (query, optional): Season (default: "2024-25")

**Response:**
```json
[
  "Argentina",
  "Brazil",
  "England",
  "France",
  "Germany",
  ...
]
```

---

## 🧪 Testing the Endpoints

### Using cURL

```bash
# Test player rating
curl http://localhost:8001/api/ratings/player/1

# Test top players
curl http://localhost:8001/api/ratings/top?limit=10

# Test team rating
curl http://localhost:8001/api/ratings/team/Liverpool

# Test leagues list
curl http://localhost:8001/api/ratings/leagues
```

### Using Browser

Navigate to the interactive API documentation:

**Swagger UI:** `http://localhost:8001/docs`

**ReDoc:** `http://localhost:8001/redoc`

---

## 📝 Notes

1. **Season Format**: Use "YYYY-YY" format (e.g., "2024-25")
2. **Team Names**: Must match exactly as stored in database (case-sensitive)
3. **Performance**: Team ratings are calculated on-the-fly, may be slower for large squads
4. **Caching**: Consider implementing caching for frequently accessed team ratings

---

## 🔧 Future Enhancements

- [ ] Add caching layer for team ratings
- [ ] Add historical comparison endpoints
- [ ] Add player comparison endpoint
- [ ] Add position-specific rankings
- [ ] Add age-based rankings (best U21, U23, etc.)
- [ ] Add league comparison statistics

