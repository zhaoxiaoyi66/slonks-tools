#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,re,subprocess,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright

BLOCK=re.compile(r"merge|wallet|connect|approve|confirm|transaction",re.I)


def log(msg): print(msg, flush=True)

def read_candidates(path:Path):
    with path.open('r',encoding='utf-8',newline='') as f:
        return [{"token_id":int(r.get('token_id','0') or 0),"price_eth":r.get('price_eth',''),"url":r.get('url',''),"marketplace":r.get('marketplace','')} for r in csv.DictReader(f)]

def screenshot(page, d:Path, name:str):
    d.mkdir(parents=True,exist_ok=True); page.screenshot(path=str(d/f"{name}.png"),full_page=True)

def find_keep_burn_controls(page):
    keep = page.get_by_text(re.compile(r"keep",re.I)).first
    burn = page.get_by_text(re.compile(r"burn",re.I)).first
    return keep, burn

def select_token(page, role:str, token_id:int):
    # role: keep or burn
    # try label/placeholder/combobox/input near role first
    cands=[
        page.get_by_label(role, exact=False),
        page.get_by_placeholder(role, exact=False),
        page.locator(f"*:has-text('{role}') >> xpath=.. >> input"),
        page.get_by_role('combobox'),
        page.locator('input')
    ]
    target=None
    for c in cands:
        if c.count()>0:
            target=c.first; break
    if not target: raise RuntimeError(f"找不到 {role} input")
    target.click(timeout=2000)
    target.fill(str(token_id))
    # try pick search result
    for sel in [page.get_by_text(re.compile(rf"\b{token_id}\b")), page.locator(f"text=#{token_id}"), page.locator(f"li:has-text('{token_id}')")]:
        if sel.count()>0:
            try:
                sel.first.click(timeout=2000)
                return
            except Exception:
                pass
    # if no selectable result, keep filled value; caller will verify

def verify_selection(page, survivor_id:int, donor_id:int):
    txt=page.inner_text('body')
    has_survivor=str(survivor_id) in txt
    has_donor=str(donor_id) in txt
    donor_zero=bool(re.search(r"burn\s*[:：]?\s*0\b", txt, re.I))
    return has_survivor, has_donor, donor_zero

def preview_button(page):
    opts=[page.get_by_text('Preview',exact=False),page.locator("button:has-text('Preview')"),page.locator("button:has-text('Simulate')"),page.get_by_role('button',name=re.compile(r'preview|simulate|no\s*-?\s*gas',re.I))]
    for o in opts:
        if o.count()==0: continue
        for i in range(o.count()):
            b=o.nth(i)
            t=(b.inner_text(timeout=800) or '').strip()
            if not BLOCK.search(t): return b
    raise RuntimeError('找不到 Preview/no-gas simulate 按钮')

def read_result_slop(page):
    end=time.time()+10
    while time.time()<end:
        for loc in [page.locator(r"text=/result\s*slop/i"),page.locator(r"text=/slop/i")]:
            if loc.count()==0: continue
            t=loc.first.inner_text(timeout=1200)
            m=re.findall(r"[-+]?\d+(?:\.\d+)?",t)
            if m: return m[-1]
        time.sleep(0.5)
    raise RuntimeError('result slop not found')

def run_case(page, base, donor, ssdir:Path):
    try:
        select_token(page,'keep',base)
    except Exception as e:
        raise RuntimeError(f'找不到 survivor input: {e}')
    try:
        select_token(page,'burn',donor)
    except Exception as e:
        raise RuntimeError(f'找不到 donor input: {e}')

    has_s,has_d,donor_zero=verify_selection(page,base,donor)
    screenshot(page,ssdir,f'before_preview_{base}_{donor}')
    if not has_s: raise RuntimeError('找不到 token search result: survivor not visible')
    if not has_d: raise RuntimeError('找不到 token search result: donor not visible')
    if donor_zero: raise RuntimeError('donor token was not selected, burn value stayed 0')

    btn=preview_button(page)
    if not btn.is_enabled():
        raise RuntimeError('preview button disabled')
    btn.click(timeout=3000)
    screenshot(page,ssdir,f'after_preview_{base}_{donor}')
    return read_result_slop(page)

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
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=args.headless and not args.debug, slow_mo=args.slowmo)
        page=browser.new_page(); page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=90000)
        screenshot(page,ssdir,'00_loaded')
        for c in read_candidates(Path(args.candidates)):
            dirs=[(args.base,c['token_id'])] + ([(c['token_id'],args.base)] if args.both_directions else [])
            for s,d in dirs:
                rec={"survivor_id":s,"donor_id":d,"result_slop":"","price_eth":c['price_eth'],"url":c['url'],"marketplace":c['marketplace'],"status":"ok","note":"preview"}
                log(f"testing survivor={s} donor={d}")
                try:
                    rec['result_slop']=run_case(page,s,d,ssdir)
                    log(f"success result_slop={rec['result_slop']}")
                except Exception as e:
                    rec['status']='error'; rec['note']=str(e)
                    log(f"failed: {e}")
                    screenshot(page,ssdir,f'failed_{s}_{d}')
                rows.append(rec)
        with Path(args.out).open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['survivor_id','donor_id','result_slop','price_eth','url','marketplace','status','note']);w.writeheader();w.writerows(rows)
        subprocess.run([sys.executable,'slonks_optimizer.py','--pairs',args.out],check=False)
        if args.keep_open or args.debug:
            log('Debug mode active. Press Enter to close browser...'); input()
        browser.close()

if __name__=='__main__': main()
