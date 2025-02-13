import pandas as pd
frames = []
for year in range(2001,2025):
    trail='ps'
    print('loading '+str(year))
    url=f'https://raw.githubusercontent.com/gabriel1200/playershift/refs/heads/main/years/{year}{trail}.csv'
    df=pd.read_csv(url)
    frames.append(df)


for year in range(2001,2026):
    trail=''
    print('loading '+str(year))
    url=f'https://raw.githubusercontent.com/gabriel1200/playershift/refs/heads/main/years/{year}{trail}.csv'
    df=pd.read_csv(url)
    frames.append(df)

master=pd.concat(frames)
file_name='shift_master.csv'
master.to_csv(file_name,index=False)