#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,re,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright

SAFE_BLOCK=re.compile(r"merge|wallet|connect|approve|transaction",re.I)


def read_candidates(path:Path):
    out=[]
    with path.open('r',encoding='utf-8',newline='') as f:
        for r in csv.DictReader(f):
            out.append({"token_id":int(r.get('token_id','0') or 0),"price_eth":r.get('price_eth',''),"url":r.get('url',''),"marketplace":r.get('marketplace','')})
    return out

def find_input(page, key):
    loc=page.get_by_label(key, exact=False)
    if loc.count()==0: loc=page.locator(f"input[placeholder*='{key}' i]")
    return loc.first

def click_preview_only(page):
    # never click dangerous buttons
    for b in page.locator('button').all():
        t=(b.inner_text() or '').strip()
        if SAFE_BLOCK.search(t):
            continue
    btn=page.get_by_role('button', name=re.compile(r'preview|simulate|no\s*-?\s*gas',re.I))
    if btn.count()==0:
        btn=page.locator("button:has-text('Preview'),button:has-text('Simulate')")
    if btn.count()==0: raise RuntimeError('preview button not found')
    btn.first.click()

def read_result_slop(page):
    cands=[page.locator(r'text=/result\s*slop/i').first,page.locator('text=/slop/i').first]
    for c in cands:
        if c.count()==0: continue
        txt=c.inner_text(timeout=2500)
        m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
        if m: return m[-1]
    raise RuntimeError('result_slop not found')

def run_one(page,survivor,donor):
    find_input(page,'survivor').fill(str(survivor))
    find_input(page,'donor').fill(str(donor))
    click_preview_only(page)
    time.sleep(1.5)
    return read_result_slop(page)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base',type=int,required=True)
    ap.add_argument('--candidates',default='candidates.csv')
    ap.add_argument('--out',default='pairs.csv')
    ap.add_argument('--both-directions',action='store_true')
    ap.add_argument('--headless',action='store_true')
    args=ap.parse_args()

    rows=[]
    cands=read_candidates(Path(args.candidates))
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=args.headless)
        page=browser.new_page()
        page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=60000)
        for c in cands:
            cid=c['token_id']
            for d in ([(args.base,cid)] + ([(cid,args.base)] if args.both_directions else [])):
                s,do=d
                rec={"survivor_id":s,"donor_id":do,"result_slop":"","price_eth":c['price_eth'],"url":c['url'],"marketplace":c['marketplace'],"status":"ok","note":"preview"}
                try:
                    rec['result_slop']=run_one(page,s,do)
                    if s!=args.base: rec['note']='reverse (burns base)'
                except Exception as e:
                    rec['status']='error'; rec['note']=str(e)
                rows.append(rec)
        browser.close()

    with Path(args.out).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['survivor_id','donor_id','result_slop','price_eth','url','marketplace','status','note'])
        w.writeheader(); w.writerows(rows)

    subprocess.run([sys.executable,'slonks_optimizer.py','--pairs',args.out],check=False)

if __name__=='__main__':
    main()
