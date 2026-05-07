#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv
from pathlib import Path
from slonks_pair_preview import run as run_pair
import requests

SLONKS='0x832233ddb7bcffd0ed53127dd6be3f1aa5845108'; MERGE='0x3e5bb2a724dBe9a6afE04ae7581639367693F51c'; RPC='https://eth.llamarpc.com'
def pad64(n): return hex(n)[2:].rjust(64,'0')
def call(to,data):
    p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
    r=requests.post(RPC,json=p,timeout=(5,10)).json()
    if 'error' in r: raise RuntimeError(r['error'].get('message','err'))
    return r['result']
def owner_ok(t):
    try: call(SLONKS,'0x6352211e'+pad64(t)); return True
    except: return False
def level(t):
    try: return int(call(MERGE,'0x2f17a224'+pad64(t)),16)
    except: return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=int,required=True)
    ap.add_argument('--start-id',type=int,default=0)
    ap.add_argument('--end-id',type=int,default=9999)
    ap.add_argument('--max-candidates',type=int,default=20)
    ap.add_argument('--debug',action='store_true')
    args=ap.parse_args()

    base_level=level(args.base)
    cands=[]; slog=[]
    for tid in range(args.start_id,args.end_id+1):
        if tid==args.base: continue
        if not owner_ok(tid): slog.append({'token_id':tid,'status':'owner_fail','note':''}); continue
        lv=level(tid)
        if lv!=base_level: slog.append({'token_id':tid,'status':'not_same_level','note':f'{lv}!={base_level}'}); continue
        cands.append(tid); slog.append({'token_id':tid,'status':'candidate','note':''})
        if len(cands)>=args.max_candidates: break

    rows=[]
    for d in cands:
        r=run_pair(args.base,d,manual=False,debug=args.debug,headful=False,keep_open=False)
        status='ok' if r['status']=='ok' else 'preview_unavailable'
        rs=r['result_slop'] if r['status']=='ok' else ''
        rows.append({'survivor_id':args.base,'donor_id':d,'base_slop':'','donor_slop':'','result_slop':rs,'gross_delta':'','net_delta':'','status':status,'note':r['note']})
        if status!='ok': slog.append({'token_id':d,'status':status,'note':r['note']})

    rows.sort(key=lambda x: float(x['result_slop']) if x['result_slop']!='' else -1e18, reverse=True)
    with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
        fn=['survivor_id','donor_id','base_slop','donor_slop','result_slop','gross_delta','net_delta','status','note']
        w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(rows)
    with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['token_id','status','note']); w.writeheader(); w.writerows(slog)
    if rows and rows[0]['status']=='ok':
        Path('best_merge.txt').write_text(f"Best merge:\nSurvivor: {args.base}\nDonor: {rows[0]['donor_id']}\nResult slop: {rows[0]['result_slop']}\nStatus: ok\n",encoding='utf-8')
    else:
        Path('best_merge.txt').write_text('Best merge:\nStatus: no valid preview result\n',encoding='utf-8')

if __name__=='__main__': main()
