#!/usr/bin/env python3
"""
historical_fbref_scraper.py

Specialized scraper for obtaining historical player data from FBref (2020-2024).
Includes player aggregation functionality and player status management.

Usage:
    python historical_fbref_scraper.py

Requirements:
    pip install cloudscraper beautifulsoup4 pandas
"""
import json
import random
import time
import requests
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from functools import reduce
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# -----------------------------
# Global Configuration
# -----------------------------

# Header rotation to simulate different browsers/devices
HEADERS_LIST = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"  
            "image/avif,image/webp,*/*;q=0.8"
        ),
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/16.4 Safari/605.1.15"
        ),
        "Accept-Language": "en-US,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:116.0) "
            "Gecko/20100101 Firefox/116.0"
        ),
        "Accept-Language": "en-GB,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "CriOS/115.0.5790.110 Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "en-US,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/115.0.5790.170 Mobile Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    },
]

# Initialize cloudscraper to handle Cloudflare
scraper = cloudscraper.create_scraper()

# -----------------------------
# Scraping Functions
# -----------------------------

def fetch_with_random_header(url: str, **kwargs) -> requests.Response:
    """Makes a GET request with a random header."""
    headers = random.choice(HEADERS_LIST)
    return scraper.get(url, headers=headers, **kwargs)

def load_historical_links(json_file: str) -> List[Dict]:
    """Loads historical URLs from JSON file."""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_links = []
    for league_group in data.values():
        all_links.extend(league_group)
    
    return all_links

def get_team_links(league_name: str, league_url: str, table_id: str) -> List[Tuple[str, str, str, str]]:
    """
    Returns list of (team_name, team_url, league_name, season) from league page.
    """
    resp = fetch_with_random_header(league_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    wrapper = soup.find("div", {"id": f"div_{table_id}"})
    table = wrapper and wrapper.find("table", {"id": table_id}) 
    if not table or not table.tbody:
        raise RuntimeError(f"Table {table_id} not found. Check ID or wrapper.")

    links = []
    for row in table.tbody.find_all("tr"):
        cell = row.find("td", {"class": "left", "data-stat": "team"})
        if not cell:
            continue
        a = cell.find("a", href=True)
        if not a:
            continue
        team_name = a.text.strip()
        team_href = urljoin("https://fbref.com", a["href"])
        links.append((team_name, team_href, league_name, table_id.split("_")[0][-4:]))  # Extract year
    
    return links

def scrape_team_stats(team_name: str, team_url: str, league_name: str, season: str) -> pd.DataFrame:
    """Scrapes player statistics for a team in a specific season."""
    resp = fetch_with_random_header(team_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    logo_tag = soup.find("img", {"class": "teamlogo"})
    team_logo = urljoin(team_url, logo_tag["src"]) if logo_tag and logo_tag.get("src") else None

    # Base IDs to scan dynamically
    base_ids = [
        "stats_standard_", "stats_keeper_adv_", "stats_shooting_",
        "stats_passing_", "stats_passing_types_", "stats_gca_",
        "stats_defense_", "stats_possession_", "stats_playing_time_",
    ]

    dfs = []
    for idx, base in enumerate(base_ids):
        found = False
        table = None
        # Iterate suffixes from 0 to 99
        for n in range(100):
            table_id = f"{base}{n}"
            tbl = soup.find("table", {"id": table_id})
            if tbl and tbl.thead and tbl.tbody:
                table = tbl
                found = True
                break
        if not found:
            print(f"Table with prefix '{base}' not found for {team_name}")
            continue

        # Extract columns
        header_rows = table.thead.find_all("tr")
        cols = [th['data-stat'] for th in header_rows[1].find_all("th")]

        # Extract records
        records = []
        for tr in table.tbody.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) != len(cols):
                continue
            row = {}
            for col, cell in zip(cols, cells):
                a = cell.find("a")
                row[col] = a.text.strip() if a else cell.get_text(strip=True)
            records.append(row)

        df = pd.DataFrame.from_records(records)
        # Basic cleaning
        if "nationality" in df.columns:
            df["nationality"] = df["nationality"].apply(
                lambda x: x.split(" ")[-1] if len(x.split(" ")) > 1 else x
            )
        if "minutes_90s" in df.columns and idx != 0:
            df.drop(columns=["minutes_90s"], inplace=True, errors='ignore')
        dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    df_all = reduce(
        lambda l, r: pd.merge(
            l, r,
            on=["player", "nationality", "position", "age", "matches"],
            how="left"
        ),
        dfs
    )
    
    # Add metadata
    df_all["Team"] = team_name
    df_all["League"] = league_name
    df_all["Season"] = season
    df_all["Team_Logo"] = team_logo
    
    # Remove automatic suffixes
    df_all.columns = [c.rstrip('_x').rstrip('_y') for c in df_all.columns]

    return df_all

# -----------------------------
# Aggregation Functions
# -----------------------------

def aggregate_player_data(player_data: pd.DataFrame) -> Dict:
    """
    Aggregates player data across multiple seasons using weighted average.
    """
    if player_data.empty:
        return {}
    
    # Calculate weighted average by minutes played
    numeric_cols = player_data.select_dtypes(include=[float, int]).columns
    numeric_cols = [col for col in numeric_cols if col not in ['age', 'matches']]
    
    # Use minutes_90s as weight (if exists) or matches as fallback
    weight_col = 'minutes_90s' if 'minutes_90s' in player_data.columns else 'matches'
    weights = player_data[weight_col].fillna(0)
    
    # If no valid weights, use simple average
    if weights.sum() == 0:
        weights = pd.Series([1] * len(player_data), index=player_data.index)
    
    # Calculate weighted averages
    aggregated = {}
    for col in numeric_cols:
        if col in player_data.columns:
            values = pd.to_numeric(player_data[col], errors='coerce').fillna(0)
            if weights.sum() > 0:
                aggregated[col] = (values * weights).sum() / weights.sum()
            else:
                aggregated[col] = values.mean()
    
    # Categorical fields (take most recent or most common)
    categorical_cols = ['player', 'nationality', 'position', 'Team', 'League']
    for col in categorical_cols:
        if col in player_data.columns:
            # Take most recent value (last season)
            aggregated[col] = player_data[col].iloc[-1] if not player_data.empty else None
    
    # Season metadata
    aggregated['seasons_played'] = sorted(player_data['Season'].unique().tolist())
    aggregated['last_season_played'] = max(player_data['Season']) if not player_data.empty else None
    aggregated['total_seasons'] = len(aggregated['seasons_played'])
    
    # Determine player status
    current_year = datetime.now().year
    last_season_year = int(aggregated['last_season_played'].split('-')[0]) if aggregated['last_season_played'] else 0
    
    if last_season_year >= current_year - 1:
        aggregated['player_status'] = 'active'
    elif last_season_year >= current_year - 3:
        aggregated['player_status'] = 'inactive'
    else:
        aggregated['player_status'] = 'retired'
    
    # Weighted average age
    if 'age' in player_data.columns:
        ages = pd.to_numeric(player_data['age'], errors='coerce').fillna(0)
        if weights.sum() > 0:
            aggregated['avg_age'] = (ages * weights).sum() / weights.sum()
        else:
            aggregated['avg_age'] = ages.mean()
    
    return aggregated

def process_historical_data(all_team_data: List[pd.DataFrame]) -> pd.DataFrame:
    """
    Processes all historical data and aggregates by player.
    """
    if not all_team_data:
        return pd.DataFrame()
    
    # Concatenate all data
    df_all = pd.concat(all_team_data, ignore_index=True, sort=False)
    
    # Group by player and aggregate
    player_groups = df_all.groupby('player')
    aggregated_players = []
    
    print(f"Processing {len(player_groups)} unique players...")
    
    for player_name, player_data in player_groups:
        aggregated = aggregate_player_data(player_data)
        if aggregated:
            aggregated_players.append(aggregated)
    
    return pd.DataFrame(aggregated_players)

# -----------------------------
# Main
# -----------------------------

def main():
    """Main function to execute historical scraping."""
    print("=== HISTORICAL PLAYER DATA SCRAPING ===")
    print("Loading historical URLs...")
    
    # Load URLs from JSON
    try:
        historical_links = load_historical_links('historic_leagues_links.json')
        print(f"Loaded {len(historical_links)} league/season configurations")
    except FileNotFoundError:
        print("Error: historic_leagues_links.json file not found")
        return
    except Exception as e:
        print(f"Error loading URLs: {e}")
        return
    
    all_team_data = []
    
    # Process each league/season
    for i, config in enumerate(historical_links):
        league_name = config['league_name']
        season = config['season']
        url = config['url']
        table_id = config['table_id']
        
        print(f"\n=== [{i+1}/{len(historical_links)}] {league_name} - {season} ===")
        
        try:
            # Get team links
            team_links = get_team_links(league_name, url, table_id)
            print(f"Found {len(team_links)} teams")
            
            # Scrape each team
            for j, (team_name, team_url, lg, year) in enumerate(team_links):
                print(f"  [{j+1}/{len(team_links)}] Scraping: {team_name}...")
                try:
                    df_team = scrape_team_stats(team_name, team_url, lg, season)
                    if not df_team.empty:
                        all_team_data.append(df_team)
                        print(f"    ✓ {len(df_team)} players obtained")
                    else:
                        print(f"    ✗ No data")
                except Exception as e:
                    print(f"    ✗ Error: {e}")
                
                # Pause between teams (4-10 seconds)
                time.sleep(random.uniform(4, 10))
            
        except Exception as e:
            print(f"Error processing {league_name} - {season}: {e}")
            continue
        
        # Pause between leagues (4-10 seconds)
        time.sleep(random.uniform(4, 10))
    
    # Process and aggregate data
    print(f"\n=== PROCESSING DATA ===")
    print(f"Total team datasets: {len(all_team_data)}")
    
    if all_team_data:
        # Save raw data by season
        df_raw = pd.concat(all_team_data, ignore_index=True, sort=False)
        df_raw.to_csv('data/historical_players_raw.csv', index=False)
        print(f"Raw data saved: {len(df_raw)} records")
        
        # Aggregate by player
        df_aggregated = process_historical_data(all_team_data)
        df_aggregated.to_csv('data/historical_players_aggregated.csv', index=False)
        print(f"Aggregated data saved: {len(df_aggregated)} unique players")
        
        # Statistics
        print(f"\n=== STATISTICS ===")
        print(f"Active players: {len(df_aggregated[df_aggregated['player_status'] == 'active'])}")
        print(f"Inactive players: {len(df_aggregated[df_aggregated['player_status'] == 'inactive'])}")
        print(f"Retired players: {len(df_aggregated[df_aggregated['player_status'] == 'retired'])}")
        
        # By league
        print(f"\nBy league:")
        for league in df_aggregated['League'].value_counts().head():
            print(f"  {league}: {df_aggregated[df_aggregated['League'] == league].shape[0]} players")
            
    else:
        print("No data obtained.")

if __name__ == "__main__":
    main()
