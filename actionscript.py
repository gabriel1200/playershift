import pandas as pd
import requests
import os
import time
from pathlib import Path
import logging
from typing import Set, Tuple
import sys

def wowy_shift(team_id,player1_id,seasons,ps = False, common = False):
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
    headers2 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}
    
    wowy_params = {
        "0Exactly1OnFloor": player_id, # Player on
        "TeamId": team_id, # Golden State Warriors
        "Season": ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player", # Player stats,

    }
    wowy_response = requests.get(wowy_url, params=wowy_params,headers=headers1)

    wowy = wowy_response.json()
    player_stats_on = wowy["multi_row_table_data"]
    wowy_url = "https://api.pbpstats.com/get-wowy-stats/nba"
    wowy_params = {
        "0Exactly0OnFloor": player_id,# Player on
        "TeamId": team_id, # Golden State Warriors
        "Season":  ",".join(seasons),
        "SeasonType": s_type,
        "Type": "Player", # Player stats,
    }
    #print(seasons)
    time.sleep(2)
    wowy_response = requests.get(wowy_url, params=wowy_params,headers=headers1)
    wowy = wowy_response.json()
    player_stats_off = wowy["multi_row_table_data"]
    #print(rts)
   
    df = pd.DataFrame(player_stats_on)
    df['on'] = True
    df2 = pd.DataFrame(player_stats_off)
    df2['on'] = False

    combo = pd.concat([df,df2])


     

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

def setup_folders(base_year: int, end_year: int,ps=False) -> None:
    """Create folders for each season if they don't exist."""
    trail='ps' if ps else ''
    for year in range(base_year, end_year + 1):
        Path(f"data/{year}{trail}").mkdir(parents=True, exist_ok=True)

def get_processed_combinations(year: int,ps=False) -> Set[Tuple[str, str]]:
    """Get already processed player-team combinations for a given year."""
    trail ='ps' if ps else ''
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
    #logging.info(processed)
    return processed

def process_season_data(year: int, is_postseason: bool, index_df: pd.DataFrame, 
                       processed_combinations: Set[Tuple[str, str]]) -> None:
    """Process data for a single season."""
    trail = 'ps' if is_postseason else ''
    season_start = str(year - 1)
    season_end = str(year)
    seasons = [f"{season_start}-{season_end[-2:]}"]
    index_df['nba_id']=index_df['nba_id'].astype(int)
    # Group by nba_id to handle multiple teams
    print(len(processed_combinations))
    print(len(index_df[index_df['year'] == year][['nba_id','team_id']]))
    for nba_id, group in index_df[index_df['year'] == year].groupby('nba_id'):
        
        output_file = Path(f"data/{int(year)}{trail}/{int(nba_id)}.csv")
        
        # Get unique team_ids for this player in this season
        team_ids = group['team_id'].unique()
        
        for team_id in team_ids:
            # Skip if already processed
            if (str(nba_id), str(team_id)) in processed_combinations:
                #logging.info(f"Skipping already processed combination: {nba_id} - {team_id} for {year}")
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
                processed_combinations.add((nba_id, str(team_id)))
       
                
                # Rate limiting
               
                
            except Exception as e:
                logging.error(f"Error processing {nba_id} - {team_id} for {year}: {e}")
                time.sleep(2.5)
                continue

def main():
    # Load data
    try:
        index_reg = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master.csv')
        index_reg.dropna(subset='nba_id',inplace=True)
        index_reg.dropna(subset='team_id',inplace=True)

        index_reg=index_reg[index_reg.team!='TOT']
        index_ps = pd.read_csv('https://raw.githubusercontent.com/gabriel1200/site_Data/refs/heads/master/index_master_ps.csv')
        index_ps=index_ps[index_ps.team!='TOT']

    except Exception as e:
        logging.error(f"Error loading index files: {e}")
        return

    # Create folders
    #setup_folders(2010, 2025)
    #setup_folders(2001, 2024,ps=True)


    # Process postseason (2001-2024)
    for year in range(2025, 2025):
        logging.info(f"Processing postseason {year}")
        processed = get_processed_combinations(year,ps=True)
        process_season_data(year, True, index_ps, processed)

    # Process regular season (2001-2025)
    for year in range(2025, 2026):
        logging.info(f"Processing regular season {year}")
        processed = get_processed_combinations(year)
        process_season_data(year, False, index_reg, processed)
   


if __name__ == "__main__":
    main()