#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,csv,json,re,time,sys
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

RPC='https://eth.llamarpc.com'
SLONKS='0x832233ddb7bcffd0ed53127dd6be3f1aa5845108'
MERGE='0x3e5bb2a724dBe9a6afE04ae7581639367693F51c'
BLOCK=re.compile(r"merge|wallet|connect|approve|confirm|transaction",re.I)


def keccak4(sig:str)->str:
    import hashlib
    return hashlib.sha3_256(sig.encode()).hexdigest()[:8]

def pad64(n:int)->str: return hex(n)[2:].rjust(64,'0')

def eth_call(to,data):
    p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
    try:
        resp=requests.post(RPC,json=p,timeout=20)
    except Exception as e:
        raise RuntimeError(f"API_FAIL network: {e}")
    if resp.status_code!=200:
        raise RuntimeError(f"API_FAIL HTTP {resp.status_code}: {resp.text[:300]}")
    try:r=resp.json()
    except Exception:
        raise RuntimeError(f"API_FAIL non-json: {resp.text[:300]}")
    if 'error' in r: raise RuntimeError(r['error'].get('message','eth_call error'))
    return r.get('result','0x')

def owner_check(tid:int):
    try:
        out=eth_call(SLONKS,'0x6352211e'+pad64(tid))
        return True,out,''
    except Exception as e:
        msg=str(e)
        if 'execution reverted' in msg or 'revert' in msg or 'OWNER_FAIL' in msg:
            return False,'',f'OWNER_FAIL {msg}'
        return None,'',f'API_FAIL {msg}'

def merge_level(tid:int)->int:
    try:
        out=eth_call(MERGE,'0x2f17a224'+pad64(tid))
        return int(out,16)
    except:
        return 0

def token_uri(tid:int)->str:
    out=eth_call(SLONKS,'0xc87b56dd'+pad64(tid))
    h=out[2:]
    ln=int(h[64:128],16); st=128
    return bytes.fromhex(h[st:st+ln*2]).decode(errors='ignore')

def slop_from_tokenuri(tid:int):
    try:
        uri=token_uri(tid)
        if uri.startswith('data:application/json;base64,'):
            j=json.loads(base64.b64decode(uri.split(',',1)[1]).decode())
            for a in j.get('attributes',[]):
                if str(a.get('trait_type','')).strip().lower() in {'slop','pixel diff','diff','difference'}:
                    return float(a.get('value'))
    except: pass
    return None

def safe_preview_btn(page):
    opts=[page.get_by_text('Preview',exact=False),page.locator("button:has-text('Preview')"),page.locator("button:has-text('Simulate')"),page.get_by_role('button',name=re.compile(r'preview|simulate|no\s*-?\s*gas',re.I))]
    for o in opts:
        if o.count()==0: continue
        for i in range(o.count()):
            b=o.nth(i); t=(b.inner_text(timeout=800) or '').strip()
            if not BLOCK.search(t): return b
    raise RuntimeError('preview button not found')

def fill_pair(page,survivor,donor):
    inputs=page.locator('input')
    if inputs.count()<2: raise RuntimeError('not enough inputs for keep/burn')
    inputs.nth(0).fill(str(survivor)); inputs.nth(1).fill(str(donor))

def read_result(page):
    end=time.time()+10
    while time.time()<end:
        for loc in [page.locator(r"text=/result\s*slop/i"),page.locator(r"text=/slop/i")]:
            if loc.count()==0: continue
            txt=loc.first.inner_text(timeout=1200)
            m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
            if m: return float(m[-1])
        time.sleep(0.5)
    raise RuntimeError('result slop not found')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=int,required=True)
    ap.add_argument('--max-candidates',type=int,default=100)
    ap.add_argument('--full-scan',action='store_true')
    ap.add_argument('--headful',action='store_true')
    ap.add_argument('--keep-open',action='store_true')
    args=ap.parse_args()

    print(f'[debug] checking base token id={args.base}')
    print(f'[debug] RPC URL={RPC}')
    ok,owner_raw,err=owner_check(args.base)
    print(f'[debug] ownerOf raw={owner_raw}')
    if ok is False: raise SystemExit(f'OWNER_FAIL = token 不存在 / burned / 未 mint; detail: {err}')
    if ok is None: raise SystemExit(f'API_FAIL = API 请求失败; detail: {err}')
    base_level=merge_level(args.base)
    base_slop=slop_from_tokenuri(args.base)
    if base_slop is None: print('METADATA_FAIL base slop read failed from tokenURI; continue with preview-only mode')

    scan_rows=[]; cands=[]
    for tid in range(10000):
        if tid==args.base: continue
        ok2,_,err2=owner_check(tid)
        if ok2 is False:
            scan_rows.append({'token_id':tid,'status':'skip','note':'OWNER_FAIL token not exists/burned'}); continue
        if ok2 is None:
            scan_rows.append({'token_id':tid,'status':'skip','note':f'API_FAIL {err2}'}); continue
        lv=merge_level(tid)
        if lv!=base_level:
            scan_rows.append({'token_id':tid,'status':'skip','note':f'level {lv} != {base_level}'}); continue
        ds=slop_from_tokenuri(tid)
        if ds is None:
            scan_rows.append({'token_id':tid,'status':'skip','note':'donor slop read failed'}); continue
        cands.append((tid,ds)); scan_rows.append({'token_id':tid,'status':'candidate','note':'ok'})
        if not args.full_scan and len(cands)>=args.max_candidates: break

    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=not args.headful)
        page=browser.new_page(); page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=90000)
        for tid,donor_slop in cands:
            try:
                fill_pair(page,args.base,tid)
                safe_preview_btn(page).click(timeout=3000)
                rs=read_result(page)
                gross=(rs-base_slop) if base_slop is not None else ''
                net=(rs-base_slop-donor_slop) if (base_slop is not None and donor_slop is not None) else ''
                results.append({'base_id':args.base,'donor_id':tid,'base_slop':base_slop,'donor_slop':donor_slop,'result_slop':rs,'gross_delta':gross,'net_delta':net})
                scan_rows.append({'token_id':tid,'status':'preview_ok','note':f'result_slop={rs}'})
            except Exception as e:
                scan_rows.append({'token_id':tid,'status':'error','note':'PREVIEW_FAIL '+str(e)})
        if args.keep_open:
            input('Press Enter to close browser...')
        browser.close()

    def k(r):
        n=r['net_delta'] if isinstance(r['net_delta'],(int,float)) else -1e18
        g=r['gross_delta'] if isinstance(r['gross_delta'],(int,float)) else -1e18
        return (n,g,r['result_slop'])
    results.sort(key=k,reverse=True)
    with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['base_id','donor_id','base_slop','donor_slop','result_slop','gross_delta','net_delta']);w.writeheader();w.writerows(results)
    with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['token_id','status','note']);w.writeheader();w.writerows(scan_rows)
    if results:
        top=results[0]
        Path('best_merge.txt').write_text(
            f"base survivor id: {top['base_id']}\n"
            f"donor id: {top['donor_id']}\n"
            f"base slop: {top['base_slop']}\n"
            f"donor slop: {top['donor_slop']}\n"
            f"result slop: {top['result_slop']}\n"
            f"gross delta: {top['gross_delta']}\n"
            f"net delta: {top['net_delta']}\n",encoding='utf-8')
        print('Top10:')
        for i,r in enumerate(results[:10],1): print(i,r)

if __name__=='__main__': main()
