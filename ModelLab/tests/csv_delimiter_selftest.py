from pathlib import Path
import tempfile
import pandas as pd

from data.dataset_integrity import read_csv_auto, build_research_window_snapshot
from factory.champion_factory import _dataset_identity


def main():
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        rows=pd.DataFrame({
            'contract':['CP32_V1','CP32_V1'],
            'signal_time':['2021.01.04 00:00','2021.01.04 01:00'],
            'decision_bar_time':['2021.01.04 01:00','2021.01.04 02:00'],
            'symbol':['EURUSD.m','EURUSD.m'],
            'period':[16385,16385],
            'open':[1,1],'high':[1,1],'low':[1,1],'close':[1,1],
        })
        semi=td/'master_semicolon.csv'; comma=td/'internal_comma.csv'
        rows.to_csv(semi,sep=';',index=False)
        rows.to_csv(comma,index=False)
        cols=['symbol','period','signal_time']
        a=read_csv_auto(semi,usecols=cols)
        b=read_csv_auto(comma,usecols=cols)
        assert set(a.columns)==set(cols) and set(b.columns)==set(cols)
        assert a.iloc[0]['symbol']=='EURUSD.m' and b.iloc[0]['symbol']=='EURUSD.m'
        snap=td/'snapshot.csv'
        build_research_window_snapshot(semi,'2021-01-04','2021-01-04',snap)
        ident=_dataset_identity(snap)
        assert ident['symbol']=='EURUSD.m' and ident['period']==16385 and ident['rows']==2
        # The actual failure class: usecols must work on semicolon authority.
        got=read_csv_auto(snap,usecols=['signal_time','period','symbol'])
        assert set(got.columns)=={'signal_time','period','symbol'}
    print('CSV_DELIMITER_AUTHORITY_SELFTEST PASS')

if __name__=='__main__':
    main()
