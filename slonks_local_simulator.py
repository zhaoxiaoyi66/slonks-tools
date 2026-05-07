#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,requests
from pathlib import Path

ADDR={
'slonks':'0x832233ddb7bcffd0ed53127dd6be3f1aa5845108',
'model':'0xca116243a2013ed33015c776ee37310b199ee80c',
'merge':'0x3e5bb2a724dbe9a6afe04ae7581639367693f51c',
'renderer':'0x103d4ef6e7d87ea27355b402a4ae0875c3fb32a1',
}
SEL={'ownerOf':'6352211e','sourceIdFor':'8514e8d5','mergeLevel':'2f17a224','mergeEmbedding':'cc8f00af','sourceEmbedding':'f6a896a1','renderEmbeddingPixels':'0f117f16','renderPixels':'15e0f8f8','diffMask':'8f790c8f','originalPixelsForSource':'a055b5f2'}

def pad64(n): return hex(n)[2:].rjust(64,'0')
def call(rpc,to,data,timeout):
    p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
    r=requests.post(rpc,json=p,timeout=(5,timeout)); r.raise_for_status(); j=r.json()
    if 'error' in j: raise RuntimeError(j['error'].get('message','err'))
    return j['result']
def b(hexs): return bytes.fromhex(hexs[2:])
def to_i8(x): return x-256 if x>=128 else x
def to_u8(x): return x+256 if x<0 else x
def blend(a,bts): return bytes(to_u8(int((to_i8(x)+to_i8(y))/2)) for x,y in zip(a,bts))
def px_rgba(arr,p): i=p*4; return arr[i:i+4]
def is_diff(mask,p): return ((mask[p//8]>>(7-(p%8)))&1)==1

def token_info(rpc,tid,timeout):
    owner=call(rpc,ADDR['slonks'],'0x'+SEL['ownerOf']+pad64(tid),timeout)
    src=int(call(rpc,ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid),timeout),16)
    try: lv=int(call(rpc,ADDR['merge'],'0x'+SEL['mergeLevel']+pad64(tid),timeout),16)
    except: lv=0
    if lv==0: emb=b(call(rpc,ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src),timeout))
    else:
        try: emb=b(call(rpc,ADDR['merge'],'0x'+SEL['mergeEmbedding']+pad64(tid),timeout))
        except: emb=b(call(rpc,ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src),timeout)); lv=0
    return {'token_id':tid,'owner':owner,'source_id':src,'level':lv,'embedding':emb.hex()}

def build_palette(rpc,timeout,start,end,cache):
    pal={int(k):bytes.fromhex(v) for k,v in cache.items()}
    for tid in range(start,end+1):
        try:
            src=int(call(rpc,ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid),timeout),16)
            rp=b(call(rpc,ADDR['renderer'],'0x'+SEL['renderPixels']+pad64(tid),timeout))
            dm=b(call(rpc,ADDR['renderer'],'0x'+SEL['diffMask']+pad64(tid),timeout))
            og=b(call(rpc,ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(src),timeout))
            for p in range(576):
                if not is_diff(dm,p):
                    idx=rp[p]
                    if idx not in pal: pal[idx]=px_rgba(og,p)
            if len(pal)>=222: break
        except: pass
    return {str(k):v.hex() for k,v in pal.items()}

def simulate_pair(rpc,timeout,survivor,donor,palette):
    s=token_info(rpc,survivor,timeout); d=token_info(rpc,donor,timeout)
    if s['level']!=d['level']: return None,'not_same_level'
    emb=blend(bytes.fromhex(s['embedding']),bytes.fromhex(d['embedding']))
    out=call(rpc,ADDR['model'],'0x'+SEL['renderEmbeddingPixels']+pad64(32)+pad64(len(emb))+emb.hex().ljust(((len(emb)+31)//32)*64,'0'),timeout)
    gen=b(out)
    og=b(call(rpc,ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(s['source_id']),timeout))
    pal={int(k):bytes.fromhex(v) for k,v in palette.items()}
    miss=0; diff=0
    for p in range(576):
        idx=gen[p]
        rgba=pal.get(idx)
        if rgba is None: miss+=1; continue
        if rgba!=px_rgba(og,p): diff+=1
    result=diff if miss==0 else diff+miss*0.5
    return {'survivor_id':survivor,'donor_id':donor,'base_source_id':s['source_id'],'donor_source_id':d['source_id'],'level':s['level'],'result_slop':result,'status':'ok' if miss==0 else 'est','note':f'unknown_palette={miss}'},None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pair',nargs=2,type=int)
    ap.add_argument('--base',type=int)
    ap.add_argument('--start-id',type=int,default=0)
    ap.add_argument('--end-id',type=int,default=10000)
    ap.add_argument('--max-candidates',type=int,default=100)
    ap.add_argument('--timeout',type=int,default=10)
    ap.add_argument('--rpc',default='https://eth.llamarpc.com')
    args=ap.parse_args()

    pal_file=Path('palette.json'); tok_cache_file=Path('token_cache.json')
    palette=json.loads(pal_file.read_text()) if pal_file.exists() else {}
    if len(palette)<180:
        palette=build_palette(args.rpc,args.timeout,args.start_id,min(args.end_id,args.start_id+2000),palette)
        pal_file.write_text(json.dumps(palette,indent=2))

    token_cache=json.loads(tok_cache_file.read_text()) if tok_cache_file.exists() else {}
    logs=[]; results=[]

    if args.pair:
        s,d=args.pair
        res,err=simulate_pair(args.rpc,args.timeout,s,d,palette)
        if err: print('status=error note=',err)
        else: print(f"survivor={s} donor={d} result_slop={res['result_slop']}")
        return

    base=args.base
    if base is None: raise SystemExit('need --base or --pair')
    if str(base) in token_cache: b=token_cache[str(base)]
    else:
        b=token_info(args.rpc,base,args.timeout); token_cache[str(base)]=b
    for tid in range(args.start_id,args.end_id+1):
        if tid==base: continue
        try:
            info=token_cache.get(str(tid)) or token_info(args.rpc,tid,args.timeout); token_cache[str(tid)]=info
            if info['level']!=b['level']:
                logs.append({'token_id':tid,'status':'not_same_level','note':''}); continue
            res,err=simulate_pair(args.rpc,args.timeout,base,tid,palette)
            if err: logs.append({'token_id':tid,'status':'error','note':err}); continue
            results.append(res); logs.append({'token_id':tid,'status':'ok','note':res['note']})
            if len(results)>=args.max_candidates: break
        except Exception as e:
            logs.append({'token_id':tid,'status':'rpc_fail','note':str(e)})
        if tid%20==0: print(f'scanned {tid-args.start_id+1}, hits={len(results)}')

    tok_cache_file.write_text(json.dumps(token_cache))
    results.sort(key=lambda r:(r['result_slop']),reverse=True)
    with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
        fn=['survivor_id','donor_id','base_source_id','donor_source_id','level','result_slop','status','note']
        w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(results)
    with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['token_id','status','note']); w.writeheader(); w.writerows(logs)
    if results:
        best=results[0]
        Path('best_merge.txt').write_text(f"Best merge:\nSurvivor: {best['survivor_id']}\nDonor: {best['donor_id']}\nLevel: {best['level']}\nResult slop: {best['result_slop']}\nStatus: {best['status']}\n",encoding='utf-8')

if __name__=='__main__': main()
