#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,time,sys,random
from pathlib import Path
import requests

ADDR={'slonks':'0x832233ddb7bcffd0ed53127dd6be3f1aa5845108','model':'0xca116243a2013ed33015c776ee37310b199ee80c','merge':'0x3e5bb2a724dbe9a6afe04ae7581639367693f51c','renderer':'0x103d4ef6e7d87ea27355b402a4ae0875c3fb32a1'}
SEL={'ownerOf':'6352211e','sourceIdFor':'8514e8d5','mergeLevel':'2f17a224','mergeEmbedding':'cc8f00af','sourceEmbedding':'f6a896a1','renderEmbeddingPixels':'0f117f16','renderPixels':'15e0f8f8','diffMask':'8f790c8f','originalPixelsForSource':'a055b5f2'}
RPC_POOL=['https://ethereum.publicnode.com','https://rpc.ankr.com/eth','https://eth.llamarpc.com']

class Rpc:
    def __init__(self,primary,timeout=10,debug=False):
        self.rpcs=[primary]+[x for x in RPC_POOL if x!=primary]; self.i=0; self.fail=0; self.timeout=timeout; self.debug=debug
    @property
    def url(self): return self.rpcs[self.i]
    def switch(self):
        if self.i+1>=len(self.rpcs): return False
        self.i+=1; self.fail=0; print(f'[rpc] switched -> {self.url}',flush=True); return True
    def call(self,to,data):
        p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
        try:
            r=requests.post(self.url,json=p,timeout=(5,self.timeout))
            if r.status_code==429:
                time.sleep(5+random.random()*5); raise RuntimeError('429')
            r.raise_for_status(); j=r.json()
            if 'error' in j: raise RuntimeError(j['error'].get('message','err'))
            self.fail=0; return j['result']
        except Exception as e:
            self.fail+=1
            if self.debug: print('[rpc-error]',self.url,e,flush=True)
            if self.fail>=10 and self.switch():
                return self.call(to,data)
            raise

def pad64(n): return hex(n)[2:].rjust(64,'0')
def b(h): return bytes.fromhex(h[2:])
def to_i8(x): return x-256 if x>=128 else x
def to_u8(x): return x+256 if x<0 else x
def blend(a,bts): return bytes(to_u8(int((to_i8(x)+to_i8(y))/2)) for x,y in zip(a,bts))
def rgba(arr,p): i=p*4; return arr[i:i+4]
def is_diff(mask,p): return ((mask[p//8]>>(7-(p%8)))&1)==1

def token_info(rpc,tid):
    owner=rpc.call(ADDR['slonks'],'0x'+SEL['ownerOf']+pad64(tid))
    src=int(rpc.call(ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid)),16)
    try: lv=int(rpc.call(ADDR['merge'],'0x'+SEL['mergeLevel']+pad64(tid)),16)
    except: lv=0
    if lv==0: emb=b(rpc.call(ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src)))
    else:
        try: emb=b(rpc.call(ADDR['merge'],'0x'+SEL['mergeEmbedding']+pad64(tid)))
        except: emb=b(rpc.call(ADDR['model'],'0x'+SEL['sourceEmbedding']+pad64(src))); lv=0
    return {'token_id':tid,'owner':owner,'source_id':src,'level':lv,'embedding':emb.hex()}

def build_palette(rpc,start,end,out_file):
    print('building palette',flush=True)
    pal={}
    total=max(1,end-start+1)
    for i,tid in enumerate(range(start,end+1),1):
        if i%20==0: print(f'palette progress {i}/{total}',flush=True)
        try:
            src=int(rpc.call(ADDR['slonks'],'0x'+SEL['sourceIdFor']+pad64(tid)),16)
            rp=b(rpc.call(ADDR['renderer'],'0x'+SEL['renderPixels']+pad64(tid)))
            dm=b(rpc.call(ADDR['renderer'],'0x'+SEL['diffMask']+pad64(tid)))
            og=b(rpc.call(ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(src)))
            for p in range(576):
                if not is_diff(dm,p): pal.setdefault(rp[p],rgba(og,p).hex())
            if len(pal)>=222: break
        except: pass
        time.sleep(0.25)
    Path(out_file).write_text(json.dumps({str(k):v for k,v in pal.items()},indent=2))
    print(f'palette completed size={len(pal)}',flush=True)

def simulate_pair(rpc,survivor,donor,palette):
    print('simulating pair',flush=True)
    s=token_info(rpc,survivor); d=token_info(rpc,donor)
    if s['level']!=d['level']: return None,'not_same_level'
    emb=blend(bytes.fromhex(s['embedding']),bytes.fromhex(d['embedding']))
    out=rpc.call(ADDR['model'],'0x'+SEL['renderEmbeddingPixels']+pad64(32)+pad64(len(emb))+emb.hex().ljust(((len(emb)+31)//32)*64,'0'))
    gen=b(out); og=b(rpc.call(ADDR['renderer'],'0x'+SEL['originalPixelsForSource']+pad64(s['source_id'])))
    pal={int(k):bytes.fromhex(v) for k,v in palette.items()}
    miss=0; diff=0
    for p in range(576):
        c=pal.get(gen[p])
        if c is None: miss+=1
        elif c!=rgba(og,p): diff+=1
    rs=diff if miss==0 else diff+miss*0.5
    return {'survivor_id':survivor,'donor_id':donor,'base_source_id':s['source_id'],'donor_source_id':d['source_id'],'level':s['level'],'result_slop':rs,'status':'ok' if miss==0 else 'est','note':f'unknown_palette={miss}'},None

def main():
    print('starting slonks_local_simulator',flush=True)
    ap=argparse.ArgumentParser()
    ap.add_argument('--pair',nargs=2,type=int)
    ap.add_argument('--base',type=int)
    ap.add_argument('--build-palette',action='store_true')
    ap.add_argument('--start-id',type=int,default=0)
    ap.add_argument('--end-id',type=int,default=1000)
    ap.add_argument('--max-candidates',type=int,default=100)
    ap.add_argument('--timeout',type=int,default=10)
    ap.add_argument('--rpc',default='https://ethereum.publicnode.com')
    ap.add_argument('--debug',action='store_true')
    a=ap.parse_args()

    rpc=Rpc(a.rpc,a.timeout,a.debug)
    pal_file='palette.json'
    if a.build_palette:
        build_palette(rpc,a.start_id,a.end_id,pal_file); return

    print('loading palette.json',flush=True)
    if not Path(pal_file).exists():
        print('palette.json missing or incomplete; run --build-palette first or use better RPC',flush=True); sys.exit(1)
    pal=json.loads(Path(pal_file).read_text())
    if len(pal)<180:
        print('palette.json missing or incomplete; run --build-palette first or use better RPC',flush=True); sys.exit(1)

    if a.pair:
        s,d=a.pair; print(f'mode=pair survivor={s} donor={d}',flush=True)
        try:
            r,e=simulate_pair(rpc,s,d,pal)
            if e: print('status=error note=',e,flush=True)
            else: print(f'survivor={s} donor={d} result_slop={r["result_slop"]}',flush=True)
        except Exception as ex:
            print('fatal error:',ex,flush=True); sys.exit(1)
        return

    if a.base is None: raise SystemExit('need --pair or --base')
    cache_file=Path('token_cache.json'); cache=json.loads(cache_file.read_text()) if cache_file.exists() else {}
    logs=[]; results=[]; b=cache.get(str(a.base)) or token_info(rpc,a.base); cache[str(a.base)]=b
    for tid in range(a.start_id,a.end_id+1):
        if tid==a.base: continue
        try:
            info=cache.get(str(tid)) or token_info(rpc,tid); cache[str(tid)]=info
            if info['level']!=b['level']: logs.append({'token_id':tid,'status':'not_same_level','note':''}); continue
            r,e=simulate_pair(rpc,a.base,tid,pal)
            if e: logs.append({'token_id':tid,'status':'error','note':e}); continue
            results.append(r); logs.append({'token_id':tid,'status':'ok','note':r['note']})
            if len(results)>=a.max_candidates: break
        except Exception as ex:
            logs.append({'token_id':tid,'status':'rpc_fail','note':str(ex)})
        if tid%20==0: print(f'scanned {tid-a.start_id+1}, hits={len(results)}',flush=True)
    cache_file.write_text(json.dumps(cache))
    results.sort(key=lambda x:x['result_slop'],reverse=True)
    with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
        fn=['survivor_id','donor_id','base_source_id','donor_source_id','level','result_slop','status','note']
        w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(results)
    with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['token_id','status','note']); w.writeheader(); w.writerows(logs)
    if results:
        b0=results[0]
        Path('best_merge.txt').write_text(f"Best merge:\nSurvivor: {b0['survivor_id']}\nDonor: {b0['donor_id']}\nLevel: {b0['level']}\nResult slop: {b0['result_slop']}\nStatus: {b0['status']}\n",encoding='utf-8')

if __name__=='__main__': main()
