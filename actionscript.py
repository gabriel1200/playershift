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

def wowy_shift(team_id, player1_id, seasons, ps=False, common=False):
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
    
    wowy_params = {
        "0Exactly1OnFloor": player_id,  # Player on
        "TeamId": team_id,  # Team ID
        "Season": ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player",  # Player stats
    }
    wowy_response = requests.get(wowy_url, params=wowy_params, headers=headers1)

    wowy = wowy_response.json()
    player_stats_on = wowy["multi_row_table_data"]
    
    wowy_url = "https://api.pbpstats.com/get-wowy-stats/nba"
    wowy_params = {
        "0Exactly0OnFloor": player_id,  # Player off
        "TeamId": team_id,  # Team ID
        "Season": ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player",  # Player stats
    }
    
    time.sleep(2)
    wowy_response = requests.get(wowy_url, params=wowy_params, headers=headers1)
    wowy = wowy_response.json()
    player_stats_off = wowy["multi_row_table_data"]
   
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

def get_recently_processed(daily_folder: Path) -> Set[Tuple[str, str]]:
    """Get combinations processed in the current daily run."""
    processed_today = set()
    
    if daily_folder.exists():
        for file in daily_folder.glob("*.csv"):
            nba_id = file.stem
            try:
                df = pd.read_csv(file)
                team_ids = df['TeamId'].unique()
                for team_id in team_ids:
                    processed_today.add((nba_id, str(team_id)))
            except Exception as e:
                logging.error(f"Error reading file {file}: {e}")
    
    return processed_today

def copy_daily_files(daily_folder: Path, main_folder: Path) -> None:
    """Copy or merge files from daily folder to main data folder."""
    for file in daily_folder.glob("*.csv"):
        dest_file = main_folder / file.name
        
        if dest_file.exists():
            # If file exists in main folder, merge the data
            try:
                daily_data = pd.read_csv(file)
                main_data = pd.read_csv(dest_file)
                
                # Combine and remove duplicates
                combined_data = pd.concat([main_data, daily_data], ignore_index=True)
                combined_data.drop_duplicates().to_csv(dest_file, index=False)
                logging.info(f"Merged {file.name} into main data folder")
            except Exception as e:
                logging.error(f"Error merging {file.name}: {e}")
        else:
            # If file doesn't exist, simply copy it
            try:
                shutil.copy2(file, dest_file)
                logging.info(f"Copied {file.name} to main data folder")
            except Exception as e:
                logging.error(f"Error copying {file.name}: {e}")

def process_daily_data(year: int, is_postseason: bool, index_df: pd.DataFrame, 
                       processed_combinations: Set[Tuple[str, str]], 
                       max_players: int = 20) -> None:
    """Process data for a daily run, with a limit on players processed."""
    daily_folder, main_folder = setup_folders(year, ps=is_postseason)
    
    # Get already processed combinations from today's run
    today_processed = get_recently_processed(daily_folder)
    
    # Combined set of all processed combinations
    all_processed = processed_combinations.union(today_processed)
    
    trail = 'ps' if is_postseason else ''
    season_start = str(year - 1)
    season_end = str(year)
    seasons = [f"{season_start}-{season_end[-2:]}"]
    
    index_df['nba_id'] = index_df['nba_id'].astype(int)
    
    # Get players who played in the last day
    # For demonstration, we'll use a simple filter
    # In a real scenario, you might want to filter by recent games
    recent_players = index_df[index_df['year'] == year].sample(min(max_players, len(index_df[index_df['year'] == year])))
    
    player_count = 0
    for nba_id, group in recent_players.groupby('nba_id'):
        # Stop if we've processed enough players
        if player_count >= max_players:
            break
            
        output_file = daily_folder / f"{int(nba_id)}.csv"
        
        # Get unique team_ids for this player in this season
        team_ids = group['team_id'].unique()
        
        for team_id in team_ids:
            # Skip if already processed
            if (str(nba_id), str(team_id)) in all_processed:
                continue
                
            try:
                logging.info(f"Processing {nba_id} - {team_id} for {year}")
                
                # Call wowy_shift function
                time.sleep(2)
                result = wowy_shift(
                    team_id=team_id,
                    player1_id=str(int(nba_id)),
                    seasons=seasons,
                    ps=is_postseason
                )
               
                # If file exists, append; if not, create new
                if output_file.exists():
                    existing_data = pd.read_csv(output_file)
                    combined_data = pd.concat([existing_data, result], ignore_index=True)
                    combined_data.drop_duplicates().to_csv(output_file, index=False)
                else:
                    result.to_csv(output_file, index=False)
                
                # Add to processed set
                all_processed.add((str(nba_id), str(team_id)))
                            
            except Exception as e:
                logging.error(f"Error processing {nba_id} - {team_id} for {year}: {e}")
                time.sleep(2.5)
                continue
        
        player_count += 1
    
    # After processing, copy files to main folder
    copy_daily_files(daily_folder, main_folder)
    
    return daily_folder, main_folder

def main():
    # Set the current year
    current_year = datetime.now().year
    
    # Load data
    try:
        index_reg = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master.csv')
        index_reg.dropna(subset='nba_id', inplace=True)
        index_reg.dropna(subset='team_id', inplace=True)
        index_reg = index_reg[index_reg.team != 'TOT']
        
        index_ps = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master_ps.csv')
        index_ps = index_ps[index_ps.team != 'TOT']

    except Exception as e:
        logging.error(f"Error loading index files: {e}")
        return

    # Create initial folders
    setup_folders(current_year)
    setup_folders(current_year, ps=True)

    # Check if we're in playoff season (April through June)
    current_month = datetime.now().month
    is_playoff_season = 4 <= current_month <= 6
    
    # Process regular season data (always)
    logging.info(f"Processing regular season {current_year}")
    processed = get_processed_combinations(current_year)
    daily_folder, main_folder = process_daily_data(current_year, False, index_reg, processed)
    
    # Process postseason data (only during playoff season)
    if is_playoff_season:
        logging.info(f"Processing postseason {current_year}")
        processed = get_processed_combinations(current_year, ps=True)
        daily_folder_ps, main_folder_ps = process_daily_data(current_year, True, index_ps, processed)

    logging.info("Daily scraping completed")

if __name__ == "__main__":
    main()