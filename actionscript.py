import pandas as pd
import requests
import os
import time
import shutil
from pathlib import Path
import logging
from typing import Set, Tuple
import sys
from datetime import datetime, timedelta
import random
from requests.exceptions import RequestException, ConnectionError, Timeout

def make_api_request(url, params, headers, max_retries=5, initial_wait=2):
    """Make an API request with exponential backoff retry logic."""
    retries = 0
    while retries <= max_retries:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            return response.json()
        except (RequestException, ConnectionError, Timeout, ValueError) as e:
            wait_time = initial_wait * (2 ** retries) + random.uniform(0, 1)  # Exponential backoff with jitter
            retries += 1
            
            if retries > max_retries:
                raise Exception(f"Maximum retries reached. Last error: {str(e)}")
            
            logging.warning(f"Request failed: {str(e)}. Retrying in {wait_time:.2f} seconds (attempt {retries}/{max_retries})")
            time.sleep(wait_time)

def wowy_shift(team_id, player1_id, seasons, ps=False, common=False, max_retries=5):
    player_id = player1_id
    team_id = team_id
    
    if ps == False:
        s_type = 'Regular Season'
    elif ps == 'all':
        s_type = 'All'
    else:
        s_type = 'Playoffs'
                                  
    wowy_url = "https://api.pbpstats.com/get-wowy-stats/nba"
    headers1 = {
        "Host": "stats.nba.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:72.0) Gecko/20100101 Firefox/72.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": "https://stats.nba.com/"
    }
    
    # Player on floor parameters
    wowy_params_on = {
        "0Exactly1OnFloor": player_id,  # Player on
        "TeamId": team_id,  # Team ID
        "Season": ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player",  # Player stats
    }
    
    # Get stats with player on floor
    wowy_data = make_api_request(wowy_url, wowy_params_on, headers1, max_retries)
    player_stats_on = wowy_data["multi_row_table_data"]
    
    # Wait to avoid rate limiting
    time.sleep(2)
    
    # Player off floor parameters
    wowy_params_off = {
        "0Exactly0OnFloor": player_id,  # Player off
        "TeamId": team_id,  # Team ID
        "Season": ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player",  # Player stats
    }
    
    # Get stats with player off floor
    wowy_data = make_api_request(wowy_url, wowy_params_off, headers1, max_retries)
    player_stats_off = wowy_data["multi_row_table_data"]
   
    # Create and combine dataframes
    df = pd.DataFrame(player_stats_on)
    df['on'] = True
    df2 = pd.DataFrame(player_stats_off)
    df2['on'] = False

    combo = pd.concat([df, df2])
    return combo

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wowy_scraper.log'),
        logging.StreamHandler()
    ]
)

def setup_folders(base_year: int, ps=False) -> None:
    """Create folders for the daily scrape and the main data folder."""
    trail = 'ps' if ps else ''
    
    # Create daily temp folder
    daily_folder = Path(f"daily_data/{base_year}{trail}")
    daily_folder.mkdir(parents=True, exist_ok=True)
    
    # Create main data folder
    main_folder = Path(f"data/{base_year}{trail}")
    main_folder.mkdir(parents=True, exist_ok=True)
    
    return daily_folder, main_folder

def get_processed_combinations(year: int, ps=False) -> Set[Tuple[str, str]]:
    """Get already processed player-team combinations for a given year."""
    trail = 'ps' if ps else ''
    year_dir = Path(f"data/{year}{trail}")
    processed = set()
    
    if year_dir.exists():
        for file in year_dir.glob("*.csv"):
            nba_id = file.stem
            try:
                df = pd.read_csv(file)
                team_ids = df['TeamId'].unique()
                for team_id in team_ids:
                    processed.add((nba_id, str(team_id)))
            except Exception as e:
                logging.error(f"Error reading file {file}: {e}")
    
    return processed

def copy_daily_files(daily_folder: Path, main_folder: Path) -> None:
    """Copy files from daily folder to main data folder."""
    for file in daily_folder.glob("*.csv"):
        dest_file = main_folder / file.name
        
        try:
            # Just copy the file (overwrite if exists)
            shutil.copy2(file, dest_file)
            logging.info(f"Copied {file.name} to main data folder")
        except Exception as e:
            logging.error(f"Error copying {file.name}: {e}")

def process_daily_data(year: int, is_postseason: bool, index_df: pd.DataFrame, max_retries=3) -> None:
    """Process data for all players for the given year with retry mechanisms."""
    daily_folder, main_folder = setup_folders(year, ps=is_postseason)
    
    # Clear the daily folder first to ensure fresh data
    for file in daily_folder.glob("*.csv"):
        try:
            file.unlink()
        except Exception as e:
            logging.error(f"Error removing old file {file}: {e}")
    
    trail = 'ps' if is_postseason else ''
    season_start = str(year - 1)
    season_end = str(year)
    seasons = [f"{season_start}-{season_end[-2:]}"]
    
    # Ensure numeric nba_id
    index_df['nba_id'] = index_df['nba_id'].astype(int)
    
    # Get all players for the current year
    current_players = index_df[index_df['year'] == year]
    
    total_players = len(current_players.groupby('nba_id'))
    logging.info(f"Processing {total_players} players for {year} {'playoffs' if is_postseason else 'regular season'}")
    
    # Track progress
    processed_count = 0
    successful_count = 0
    
    for nba_id, group in current_players.groupby('nba_id'):
        processed_count += 1
        output_file = daily_folder / f"{int(nba_id)}.csv"
        player_data = pd.DataFrame()
        
        # Get unique team_ids for this player in this season
        team_ids = group['team_id'].unique()
        player_success = False
        
        for team_id in team_ids:
            # Implement retry logic at the team level
            for retry in range(max_retries + 1):
                try:
                    if retry > 0:
                        logging.info(f"Retry {retry}/{max_retries} for player {nba_id} - team {team_id}")
                    else:
                        logging.info(f"Processing {nba_id} - {team_id} for {year} ({processed_count}/{total_players})")
                    
                    # Call wowy_shift function with its own retry mechanism
            
                    result = wowy_shift(
                        team_id=team_id,
                        player1_id=str(int(nba_id)),
                        seasons=seasons,
                        ps=is_postseason,
                        max_retries=3  # API-level retries
                    )
                   
                    # Add to the player's data
                    player_data = pd.concat([player_data, result], ignore_index=True)
                    player_success = True
                    
                    # Add jitter to rate limiting
                    time.sleep(2 + random.uniform(0, 1))
                    break  # Success, exit retry loop
                            
                except Exception as e:
                    if retry < max_retries:
                        wait_time = 2 * (retry + 1) + random.uniform(0, 2)
                        logging.warning(f"Error processing {nba_id} - {team_id}: {e}. Retrying in {wait_time:.2f}s")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"Failed after {max_retries} retries for {nba_id} - {team_id}: {e}")
        
        # Save the player's data to csv
        if not player_data.empty:
            try:
                player_data.to_csv(output_file, index=False)
                logging.info(f"Saved data for player {nba_id} to {output_file}")
                successful_count += 1
            except Exception as e:
                logging.error(f"Error saving data for player {nba_id}: {e}")
        elif player_success:
            # Create empty dataframe with expected columns if we had success but no data
            empty_df = pd.DataFrame(columns=["TeamId", "on"])
            empty_df.to_csv(output_file, index=False)
            logging.warning(f"Player {nba_id} returned no data, saving empty file")
            successful_count += 1
        
        # Log progress periodically
        if processed_count % 10 == 0:
            completion = (processed_count / total_players) * 100
            logging.info(f"Progress: {processed_count}/{total_players} players processed ({completion:.1f}%)")
    
    # After processing, copy all files to main folder
    logging.info(f"Successfully processed {successful_count}/{total_players} players. Copying files to main folder...")
    copy_daily_files(daily_folder, main_folder)
    
    return daily_folder, main_folder

def main():
    start_time = datetime.now()
    logging.info(f"Starting daily scrape at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Set the current year
    current_year = datetime.now().year
    
    # Load data with retries
    max_retries = 3
    retry_count = 0
    index_reg = None
    index_ps = None
    
    while retry_count <= max_retries:
        try:
            logging.info("Loading player index data...")
            # Load regular season data
            index_reg = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master.csv')
            index_reg.dropna(subset='nba_id', inplace=True)
            index_reg.dropna(subset='team_id', inplace=True)
            index_reg = index_reg[index_reg.team != 'TOT']
            
            # Load playoff data
            index_ps = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master_ps.csv')
            index_ps = index_ps[index_ps.team != 'TOT']
            
            logging.info(f"Data loaded successfully. Found {len(index_reg)} regular season entries and {len(index_ps)} playoff entries.")
            break
            
        except Exception as e:
            retry_count += 1
            if retry_count > max_retries:
                logging.error(f"Failed to load index files after {max_retries} attempts: {e}")
                return
            
            wait_time = 5 * retry_count
            logging.warning(f"Error loading index files: {e}. Retrying in {wait_time} seconds (attempt {retry_count}/{max_retries})")
            time.sleep(wait_time)

    # Create initial folders
    setup_folders(current_year)
    setup_folders(current_year, ps=True)

    # Check if we're in playoff season (April through June)
    current_month = datetime.now().month
    is_playoff_season = 4 <= current_month <= 6
    
    try:
        # Process regular season data (always)
        logging.info(f"Starting daily scrape for regular season {current_year}")
        daily_folder, main_folder = process_daily_data(current_year, False, index_reg)
        
        # Process postseason data (only during playoff season)
        if is_playoff_season:
            logging.info(f"Starting daily scrape for postseason {current_year}")
            daily_folder_ps, main_folder_ps = process_daily_data(current_year, True, index_ps)
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        logging.info(f"Daily scraping completed successfully")
        logging.info(f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"Total duration: {duration}")
        
    except Exception as e:
        logging.error(f"Uncaught exception during scraping: {e}")
        raise  # Re-raise to ensure we see the full traceback

if __name__ == "__main__":
    main()