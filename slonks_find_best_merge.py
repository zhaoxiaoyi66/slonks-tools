#!/usr/bin/env python3
from __future__ import annotations
import argparse,base64,csv,json,re,time
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

SLONKS='0x832233ddb7bcffd0ed53127dd6be3f1aa5845108'
MERGE='0x3e5bb2a724dBe9a6afE04ae7581639367693F51c'
RPC_POOL=['https://eth.llamarpc.com','https://ethereum.publicnode.com','https://rpc.ankr.com/eth']
BLOCK=re.compile(r"merge|wallet|connect|approve|confirm|transaction",re.I)


def log(msg,debug=False):
    if debug: print(msg,flush=True)

def pad64(n:int)->str: return hex(n)[2:].rjust(64,'0')

class RpcClient:
    def __init__(self, primary:str, timeout:tuple[int,int], debug=False):
        self.rpcs=[primary]+[x for x in RPC_POOL if x!=primary]
        self.i=0; self.timeout=timeout; self.debug=debug; self.fail_streak=0
    @property
    def rpc(self): return self.rpcs[self.i]
    def rotate(self):
        if self.i+1>=len(self.rpcs): return False
        self.i+=1; self.fail_streak=0
        print(f"[rpc] switched to {self.rpc}")
        return True
    def call(self,to,data):
        p={"jsonrpc":"2.0","id":1,"method":"eth_call","params":[{"to":to,"data":data},"latest"]}
        try:
            r=requests.post(self.rpc,json=p,timeout=self.timeout)
            if r.status_code!=200: raise RuntimeError(f"API_FAIL HTTP {r.status_code}: {r.text[:300]}")
            j=r.json()
            if 'error' in j: raise RuntimeError(j['error'].get('message','eth_call error'))
            self.fail_streak=0
            return j.get('result','0x')
        except Exception as e:
            self.fail_streak+=1
            raise RuntimeError(str(e))

def owner_check(rc:RpcClient, tid:int):
    try:
        out=rc.call(SLONKS,'0x6352211e'+pad64(tid)); return 'ok',out
    except Exception as e:
        m=str(e)
        if 'revert' in m.lower() or 'execution reverted' in m.lower(): return 'owner_fail',m
        return 'rpc_timeout',m

def merge_level(rc:RpcClient, tid:int):
    try: return int(rc.call(MERGE,'0x2f17a224'+pad64(tid)),16)
    except: return 0

def token_uri(rc:RpcClient, tid:int):
    out=rc.call(SLONKS,'0xc87b56dd'+pad64(tid)); h=out[2:]; ln=int(h[64:128],16); st=128
    return bytes.fromhex(h[st:st+ln*2]).decode(errors='ignore')

def slop_from_tokenuri(rc:RpcClient, tid:int):
    try:
        uri=token_uri(rc,tid)
        if uri.startswith('data:application/json;base64,'):
            j=json.loads(base64.b64decode(uri.split(',',1)[1]).decode())
            for a in j.get('attributes',[]):
                if str(a.get('trait_type','')).strip().lower() in {'slop','pixel diff','diff','difference'}:
                    return float(a.get('value'))
        return None
    except Exception:
        return None

def safe_click_preview(page, base:int, donor:int, debug=False):
    danger=re.compile(r"merge|connect|wallet|approve|confirm|transaction|mint|burn",re.I)
    okpat=re.compile(r"preview|simulate",re.I)
    buttons=page.locator('button')
    texts=[]; safe=[]
    for i in range(buttons.count()):
        b=buttons.nth(i)
        t=(b.inner_text(timeout=800) or '').strip()
        texts.append(t)
        if okpat.search(t) and not danger.search(t):
            safe.append((b,t))
    if debug:
        print('[debug] all button texts:')
        for t in texts: print('  -',t)
        print('[debug] safe preview candidates:', [t for _,t in safe])
    if not safe:
        raise RuntimeError('preview_button_not_found')
    for b,t in safe:
        if not b.is_visible() or not b.is_enabled():
            continue
        b.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        page.evaluate("el=>el.scrollIntoView({block:'center'})", b)
        page.wait_for_timeout(300)
        try:
            b.click(timeout=3000)
            if debug: print(f"[debug] clicked preview button: {t}")
            return t
        except Exception:
            shot_path=shot(page,f'preview_click_intercept_{base}_{donor}')
            if debug: print(f'[debug] click intercept, screenshot={shot_path}')
            page.mouse.wheel(0,400); page.wait_for_timeout(200)
            b.click(force=True,timeout=3000)
            if debug: print(f"[debug] force clicked preview button: {t}")
            return t
    raise RuntimeError('preview_button_not_found')

def shot(page,name):
    d=Path('screenshots'); d.mkdir(exist_ok=True)
    path=d/f"{name}.png"; page.screenshot(path=str(path),full_page=True)
    return str(path)

def select_tokens(page, base, donor):
    ins=page.locator('input')
    if ins.count()<2: return False,False,'page structure mismatch: inputs<2'
    ins.nth(0).fill(str(base)); ins.nth(1).fill(str(donor))
    body=page.inner_text('body')
    return (str(base) in body),(str(donor) in body),'ok'

def read_result_flexible(page, timeout_s=15):
    end=time.time()+timeout_s
    while time.time()<end:
        patterns=[r"text=/result\s*slop/i",r"text=/slop/i",r"text=/result/i"]
        for pat in patterns:
            loc=page.locator(pat)
            if loc.count()>0:
                txt=loc.first.inner_text(timeout=1000)
                m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
                if m: return float(m[-1]),f'from {pat}'
        txt=page.inner_text('body')
        if 'slop' in txt.lower() or 'result' in txt.lower():
            m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
            if m: return float(m[-1]),'from body numeric'
        time.sleep(0.5)
    raise RuntimeError('result_not_found')
def load_candidates_csv(path:Path):
    out=[]
    for r in csv.DictReader(path.open('r',encoding='utf-8',newline='')):
        out.append({'token_id':int(r['token_id']),'price_eth':r.get('price_eth',''),'url':r.get('url',''),'marketplace':r.get('marketplace','')})
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=int,required=True)
    ap.add_argument('--rpc',default='https://eth.llamarpc.com')
    ap.add_argument('--timeout',type=int,default=10)
    ap.add_argument('--max-candidates',type=int,default=20)
    ap.add_argument('--start-id',type=int,default=0)
    ap.add_argument('--end-id',type=int,default=9999)
    ap.add_argument('--full-scan',action='store_true')
    ap.add_argument('--candidates')
    ap.add_argument('--allow-reverse',action='store_true')
    ap.add_argument('--debug',action='store_true')
    ap.add_argument('--headful',action='store_true')
    ap.add_argument('--keep-open',action='store_true')
    args=ap.parse_args()

    rc=RpcClient(args.rpc,(5,args.timeout),args.debug)
    print(f"[debug] checking base token id={args.base}")
    print(f"[debug] using RPC={rc.rpc}")
    st,detail=owner_check(rc,args.base)
    print(f"[debug] ownerOf result status={st} detail={detail}")
    if st=='owner_fail': raise SystemExit('OWNER_FAIL = token 不存在 / burned / 未 mint')
    if st!='ok': raise SystemExit(f'API_FAIL = API 请求失败: {detail}')

    base_level=merge_level(rc,args.base)
    base_slop=slop_from_tokenuri(rc,args.base)
    if base_slop is None: print('METADATA_FAIL base slop read failed; preview-only mode')

    scan_rows=[]; candidates=[]; rpc_errors=0; last_progress=time.time(); valid=same=0
    if args.candidates:
        candidates=load_candidates_csv(Path(args.candidates))
        scan_rows.append({'token_id':args.base,'status':'info','note':f'using candidates csv: {args.candidates}'})
    else:
        for tid in range(args.start_id,args.end_id+1):
            if tid==args.base: continue
            if time.time()-last_progress>60:
                print('scan timed out, try another RPC or smaller range'); break
            st,detail=owner_check(rc,tid)
            if st=='rpc_timeout':
                rpc_errors+=1; scan_rows.append({'token_id':tid,'status':'rpc_timeout','note':detail})
            elif st=='owner_fail':
                scan_rows.append({'token_id':tid,'status':'owner_fail','note':'token may be burned/unminted'})
            else:
                valid+=1
                lv=merge_level(rc,tid)
                if lv==base_level:
                    same+=1
                    ds=slop_from_tokenuri(rc,tid)
                    candidates.append({'token_id':tid,'price_eth':'','url':'','marketplace':'','donor_slop':ds})
                    scan_rows.append({'token_id':tid,'status':'same_level','note':f'level={lv}'})
                    last_progress=time.time()
                    if (not args.full_scan) and len(candidates)>=args.max_candidates: break
                else:
                    scan_rows.append({'token_id':tid,'status':'skip_level','note':f'level {lv} != {base_level}'})
            if tid%10==0:
                print(f"scanned {tid-args.start_id+1} / valid {valid} / same_level {same} / rpc_errors {rpc_errors}")
            if rc.fail_streak>=20 and not rc.rotate():
                print('all RPC endpoints failed; stopping scan'); break

    results=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=not args.headful)
        page=browser.new_page(); page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=90000)
        for c in candidates:
            donor=c['token_id']; log(f"[preview] donor={donor}",True)
            ss_before=shot(page,f'before_select_{args.base}_{donor}')
            sel_s,sel_d,sel_note=select_tokens(page,args.base,donor)
            ss_after_sel=shot(page,f'after_select_{args.base}_{donor}')
            print(f"  survivor_selected={sel_s} donor_selected={sel_d}")
            if not (sel_s and sel_d):
                note='selection_failed: base/donor not both visible'
                results.append({'survivor_id':args.base,'donor_id':donor,'base_slop':base_slop,'donor_slop':c.get('donor_slop'),'result_slop':'','gross_delta':'','net_delta':'','price_eth':c.get('price_eth',''),'gross_slop_per_eth':'','net_slop_per_eth':'','status':'selection_failed','note':note})
                scan_rows.append({'token_id':donor,'status':'selection_failed','note':note,'screenshot_path':ss_after_sel})
                continue
            try:
                btn=safe_preview_btn(page)
                if not btn.is_enabled():
                    raise RuntimeError('preview_unavailable')
                btn.click(timeout=3000)
                print('  preview_clicked=True')
                ss_after_preview=shot(page,f'after_preview_{args.base}_{donor}')
                rs,src=read_result_flexible(page,20)
                print(f'  result_found=True result_slop={rs} source={src}')
                ds=c.get('donor_slop')
                gd=(rs-base_slop) if base_slop is not None else ''
                nd=(rs-base_slop-ds) if (base_slop is not None and ds is not None) else ''
                pe=float(c['price_eth']) if str(c.get('price_eth','')).strip() else None
                gpe=(gd/pe) if isinstance(gd,(int,float)) and pe and pe>0 else ''
                npe=(nd/pe) if isinstance(nd,(int,float)) and pe and pe>0 else ''
                results.append({'survivor_id':args.base,'donor_id':donor,'base_slop':base_slop,'donor_slop':ds,'result_slop':rs,'gross_delta':gd,'net_delta':nd,'price_eth':c.get('price_eth',''),'gross_slop_per_eth':gpe,'net_slop_per_eth':npe,'status':'ok','note':src})
                scan_rows.append({'token_id':donor,'status':'preview_ok','note':src,'screenshot_path':ss_after_preview})
            except Exception as e:
                err=str(e)
                status='result_not_found' if 'result_not_found' in err else ('preview_unavailable' if 'preview_unavailable' in err else 'preview_error')
                print(f'  preview_clicked=False/failed reason={err}')
                ss_err=shot(page,f'preview_error_{args.base}_{donor}')
                results.append({'survivor_id':args.base,'donor_id':donor,'base_slop':base_slop,'donor_slop':c.get('donor_slop'),'result_slop':'','gross_delta':'','net_delta':'','price_eth':c.get('price_eth',''),'gross_slop_per_eth':'','net_slop_per_eth':'','status':status,'note':err})
                scan_rows.append({'token_id':donor,'status':status,'note':err,'screenshot_path':ss_err})
        if args.keep_open: input('Press Enter to close browser...')
        browser.close()

    def rk(r):
        n=r['net_delta'] if isinstance(r['net_delta'],(int,float)) else -1e18
        g=r['gross_delta'] if isinstance(r['gross_delta'],(int,float)) else -1e18
        return (n,g,r['result_slop'] if isinstance(r['result_slop'],(int,float)) else -1e18)
    results.sort(key=rk,reverse=True)

    with Path('ranked_results.csv').open('w',newline='',encoding='utf-8') as f:
        fn=['survivor_id','donor_id','base_slop','donor_slop','result_slop','gross_delta','net_delta','price_eth','gross_slop_per_eth','net_slop_per_eth','status','note']
        w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(results)
    with Path('scan_log.csv').open('w',newline='',encoding='utf-8') as f:
        for r in scan_rows:
            if 'screenshot_path' not in r:
                r['screenshot_path']=''
        w=csv.DictWriter(f,fieldnames=['token_id','status','note','screenshot_path'])
        w.writeheader()
        w.writerows(scan_rows)

    valid=[r for r in results if r['status']=='ok']
    if not valid:
        print('No valid preview results. Check scan_log.csv and ranked_results.csv')
        Path('best_merge.txt').write_text('No valid result\n',encoding='utf-8')
        return
    top=valid[0]
    Path('best_merge.txt').write_text(
        f"Survivor: {top['survivor_id']}\nDonor: {top['donor_id']}\nBase slop: {top['base_slop']}\nDonor slop: {top['donor_slop']}\nResult slop: {top['result_slop']}\nGross delta: {top['gross_delta']}\nNet delta: {top['net_delta']}\nGross slop/ETH: {top['gross_slop_per_eth']}\nNet slop/ETH: {top['net_slop_per_eth']}\n",encoding='utf-8')
    print('Top10:')
    for i,r in enumerate(valid[:10],1): print(i,r)

if __name__=='__main__': main()
