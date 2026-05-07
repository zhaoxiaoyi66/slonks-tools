#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,re,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BLOCK=re.compile(r"merge|wallet|connect|approve|confirm|transaction",re.I)


def log(msg,debug=True):
    if debug: print(msg, flush=True)

def read_candidates(path:Path):
    out=[]
    with path.open('r',encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            out.append({"token_id":int(r.get('token_id','0') or 0),"price_eth":r.get('price_eth',''),"url":r.get('url',''),"marketplace":r.get('marketplace','')})
    return out

def screenshot(page, d:Path, name:str):
    d.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(d/f"{name}.png"),full_page=True)

def pick_input(page, key:str, nth:int):
    options=[
        page.get_by_placeholder(key, exact=False),
        page.get_by_label(key, exact=False),
        page.locator(f"input[placeholder*='{key}' i]"),
        page.locator("input")
    ]
    for loc in options:
        if loc.count()>0:
            return loc.nth(min(nth,loc.count()-1))
    raise RuntimeError(f"input not found: {key}")

def safe_preview_button(page):
    options=[
        page.get_by_text("Preview", exact=False),
        page.locator("button:has-text('Preview')"),
        page.locator("button:has-text('Simulate')"),
        page.get_by_role("button", name=re.compile(r"preview|simulate|no\s*-?\s*gas",re.I)),
    ]
    for loc in options:
        if loc.count()==0: continue
        for i in range(loc.count()):
            b=loc.nth(i)
            txt=(b.inner_text(timeout=1000) or '').strip()
            if not BLOCK.search(txt):
                return b
    raise RuntimeError("safe preview/simulate button not found")

def read_result_slop(page, timeout_ms=10000):
    deadline=time.time()+timeout_ms/1000
    while time.time()<deadline:
        for loc in [page.locator(r"text=/result\s*slop/i"), page.locator(r"text=/slop/i")]:
            if loc.count()==0: continue
            txt=loc.first.inner_text(timeout=1200)
            m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
            if m: return m[-1]
        time.sleep(0.5)
    raise RuntimeError("result_slop not found within timeout")

def run_one(page, survivor, donor, ssdir:Path, idx:str, debug=False):
    log(f"[case {idx}] testing survivor={survivor} donor={donor}",debug)
    s_in=pick_input(page,'survivor',0); d_in=pick_input(page,'donor',1)
    s_in.fill(str(survivor)); d_in.fill(str(donor))
    screenshot(page,ssdir,f"{idx}_filled")
    btn=safe_preview_button(page)
    btn.click(timeout=3000)
    log(f"[case {idx}] preview click ok",debug)
    screenshot(page,ssdir,f"{idx}_clicked")
    val=read_result_slop(page,timeout_ms=10000)
    log(f"[case {idx}] result_slop={val}",debug)
    return val


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=int,required=True)
    ap.add_argument('--candidates',default='candidates.csv')
    ap.add_argument('--out',default='pairs.csv')
    ap.add_argument('--both-directions',action='store_true')
    ap.add_argument('--headless',action='store_true')
    ap.add_argument('--keep-open',action='store_true')
    ap.add_argument('--slowmo',type=int,default=0)
    ap.add_argument('--debug',action='store_true')
    ap.add_argument('--screenshot-dir',default='screenshots')
    args=ap.parse_args()

    rows=[]; ssdir=Path(args.screenshot_dir)
    cands=read_candidates(Path(args.candidates))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=args.headless and not args.debug, slow_mo=args.slowmo)
        page=browser.new_page()
        page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=90000)
        screenshot(page,ssdir,'00_loaded')
        case_i=0
        for c in cands:
            cid=c['token_id']
            dirs=[(args.base,cid)] + ([(cid,args.base)] if args.both_directions else [])
            for s,d in dirs:
                case_i+=1
                rec={"survivor_id":s,"donor_id":d,"result_slop":"","price_eth":c['price_eth'],"url":c['url'],"marketplace":c['marketplace'],"status":"ok","note":"preview"}
                try:
                    rec['result_slop']=run_one(page,s,d,ssdir,f"{case_i:04d}",args.debug)
                    if s!=args.base: rec['note']='reverse (burns base)'
                except Exception as e:
                    rec['status']='error'; rec['note']=str(e)
                    log(f"[case {case_i:04d}] failed: {e}",True)
                    try: screenshot(page,ssdir,f"{case_i:04d}_failed")
                    except Exception: pass
                rows.append(rec)
        with Path(args.out).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['survivor_id','donor_id','result_slop','price_eth','url','marketplace','status','note'])
            w.writeheader(); w.writerows(rows)
        subprocess.run([sys.executable,'slonks_optimizer.py','--pairs',args.out],check=False)

        if args.keep_open or args.debug:
            log("Debug mode active. Press Enter in terminal to close browser...",True)
            input()
        browser.close()

if __name__=='__main__': main()
