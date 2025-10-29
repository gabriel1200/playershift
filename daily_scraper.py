import pandas as pd
import requests
import os
import time
from pathlib import Path
import logging
from typing import Set, Tuple, List, Dict, Any, Optional
import sys
import random
import concurrent.futures
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from datetime import date, datetime, timedelta

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_wowy_scraper.log'),
        logging.StreamHandler()
    ]
)

# Create a session with retry capabilities
def create_session_with_retries(retries=5, backoff_factor=0.5, 
                               status_forcelist=(500, 502, 503, 504, 429)):
    """Create a requests Session with automatic retries."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

# Use a session for all requests
session = create_session_with_retries()

# Headers pools to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Edge/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
]

ACCEPT_TYPES = [
    "application/json, text/plain, */*",
    "application/json",
    "application/json, text/javascript, */*; q=0.01",
    "*/*",
    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
]

ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.5",
    "en-GB,en;q=0.7,en-US;q=0.3",
    "en-US,en;q=0.8,es;q=0.5",
    "en-CA,en;q=0.9,fr-CA;q=0.7"
]

ACCEPT_ENCODINGS = [
    "gzip, deflate, br",
    "gzip, deflate",
    "br;q=1.0, gzip;q=0.8, *;q=0.1"
]

REFERERS = [
    "https://stats.nba.com/",
    "https://www.nba.com/",
    "https://www.nba.com/stats/",
    "https://www.nba.com/players/",
    "https://www.nba.com/teams/",
    "https://www.espn.com/nba/",
    "https://www.basketball-reference.com/"
]

HOSTS = [
    "stats.nba.com",
    "api.nba.com",
    "data.nba.com",
    "www.nba.com"
]

CONNECTIONS = [
    "keep-alive",
    "close"
]

CACHE_CONTROLS = [
    "max-age=0",
    "no-cache",
    "max-age=300"
]

def get_random_headers():
    """Generate random realistic headers to avoid detection."""
    user_agent = random.choice(USER_AGENTS)
    
    # Build header with mandatory fields
    headers = {
        "User-Agent": user_agent,
        "Accept": random.choice(ACCEPT_TYPES),
    }
    
    # Add optional headers with some randomness
    if random.random() > 0.2:  # 80% chance to include
        headers["Accept-Language"] = random.choice(ACCEPT_LANGUAGES)
    
    if random.random() > 0.2:  # 80% chance to include
        headers["Accept-Encoding"] = random.choice(ACCEPT_ENCODINGS)
        
    if random.random() > 0.1:  # 90% chance to include
        headers["Referer"] = random.choice(REFERERS)
        
    if random.random() > 0.3:  # 70% chance to include
        headers["Host"] = random.choice(HOSTS)
        
    if random.random() > 0.3:  # 70% chance to include
        headers["Connection"] = random.choice(CONNECTIONS)
        
    # Add some extra headers occasionally
    if random.random() > 0.7:  # 30% chance to include
        headers["Cache-Control"] = random.choice(CACHE_CONTROLS)
        
    if random.random() > 0.8:  # 20% chance to include
        headers["Pragma"] = "no-cache"
        
    if random.random() > 0.8:  # 20% chance to include
        headers["DNT"] = "1"
        
    if random.random() > 0.9:  # 10% chance to include
        headers["Upgrade-Insecure-Requests"] = "1"
        
    # Add some random cookies occasionally
    if random.random() > 0.9:  # 10% chance to include
        cookie_id = f"{random.randint(10000000, 99999999)}"
        session_id = f"session_{random.randint(1000000, 9999999)}"
        headers["Cookie"] = f"_ga=GA1.2.{cookie_id}.{int(time.time() - random.randint(1000000, 9999999))}; _gid=GA1.2.{cookie_id}; sessionid={session_id}"
        
    return headers

def wowy_shift(team_id: str, player1_id: str, seasons: List[str], ps=False, max_retries=5) -> pd.DataFrame:
    """
    Get WOWY (With Or Without You) stats for a player from the NBA stats API.
    
    Args:
        team_id: NBA team ID
        player1_id: NBA player ID
        seasons: List of seasons (e.g., ["2021-22"])
        ps: False for regular season, True for playoffs, 'all' for both
        max_retries: Maximum number of retries for failed requests
        
    Returns:
        DataFrame with WOWY stats
    """
    if ps == False:
        s_type = 'Regular Season'
    elif ps == 'all':
        s_type = 'All'
    else:
        s_type = 'Playoffs'
    
    seasons_str = ",".join(seasons)
    
    # Data for both requests
    datasets = [
        {
            "param_key": "0Exactly1OnFloor",
            "label": True,  # Player on
        },
        {
            "param_key": "0Exactly0OnFloor",
            "label": False,  # Player off
        }
    ]
    
    combined_data = []
    
    for dataset in datasets:
        retry_count = 0
        success = False
        
        while not success and retry_count < max_retries:
            try:
                headers = get_random_headers()
                wowy_params = {
                    dataset["param_key"]: player1_id,
                    "TeamId": team_id,
                    "Season": seasons_str,
                    "SeasonType": s_type,
                    "Type": "Player",
                }
                
                wowy_url = "https://api.pbpstats.com/get-wowy-stats/nba"
                response = session.get(wowy_url, params=wowy_params, headers=headers, timeout=10)
                
                if response.status_code != 200:
                    logging.warning(f"Got status code {response.status_code}, retrying {retry_count+1}/{max_retries}")
                    retry_count += 1
                    # Add jitter to avoid synchronized retries
                    time.sleep(1 + random.uniform(0, 2))
                    continue
                
                wowy = response.json()
                print(wowy)
                
                if not wowy.get("multi_row_table_data"):
                    logging.warning(f"No data returned for {player1_id} with {team_id}, retrying {retry_count+1}/{max_retries}")
                    retry_count += 1
                    time.sleep(1 + random.uniform(0, 2))
                    continue
                
                player_stats = wowy["multi_row_table_data"]
                df = pd.DataFrame(player_stats)
                df['on'] = dataset["label"]
                combined_data.append(df)
                success = True
                
                # Add slight delay between successful requests
                time.sleep(0.5 + random.uniform(0, 0.5))
                
            except Exception as e:
                retry_count += 1
                wait_time = 2 ** retry_count  # Exponential backoff
                logging.error(f"Error processing {player1_id} with {team_id}: {e}. Retrying in {wait_time}s")
                time.sleep(wait_time)
        
        if not success:
            logging.error(f"Failed to get data for {player1_id} with {team_id} after {max_retries} retries")
            # Return empty DataFrame if one request succeeded but not the other
            if combined_data:
                return combined_data[0]
            # Return completely empty DataFrame if both failed
            return pd.DataFrame()
    
    # If we get here, both requests were successful
    return pd.concat(combined_data) if combined_data else pd.DataFrame()

def setup_folders(base_dir: str, curr_date: str, is_playoff: bool) -> None:
    """Create folders for daily data if they don't exist."""
    trail = 'ps' if is_playoff else ''
    folder_path = Path(f"{base_dir}/{curr_date}_{trail}")
    folder_path.mkdir(parents=True, exist_ok=True)
    logging.info(f"Created folder: {folder_path}")
    return folder_path

def save_data(output_path: Path, data: pd.DataFrame) -> None:
    """Save data to CSV, creating the file if it doesn't exist."""
    try:
        if output_path.exists():
            existing_data = pd.read_csv(output_path)
            combined_data = pd.concat([existing_data, data], ignore_index=True)
            combined_data.drop_duplicates().to_csv(output_path, index=False)
        else:
            data.to_csv(output_path, index=False)
        logging.info(f"Successfully saved data to {output_path}")
    except Exception as e:
        logging.error(f"Error saving data to {output_path}: {e}")
        # Create backup in case of error
        backup_file = output_path.with_suffix('.backup.csv')
        try:
            data.to_csv(backup_file, index=False)
            logging.info(f"Created backup file {backup_file}")
        except Exception as backup_e:
            logging.error(f"Failed to create backup: {backup_e}")

def process_player_team_combination(
    nba_id: str, 
    team_id: str, 
    season: str, 
    curr_date: str,
    output_dir: Path,
    is_playoff: bool,
    max_retries: int = 5
) -> None:
    """Process a single player-team combination for daily data."""
    output_file = output_dir / f"{nba_id}.csv"
    
    logging.info(f"Processing player {nba_id} with team {team_id} for {curr_date}")
    
    try:
        # Add jitter to avoid synchronized requests
        time.sleep(random.uniform(0.1, 0.5))
        
        result = wowy_shift(
            team_id=str(team_id),
            player1_id=str(nba_id),
            seasons=[season],
            ps=is_playoff,
            max_retries=max_retries
        )
        
        if result.empty:
            logging.warning(f"No data returned for player {nba_id} with team {team_id}")
            return
        
        # Add metadata to the result
        result['game_date'] = curr_date
        result['player_id'] = nba_id
        result['team_id'] = team_id
        
        # Save data immediately after retrieval
        save_data(output_file, result)
        
    except Exception as e:
        logging.error(f"Error processing player {nba_id} with team {team_id}: {e}")

def get_previous_day_date():
    """Get yesterday's date in YYYYMMDD format."""
    yesterday = date.today() - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")

def get_daily_games_index(date_str: str):
    """Get the index of games played on a specific date."""
    try:
        # Load game dates
        dates = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/shot_data/refs/heads/master/game_dates.csv')
        dates = dates[dates.date == int(date_str)]
        
        if dates.empty:
            logging.warning(f"No games found for date {date_str}")
            return None, None, None
        
        # Get teams that played on this date
        teams = dates['TEAM_ID'].unique()
        is_playoffs = dates.playoffs.iloc[0]
        season = dates.season.iloc[0]
        season_year = int(season.split('-')[0]) + 1
        
        # Get appropriate index file
        if not is_playoffs:
            index_file = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master.csv')
        else:
            index_file = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master_ps.csv')
        
        # Filter for relevant data
        index_file.dropna(subset=['nba_id', 'team_id'], inplace=True)
        index_file = index_file[index_file.team != 'TOT']
        index_file = index_file[index_file.year == season_year]
        daily_index = index_file[index_file.team_id.isin(teams)]
        
        logging.info(f"Found {len(daily_index)} player-team combinations for {date_str}")
        return daily_index, is_playoffs, season
    
    except Exception as e:
        logging.error(f"Error getting daily games index for {date_str}: {e}")
        return None, None, None

def process_daily_data(
    date_str: str = None, 
    data_dir: str = "daily_data",
    concurrent_requests: int = 1
):
    """Process WOWY data for the previous day's games."""
    try:
        # Get yesterday's date if not provided
        if date_str is None:
            date_str = get_previous_day_date()
        
        logging.info(f"Processing data for date: {date_str}")
        
        # Get games and players for the given date
        daily_index, is_playoffs, season = get_daily_games_index(date_str)
        
        if daily_index is None or daily_index.empty:
            logging.warning(f"No data to process for {date_str}")
            return
        
        # Setup output directory
        output_dir = setup_folders(data_dir, date_str, is_playoffs)
        
        # Process all player-team combinations
        player_teams = []
        for _, row in daily_index.iterrows():
            nba_id, team_id = int(row['nba_id']), row['team_id']
            player_teams.append((nba_id, team_id))
        
        logging.info(f"Processing {len(player_teams)} player-team combinations")
        
        # Process in batches with concurrent requests
        batch_size = 15  # Process 15 players at a time
        for i in range(0, len(player_teams), batch_size):
            batch = player_teams[i:i+batch_size]
            logging.info(f"Processing batch {i//batch_size + 1}/{(len(player_teams) + batch_size - 1)//batch_size}")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_requests) as executor:
                futures = []
                for nba_id, team_id in batch:
                    futures.append(
                        executor.submit(
                            process_player_team_combination,
                            str(nba_id),
                            str(team_id),
                            season,
                            date_str,
                            output_dir,
                            is_playoffs
                        )
                    )
                
                # Wait for all futures to complete
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        logging.error(f"Error in thread execution: {e}")
            
            # Add delay between batches to avoid rate limiting
            if i + batch_size < len(player_teams):
                logging.info("Waiting before processing next batch...")
                time.sleep(5 + random.uniform(0, 3))
        
        logging.info(f"Completed processing data for {date_str}")
        
    except Exception as e:
        logging.error(f"Error in process_daily_data: {e}")

def main():
    # Parse command line arguments if any
    import argparse
    parser = argparse.ArgumentParser(description='Daily NBA WOWY data scraper')
    parser.add_argument('--date', type=str, default=None, 
                        help='Date to process in YYYYMMDD format. Defaults to yesterday.')
    parser.add_argument('--datadir', type=str, default='daily_data',
                        help='Directory to store the scraped data')
    parser.add_argument('--concurrent', type=int, default=3,
                        help='Number of concurrent requests')
    
    args = parser.parse_args()
    
    # Create base data directory if it doesn't exist
    Path(args.datadir).mkdir(parents=True, exist_ok=True)
    
    # Process the data
    process_daily_data(
        date_str=args.date,
        data_dir=args.datadir,
        concurrent_requests=args.concurrent
    )

if __name__ == "__main__":
    main()