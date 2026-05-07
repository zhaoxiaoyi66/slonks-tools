#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,time
from datetime import datetime
from pathlib import Path
import requests

SLONKS='0x832233ddb7bcffd0ed53127dd6be3f1aa5845108'
MERGE='0x3e5bb2a724dBe9a6afE04ae7581639367693F51c'
RPC='https://eth.llamarpc.com'

def pad64(n:int)->str: return hex(n)[2:].rjust(64,'0')
def eth_call(data,to):
    p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
    r=requests.post(RPC,json=p,timeout=(5,10))
    r.raise_for_status(); j=r.json()
    if 'error' in j: raise RuntimeError(j['error'].get('message','eth_call error'))
    return j['result']

def merge_level(tid:int):
    try:return int(eth_call('0x2f17a224'+pad64(tid),MERGE),16)
    except:return None

def token_uri(tid:int):
    out=eth_call('0xc87b56dd'+pad64(tid),SLONKS)[2:]; ln=int(out[64:128],16); st=128
    return bytes.fromhex(out[st:st+ln*2]).decode(errors='ignore')

def slop(tid:int):
    try:
        uri=token_uri(tid)
        if uri.startswith('data:application/json;base64,'):
            import base64
            j=json.loads(base64.b64decode(uri.split(',',1)[1]).decode())
            for a in j.get('attributes',[]):
                if str(a.get('trait_type','')).strip().lower() in {'slop','pixel diff','diff','difference'}:
                    return float(a.get('value'))
    except: pass
    return None

def fetch_eth_usd():
    try:
        r=requests.get('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd',timeout=(5,10)); r.raise_for_status()
        return float(r.json()['ethereum']['usd'])
    except:return None

def fetch_reservoir():
    u=f'https://api.reservoir.tools/orders/asks/v5?contracts={SLONKS}&status=active&sortBy=price&limit=200'
    r=requests.get(u,timeout=(5,10)); r.raise_for_status(); j=r.json()
    out=[]
    for o in j.get('orders',[]):
        tid=(o.get('criteria',{}).get('data',{}).get('token',{}) or {}).get('tokenId') or (o.get('token') or {}).get('tokenId')
        if tid is None: continue
        out.append({'token_id':int(tid),'price_eth':float(o.get('price',{}).get('amount',{}).get('decimal') or 0),'url':o.get('source',{}).get('url',''),'marketplace':o.get('source',{}).get('name','')})
    return out

def read_listings_csv(path):
    return [{'token_id':int(r['token_id']),'price_eth':float(r['price_eth']),'url':r.get('url',''),'marketplace':r.get('marketplace','csv')} for r in csv.DictReader(Path(path).open('r',encoding='utf-8',newline=''))]

def run_once(args, seen:set):
    eth_usd=fetch_eth_usd()
    try:listings=read_listings_csv(args.listings) if args.listings else fetch_reservoir()
    except Exception as e:
        print(f"[{datetime.now()}] API_FAIL listings fetch failed: {e}")
        return [],[]
    base_level=merge_level(args.base) if args.base is not None else None
    hits=[]
    for x in listings:
        tid=x['token_id']; price=x['price_eth']
        ml=merge_level(tid)
        if args.base is not None and base_level is not None and ml!=base_level: continue
        if args.target_level is not None and ml!=args.target_level: continue
        if args.max_price is not None and price>args.max_price: continue
        s=slop(tid)
        status='ok' if s is not None else 'metadata_fail'
        if s is None: continue
        if args.min_slop is not None and s<args.min_slop: continue
        spe=s/price if price>0 else 0
        be=(price*eth_usd/s) if (eth_usd and s>0) else None
        rec={**x,'slop':s,'ml':ml,'slop_per_eth':spe,'break_even_usd_per_slop':be,'status':status,'opensea':f'https://opensea.io/assets/ethereum/{SLONKS}/{tid}'}
        hits.append(rec)
    hits.sort(key=lambda r:r['slop_per_eth'],reverse=True)
    top=hits[:args.top]
    new=[]
    for r in hits:
        key=f"{r['token_id']}@{r['price_eth']:.8f}"
        if key not in seen:
            seen.add(key); new.append(r)
    ts=datetime.now().strftime('%m/%d/%Y, %I:%M:%S %p')
    print(f"[{ts}] ETH=${eth_usd if eth_usd else 'N/A'} listings={len(listings)} hits={len(hits)} new={len(new)}")
    print('Top hits:')
    for r in top:
        be='unknown' if r['break_even_usd_per_slop'] is None else f"${r['break_even_usd_per_slop']:.4f}"
        print(f"  #{r['token_id']} | {r['price_eth']:.4f} ETH | slop={int(r['slop'])} | 回本={be} | slop/ETH={r['slop_per_eth']:.2f} | ML={r['ml']} | {r['opensea']}")
    if new:
        print('\nNEW ALERTS:')
        for r in new[:args.top]:
            be='unknown' if r['break_even_usd_per_slop'] is None else f"${r['break_even_usd_per_slop']:.4f}"
            print(f"  #{r['token_id']} | {r['price_eth']:.4f} ETH | slop={int(r['slop'])} | 回本={be} | slop/ETH={r['slop_per_eth']:.2f} | ML={r['ml']} | {r['opensea']}")
    return hits,new

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--min-slop',type=float)
    ap.add_argument('--max-price',type=float)
    ap.add_argument('--target-level',type=int)
    ap.add_argument('--top',type=int,default=10)
    ap.add_argument('--interval',type=int,default=60)
    ap.add_argument('--once',action='store_true')
    ap.add_argument('--base',type=int)
    ap.add_argument('--alerts-file',default='seen_alerts.json')
    ap.add_argument('--listings')
    args=ap.parse_args()

    seen=set()
    f=Path(args.alerts_file)
    if f.exists():
        try: seen=set(json.loads(f.read_text(encoding='utf-8')))
        except: seen=set()

    all_hits=[]
    while True:
        hits,_=run_once(args,seen); all_hits=hits
        f.write_text(json.dumps(sorted(seen)),encoding='utf-8')
        with Path('listing_hits.csv').open('w',newline='',encoding='utf-8') as wf:
            fn=['token_id','price_eth','slop','break_even_usd_per_slop','slop_per_eth','ml','status','marketplace','url','opensea']
            w=csv.DictWriter(wf,fieldnames=fn); w.writeheader(); w.writerows(all_hits)
        if args.once: break
        time.sleep(args.interval)

if __name__=='__main__': main()
