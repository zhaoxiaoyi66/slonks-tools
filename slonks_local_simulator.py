#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,time,sys
from pathlib import Path
import requests

ADDR={'slonks':'0x832233ddb7bcffd0ed53127dd6be3f1aa5845108','model':'0xca116243a2013ed33015c776ee37310b199ee80c','merge':'0x3e5bb2a724dbe9a6afe04ae7581639367693f51c','renderer':'0x103d4ef6e7d87ea27355b402a4ae0875c3fb32a1'}
SEL={'ownerOf':'6352211e','sourceIdFor':'8514e8d5','mergeLevel':'2f17a224','mergeEmbedding':'cc8f00af','sourceEmbedding':'f6a896a1','renderEmbeddingPixels':'0f117f16','renderPixels':'15e0f8f8','diffMask':'8f790c8f','originalPixelsForSource':'a055b5f2'}

LAST=time.time()
def touch(msg=''):
    global LAST; LAST=time.time()
    if msg: print(msg, flush=True)
def watchdog(sec=30):
    if time.time()-LAST>sec: raise TimeoutError('operation timed out')

def pad64(n): return hex(n)[2:].rjust(64,'0')
def call(rpc,to,data,timeout,debug=False):
    try:
        watchdog();
        p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
        r=requests.post(rpc,json=p,timeout=(5,timeout)); r.raise_for_status(); j=r.json()
        if 'error' in j: raise RuntimeError(j['error'].get('message','err'))
        return j['result']
    except Exception as e:
        if debug: print(f'[rpc-error] to={to} data={data[:10]}... err={e}', flush=True)
        raise

def b(hexs): return bytes.fromhex(hexs[2:])
def to_i8(x): return x-256 if x>=128 else x
def to_u8(x): return x+256 if x<0 else x
def blend(a,bts): return bytes(to_u8(int((to_i8(x)+to_i8(y))/2)) for x,y in zip(a,bts))
def px_rgba(arr,p): i=p*4; return arr[i:i+4]
def is_diff(mask,p): return ((mask[p//8]>>(7-(p%8)))&1)==1

def token_info(rpc,tid,timeout,debug=False):
    touch('checking survivor/donor ownerOf' if debug else '')
    owner=call(rpc,ADDR['slonks'],'0x'+SEL['ownerOf']+pad64(tid),timeout,debug)
    touch('reading sourceId')
    src=int(call(rpc,ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid),timeout,debug),16)
    touch('reading merge level')
    try: lv=int(call(rpc,ADDR['merge'],'0x'+SEL['mergeLevel']+pad64(tid),timeout,debug),16)
    except: lv=0
    touch('reading embedding')
    if lv==0: emb=b(call(rpc,ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src),timeout,debug))
    else:
        try: emb=b(call(rpc,ADDR['merge'],'0x'+SEL['mergeEmbedding']+pad64(tid),timeout,debug))
        except: emb=b(call(rpc,ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src),timeout,debug)); lv=0
    return {'token_id':tid,'owner':owner,'source_id':src,'level':lv,'embedding':emb.hex()}

def build_palette(rpc,timeout,start,end,cache,debug=False):
    print('palette.json not found, building palette...', flush=True)
    pal={int(k):bytes.fromhex(v) for k,v in cache.items()}
    total=max(1,end-start+1)
    for i,tid in enumerate(range(start,end+1),1):
        watchdog()
        if i%20==0: print(f'building palette progress {i}/{total}', flush=True)
        try:
            src=int(call(rpc,ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid),timeout,debug),16)
            rp=b(call(rpc,ADDR['renderer'],'0x'+SEL['renderPixels']+pad64(tid),timeout,debug))
            dm=b(call(rpc,ADDR['renderer'],'0x'+SEL['diffMask']+pad64(tid),timeout,debug))
            og=b(call(rpc,ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(src),timeout,debug))
            for p in range(576):
                if not is_diff(dm,p): pal.setdefault(rp[p],px_rgba(og,p))
            if len(pal)>=222: break
        except Exception as e:
            if debug: print('[palette-skip]',tid,e,flush=True)
    return {str(k):v.hex() for k,v in pal.items()}

def simulate_pair(rpc,timeout,survivor,donor,palette,debug=False):
    touch('checking survivor ownerOf'); s=token_info(rpc,survivor,timeout,debug)
    touch('checking donor ownerOf'); d=token_info(rpc,donor,timeout,debug)
    if s['level']!=d['level']: return None,'not_same_level'
    touch('rendering blended embedding')
    emb=blend(bytes.fromhex(s['embedding']),bytes.fromhex(d['embedding']))
    out=call(rpc,ADDR['model'],'0x'+SEL['renderEmbeddingPixels']+pad64(32)+pad64(len(emb))+emb.hex().ljust(((len(emb)+31)//32)*64,'0'),timeout,debug)
    gen=b(out)
    og=b(call(rpc,ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(s['source_id']),timeout,debug))
    touch('calculating slop')
    pal={int(k):bytes.fromhex(v) for k,v in palette.items()}
    miss=0; diff=0
    for p in range(576):
        rgba=pal.get(gen[p])
        if rgba is None: miss+=1
        elif rgba!=px_rgba(og,p): diff+=1
    result=diff if miss==0 else diff+miss*0.5
    return {'survivor_id':survivor,'donor_id':donor,'base_source_id':s['source_id'],'donor_source_id':d['source_id'],'level':s['level'],'result_slop':result,'status':'ok' if miss==0 else 'est','note':f'unknown_palette={miss}'},None

def main():
    print('starting slonks_local_simulator', flush=True)
    ap=argparse.ArgumentParser()
    ap.add_argument('--pair',nargs=2,type=int)
    ap.add_argument('--base',type=int)
    ap.add_argument('--start-id',type=int,default=0)
    ap.add_argument('--end-id',type=int,default=10000)
    ap.add_argument('--max-candidates',type=int,default=100)
    ap.add_argument('--timeout',type=int,default=10)
    ap.add_argument('--rpc',default='https://eth.llamarpc.com')
    ap.add_argument('--debug',action='store_true')
    a=ap.parse_args()

    if a.pair: print(f'mode=pair survivor={a.pair[0]} donor={a.pair[1]}', flush=True)
    try:
        pal_file=Path('palette.json'); tok_file=Path('token_cache.json')
        touch('building/loading palette')
        pal=json.loads(pal_file.read_text()) if pal_file.exists() else {}
        if len(pal)<180:
            pal=build_palette(a.rpc,a.timeout,a.start_id,min(a.end_id,a.start_id+2000),pal,a.debug)
            pal_file.write_text(json.dumps(pal,indent=2))

        cache=json.loads(tok_file.read_text()) if tok_file.exists() else {}
        logs=[]; results=[]
        if a.pair:
            s,d=a.pair
            res,err=simulate_pair(a.rpc,a.timeout,s,d,pal,a.debug)
            touch('writing result')
            if err: print('status=error note=',err, flush=True)
            else: print(f"survivor={s} donor={d} result_slop={res['result_slop']}", flush=True)
            return

        if a.base is None: raise SystemExit('need --base or --pair')
        b=cache.get(str(a.base)) or token_info(a.rpc,a.base,a.timeout,a.debug); cache[str(a.base)]=b
        for tid in range(a.start_id,a.end_id+1):
            watchdog()
            if tid==a.base: continue
            try:
                info=cache.get(str(tid)) or token_info(a.rpc,tid,a.timeout,a.debug); cache[str(tid)]=info
                if info['level']!=b['level']: logs.append({'token_id':tid,'status':'not_same_level','note':''}); continue
                res,err=simulate_pair(a.rpc,a.timeout,a.base,tid,pal,a.debug)
                if err: logs.append({'token_id':tid,'status':'error','note':err}); continue
                results.append(res); logs.append({'token_id':tid,'status':'ok','note':res['note']})
                if len(results)>=a.max_candidates: break
            except Exception as e:
                print('[token-error]',tid,e,flush=True)
                logs.append({'token_id':tid,'status':'rpc_fail','note':str(e)})
            if tid%20==0: print(f'scanned {tid-a.start_id+1}, hits={len(results)}', flush=True)
        tok_file.write_text(json.dumps(cache))
        results.sort(key=lambda r:r['result_slop'],reverse=True)
        with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
            fn=['survivor_id','donor_id','base_source_id','donor_source_id','level','result_slop','status','note']
            w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(results)
        with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=['token_id','status','note']); w.writeheader(); w.writerows(logs)
        if results:
            best=results[0]
            Path('best_merge.txt').write_text(f"Best merge:\nSurvivor: {best['survivor_id']}\nDonor: {best['donor_id']}\nLevel: {best['level']}\nResult slop: {best['result_slop']}\nStatus: {best['status']}\n",encoding='utf-8')
    except TimeoutError as e:
        print(str(e), flush=True); sys.exit(1)
    except Exception as e:
        print('fatal error:',e, flush=True); sys.exit(1)

if __name__=='__main__': main()
