#!/usr/bin/env python3
"""
fbref_scraper.py

Este script scrapea estadísticas de jugadores de múltiples ligas de fbref.com.
Uso:
    python fbref_scraper.py

Requiere:
    pip install cloudscraper beautifulsoup4 pandas
"""
import random
import time
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from functools import reduce

# -----------------------------
# Configuración global
# -----------------------------

# Rotación de headers para simular diferentes navegadores/dispositivos
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

# Inicializar cloudscraper para manejar Cloudflare
scraper = cloudscraper.create_scraper()

# Función para peticiones con header aleatorio
def fetch_with_random_header(url: str, **kwargs):
    headers = random.choice(HEADERS_LIST)
    return scraper.get(url, headers=headers, **kwargs)

# -----------------------------
# Funciones de scraping
# -----------------------------

def get_team_links(league_name: str, league_url: str, lid:str) -> list[tuple[str, str, str]]:
    """
    Devuelve lista de (team_name, team_url, league_name) de la página de la liga.
    """
    resp = fetch_with_random_header(league_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    wrapper = soup.find("div", {"id": f"all_{lid}"})
    table = wrapper and wrapper.find("table", {"id": f"{lid}_overall"}) 
    if not table or not table.tbody:
        raise RuntimeError("No se encontró la tabla de squads. Revisar ID o wrapper.")

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
        links.append((team_name, team_href, league_name))
    return links


def scrape_team_stats(team_name: str, team_url: str, league_name: str) -> pd.DataFrame:
    resp = fetch_with_random_header(team_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    logo_tag = soup.find("img", {"class": "teamlogo"})
    team_logo = urljoin(team_url, logo_tag["src"]) if logo_tag and logo_tag.get("src") else None

    # Base IDs a escanear dinámicamente
    base_ids = [
        "stats_standard_", "stats_keeper_adv_", "stats_shooting_",
        "stats_passing_", "stats_passing_types_", "stats_gca_",
        "stats_defense_", "stats_possession_", "stats_playing_time_",
    ]

    dfs = []
    for idx, base in enumerate(base_ids):
        found = False
        table = None
        # Iterar sufijos de 0 a 99
        for n in range(100):
            table_id = f"{base}{n}"
            tbl = soup.find("table", {"id": table_id})
            if tbl and tbl.thead and tbl.tbody:
                table = tbl
                found = True
                break
        if not found:
            print(f"No se encontró tabla con prefijo '{base}' para {team_name}")
            continue

        # Extraer columnas
        header_rows = table.thead.find_all("tr")
        cols = [th['data-stat'] for th in header_rows[1].find_all("th")]

        # Extraer registros
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
        # Limpieza básica
        if "nationality" in df.columns:
            df["nationality"] = df["nationality"].apply(lambda x: x.split(" ")[-1] if len(x.split(" ")) > 1 else x)
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
    df_all["Team"] = team_name
    df_all["League"] = league_name
    df_all["Team_Logo"] = team_logo
    # Quitar sufijos automáticos
    df_all.columns = [c.rstrip('_x').rstrip('_y') for c in df_all.columns]

    return df_all

# -----------------------------
# Main
# -----------------------------

def main():
    urls = [
        #("https://fbref.com/en/comps/12/La-Liga-Stats","La Liga", "results2024-2025121"),
        #("https://fbref.com/en/comps/9/Premier-League-Stats","Premier League", "results2024-202591"),
        #("https://fbref.com/en/comps/11/Serie-A-Stats","Serie A", "results2024-2025111"),
        #("https://fbref.com/en/comps/20/Bundesliga-Stats","Bundesliga", "results2024-2025201"),
        #("https://fbref.com/en/comps/13/Ligue-1-Stats","Ligue 1", "results2024-2025131"),
        #("https://fbref.com/en/comps/22/Major-League-Soccer-Stats","Major League Soccer Eastern Conf", "results2025221Eastern-Conference"),
        #("https://fbref.com/en/comps/22/Major-League-Soccer-Stats","Major League Soccer Western Conf", "results2025221Western-Conference"),
        #("https://fbref.com/en/comps/10/Championship-Stats","Premier Championship England", "results2024-2025101"),
        #("https://fbref.com/en/comps/24/Serie-A-Stats","Brasileirao", "results2025241"),
        #("https://fbref.com/en/comps/32/Primeira-Liga-Stats","Primeira Liga", "results2024-2025321"),
        #("https://fbref.com/en/comps/23/Eredivisie-Stats","Eredivisie", "results2024-2025231"),
        #("https://fbref.com/en/comps/31/2024-2025/2024-2025-Liga-MX-Stats","Liga MX", "results2024-2025310"),
        #("https://fbref.com/en/comps/21/Liga-Profesional-Argentina-Stats","Liga Argentina", "results2025210"),
        #("https://fbref.com/en/comps/37/Belgian-Pro-League-Stats"," Belgian Pro League", "results2024-2025371"),
        #("https://fbref.com/en/comps/17/Segunda-Division-Stats","Liga Hypermotion", "results2024-2025171"),
        #("https://fbref.com/en/comps/25/J1-League-Stats","J1 League", "results2025251"),
        #("https://fbref.com/en/comps/26/Super-Lig-Stats","Turkiye Super Lig", "results2024-2025261"),
        #("https://fbref.com/en/comps/38/Serie-B-Stats","Brasileirao B", "results2025381"),
        #("https://fbref.com/en/comps/70/Saudi-Professional-League-Stats","Saudi Pro League", "results2024-2025701"),
        #("https://fbref.com/en/comps/18/Serie-B-Stats","Serie B", "results2024-2025181"),
        #("https://fbref.com/en/comps/56/history/Austrian-Bundesliga-Stats","Austrian Bundesliga", "results2024-2025560"),
        ("https://fbref.com/en/comps/67/2024-2025/2024-2025-Bulgarian-First-League-Stats","Bulgarian First League", "results2024-2025670"),
        ("https://fbref.com/en/comps/62/2024/2024-Chinese-Super-League-Stats","Chinese Super League", "results2024621"),
        ("https://fbref.com/en/comps/63/Hrvatska-NL-Stats","Croatian League", "results2024-2025631"),
        ("https://fbref.com/en/comps/50/2024-2025/2024-2025-Danish-Superliga-Stats","Danish Superliga", "results2024-2025500"),
        ("https://fbref.com/en/comps/27/history/Super-League-Greece-Stats","Greece Super League", "results2024-2025270"),
        ("https://fbref.com/en/comps/55/2024/2024-K-League-1-Stats","Korean League 1", "results2024550"),
        ("https://fbref.com/en/comps/47/2024-2025/2024-2025-Liga-I-Stats","Roumanian League I", "results2024-2025470"),
        ("https://fbref.com/en/comps/57/2024-2025/2024-2025-Swiss-Super-League-Stats","Swiss Super League", "results2024-2025570"),
        ("https://fbref.com/en/comps/28/2024/2024-Eliteserien-Stats","Eliteserien", "results2024281"),
        ("https://fbref.com/en/comps/66/2024-2025/2024-2025-Czech-First-League-Stats","Czech First League", "results2024-2025660"),
        ("https://fbref.com/en/comps/43/2024/2024-Veikkausliiga-Stats","Veikkausliiga", "results2024430")
    ]

    all_data = []
    for league_url, league_name, lid in urls:
        print(f"=== Liga: {league_name} ===")
        try:
            links = get_team_links(league_name, league_url, lid)
        except Exception as e:
            print(f"Error obteniendo equipos de {league_name}: {e}")
            continue

        for team_name, team_url, lg in links:
            print(f"Scrapeando: {team_name} ({lg})...")
            try:
                df_team = scrape_team_stats(team_name, team_url, lg)
                if not df_team.empty:
                    all_data.append(df_team)
            except Exception as e:
                print(f"Error scrapeando {team_name}: {e}")
            time.sleep(random.uniform(5, 12))

        # Concatenar todas las ligas y exportar
        if all_data:
            df_final = pd.concat(all_data, ignore_index=True, sort=False)
            df_final.to_csv(f"data/players_all_leagues_until_{league_name}.csv", index=False)
            print(f"Datos exportados a players_all_leagues_until_{league_name}.csv")
        else:
            print("No se obtuvo ningún dato.")

if __name__ == "__main__":
    main()
