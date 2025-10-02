#!/usr/bin/env python3
"""
test_all_leagues_wrapper.py

Test script to validate wrapper structure for all historical leagues.
This helps identify if different leagues use different wrapper IDs.

Usage:
    python test_all_leagues_wrapper.py

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
]

# Initialize cloudscraper to handle Cloudflare
scraper = cloudscraper.create_scraper()

# -----------------------------
# Testing Functions
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

def test_wrapper_structure(league_name: str, league_url: str, table_id: str) -> Dict:
    """
    Tests different wrapper structures for a league/season.
    Returns information about which wrapper works.
    """
    print(f"  Testing: {league_name} - {table_id}")
    
    try:
        resp = fetch_with_random_header(league_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Test different wrapper patterns
        wrapper_patterns = [
            f"all_{table_id}",
            f"div_{table_id}",
            f"wrapper_{table_id}",
            f"content_{table_id}",
            f"table_{table_id}",
            f"stats_{table_id}",
        ]
        
        results = {
            'league_name': league_name,
            'table_id': table_id,
            'url': league_url,
            'status': 'failed',
            'working_wrapper': None,
            'teams_found': 0,
            'error': None
        }
        
        for pattern in wrapper_patterns:
            wrapper = soup.find("div", {"id": pattern})
            if wrapper:
                table = wrapper.find("table", {"id": table_id})
                if table and table.tbody:
                    rows = table.tbody.find_all("tr")
                    team_count = len(rows)
                    
                    if team_count > 0:
                        results['status'] = 'success'
                        results['working_wrapper'] = pattern
                        results['teams_found'] = team_count
                        print(f"    ✓ Found {team_count} teams with wrapper: {pattern}")
                        break
                    else:
                        print(f"    - Wrapper {pattern} found but no teams")
                else:
                    print(f"    - Wrapper {pattern} found but no table/tbody")
            else:
                print(f"    - Wrapper {pattern} not found")
        
        if results['status'] == 'failed':
            # Try to find any wrapper that contains the table
            all_wrappers = soup.find_all("div", id=lambda x: x and table_id in x)
            if all_wrappers:
                results['error'] = f"No working wrapper found. Available wrappers: {[w.get('id') for w in all_wrappers]}"
            else:
                results['error'] = "No wrappers found containing table_id"
            print(f"    ✗ Failed: {results['error']}")
        
        return results
        
    except Exception as e:
        error_msg = str(e)
        print(f"    ✗ Error: {error_msg}")
        return {
            'league_name': league_name,
            'table_id': table_id,
            'url': league_url,
            'status': 'error',
            'working_wrapper': None,
            'teams_found': 0,
            'error': error_msg
        }

def test_league_sample_teams(league_name: str, league_url: str, table_id: str, wrapper_pattern: str) -> Dict:
    """
    Tests extracting team links using the working wrapper pattern.
    """
    print(f"  Testing team extraction with wrapper: {wrapper_pattern}")
    
    try:
        resp = fetch_with_random_header(league_url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        wrapper = soup.find("div", {"id": wrapper_pattern})
        if not wrapper:
            return {'status': 'failed', 'error': f'Wrapper {wrapper_pattern} not found'}
        
        table = wrapper.find("table", {"id": table_id})
        if not table or not table.tbody:
            return {'status': 'failed', 'error': 'Table or tbody not found'}
        
        # Extract first 3 team links
        team_links = []
        for row in table.tbody.find_all("tr")[:3]:  # Only first 3 teams
            cell = row.find("td", {"class": "left", "data-stat": "team"})
            if not cell:
                continue
            a = cell.find("a", href=True)
            if not a:
                continue
            team_name = a.text.strip()
            team_href = urljoin("https://fbref.com", a["href"])
            team_links.append((team_name, team_href))
        
        return {
            'status': 'success',
            'team_links': team_links,
            'teams_found': len(team_links)
        }
        
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

# -----------------------------
# Main
# -----------------------------

def main():
    """Main function to test all leagues."""
    print("=== TESTING ALL LEAGUES WRAPPER STRUCTURES ===")
    print("Loading historical URLs...")
    
    # Load URLs from test JSON (Top 5 leagues)
    try:
        historical_links = load_historical_links('test_all_major_leagues_links.json')
        print(f"Loaded {len(historical_links)} league/season configurations")
    except FileNotFoundError:
        print("Error: test_all_major_leagues_links.json file not found")
        return
    except Exception as e:
        print(f"Error loading URLs: {e}")
        return
    
    results = []
    successful_leagues = []
    
    # Test each league/season
    for i, config in enumerate(historical_links):
        league_name = config['league_name']
        season = config['season']
        url = config['url']
        table_id = config['table_id']
        
        print(f"\n=== [{i+1}/{len(historical_links)}] {league_name} - {season} ===")
        
        # Test wrapper structure
        wrapper_result = test_wrapper_structure(league_name, url, table_id)
        results.append(wrapper_result)
        
        # If successful, test team extraction
        if wrapper_result['status'] == 'success':
            successful_leagues.append(wrapper_result)
            team_result = test_league_sample_teams(
                league_name, url, table_id, wrapper_result['working_wrapper']
            )
            wrapper_result['team_extraction'] = team_result
            
            if team_result['status'] == 'success':
                print(f"    ✓ Team extraction successful: {team_result['teams_found']} teams")
            else:
                print(f"    ✗ Team extraction failed: {team_result['error']}")
        
        # Pause between leagues
        time.sleep(random.uniform(2, 5))
    
    # Summary
    print(f"\n=== SUMMARY ===")
    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'failed']
    errors = [r for r in results if r['status'] == 'error']
    
    print(f"Total leagues tested: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    print(f"Errors: {len(errors)}")
    
    # Show wrapper patterns used
    if successful:
        print(f"\n=== WORKING WRAPPER PATTERNS ===")
        wrapper_counts = {}
        for result in successful:
            wrapper = result['working_wrapper']
            wrapper_counts[wrapper] = wrapper_counts.get(wrapper, 0) + 1
        
        for wrapper, count in sorted(wrapper_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {wrapper}: {count} leagues")
    
    # Show failed leagues
    if failed or errors:
        print(f"\n=== FAILED LEAGUES ===")
        for result in failed + errors:
            print(f"  {result['league_name']} - {result['table_id']}: {result['error']}")
    
    # Save results to CSV
    df_results = pd.DataFrame(results)
    df_results.to_csv('data/wrapper_test_results.csv', index=False)
    print(f"\nResults saved to: data/wrapper_test_results.csv")
    
    # Show sample of successful extractions
    if successful_leagues:
        print(f"\n=== SAMPLE SUCCESSFUL EXTRACTIONS ===")
        for result in successful_leagues[:3]:  # Show first 3
            if 'team_extraction' in result and result['team_extraction']['status'] == 'success':
                teams = result['team_extraction']['team_links']
                print(f"  {result['league_name']}: {[t[0] for t in teams]}")

if __name__ == "__main__":
    main()
