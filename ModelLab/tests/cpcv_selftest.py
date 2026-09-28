from research.cpcv import cpcv_splits

def req(x,m):
    if not x: raise AssertionError(m)

splits=cpcv_splits(1200,n_groups=6,test_groups=2,purge_bars=24,embargo_bars=24,max_combinations=15)
req(len(splits)==15,'6 choose 2 CPCV combinations expected')
for tr,te,combo in splits:
    req(len(set(tr).intersection(set(te)))==0,'train/test overlap')
    for x in te:
        req(x not in set(tr),'test leaked into train')
print('CPCV_PURGE_EMBARGO PASS')
