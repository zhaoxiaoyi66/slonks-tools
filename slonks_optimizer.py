#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv
from pathlib import Path

def f(x):
    try:return float(x)
    except:return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pairs',default='pairs.csv')
    ap.add_argument('--ranked',default='ranked_pairs.csv')
    ap.add_argument('--plan',default='merge_plan.csv')
    ap.add_argument('--base-slope',type=float,default=0)
    args=ap.parse_args()
    rows=list(csv.DictReader(Path(args.pairs).open('r',encoding='utf-8')))
    ok=[r for r in rows if r.get('status')=='ok' and r.get('result_slop')]
    for r in ok:
        rs=f(r['result_slop']) or 0; pe=f(r.get('price_eth'))
        gross=rs-args.base_slope; net=gross
        r['gross_delta']=gross; r['net_delta']=net
        r['gross_slop_per_eth']=gross/pe if pe and pe>0 else ''
        r['net_slop_per_eth']=net/pe if pe and pe>0 else ''
    ok.sort(key=lambda r: ((f(r['net_slop_per_eth']) if r['net_slop_per_eth']!='' else -1e18),(f(r['gross_slop_per_eth']) if r['gross_slop_per_eth']!='' else -1e18),f(r['result_slop']) or -1e18), reverse=True)
    for i,r in enumerate(ok,1): r['rank']=i
    fields=['rank','survivor_id','donor_id','result_slop','price_eth','gross_delta','net_delta','gross_slop_per_eth','net_slop_per_eth','url','marketplace','status','note']
    with Path(args.ranked).open('w',encoding='utf-8',newline='') as fcsv:
        w=csv.DictWriter(fcsv,fieldnames=fields);w.writeheader();w.writerows(ok)
    used=set();plan=[]
    for r in ok:
        s,d=r['survivor_id'],r['donor_id']
        if s in used or d in used: continue
        used|={s,d}; plan.append(r)
    with Path(args.plan).open('w',encoding='utf-8',newline='') as fcsv:
        w=csv.DictWriter(fcsv,fieldnames=fields);w.writeheader();w.writerows(plan)

if __name__=='__main__':main()
