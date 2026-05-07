#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,re,time
from pathlib import Path
from playwright.sync_api import sync_playwright

BAD=re.compile(r"merge|connect|wallet|approve|confirm|transaction|mint|burn",re.I)
GOOD=re.compile(r"preview|simulate",re.I)

def shot(page,name):
    d=Path('screenshots'); d.mkdir(exist_ok=True)
    p=d/f'{name}.png'; page.screenshot(path=str(p),full_page=True); return str(p)

def dump_debug(page):
    print('[debug] url=',page.url)
    print('[debug] buttons:')
    bs=page.locator('button')
    for i in range(bs.count()):
        print('  -', (bs.nth(i).inner_text(timeout=500) or '').strip())
    print('[debug] input/combobox/textbox:')
    for sel in ['input','[role="combobox"]','[role="textbox"]']:
        loc=page.locator(sel)
        for i in range(loc.count()):
            el=loc.nth(i)
            print('  -',sel,i,'placeholder=',el.get_attribute('placeholder'),'name=',el.get_attribute('name'))

def safe_preview_click(page):
    bs=page.locator('button')
    cands=[]
    for i in range(bs.count()):
        b=bs.nth(i); t=(b.inner_text(timeout=700) or '').strip()
        if GOOD.search(t) and not BAD.search(t): cands.append((b,t))
    if not cands: raise RuntimeError('preview 按钮找不到')
    for b,t in cands:
        if b.is_visible() and b.is_enabled():
            b.scroll_into_view_if_needed(); page.wait_for_timeout(300)
            b.click(timeout=3000)
            return t
    raise RuntimeError('preview 按钮不可用')

def read_result(page,timeout=20):
    end=time.time()+timeout
    while time.time()<end:
        for pat in [r'text=/result\s*slop/i',r'text=/slop/i',r'text=/result/i']:
            loc=page.locator(pat)
            if loc.count()==0: continue
            txt=loc.first.inner_text(timeout=1000)
            m=re.findall(r"[-+]?\d+(?:\.\d+)?",txt)
            if m: return float(m[-1])
        time.sleep(0.4)
    raise RuntimeError('result_slop 抓不到')

def write_result(row):
    with Path('pair_preview_result.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=['survivor_id','donor_id','result_slop','status','note'])
        w.writeheader(); w.writerow(row)

def run(survivor, donor, manual=False, debug=False, headful=False, keep_open=False):
    row={'survivor_id':survivor,'donor_id':donor,'result_slop':'','status':'error','note':''}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=not headful)
        page=browser.new_page(); page.goto('https://slonks.xyz/merge-lab',wait_until='domcontentloaded',timeout=90000)
        if debug: dump_debug(page)
        if manual:
            shot(page,f'before_manual_{survivor}_{donor}')
            print('请手动选择 survivor/donor 并手动点击 Preview，然后回终端按 Enter...')
            input()
        else:
            inputs=page.locator('input')
            if inputs.count()<2:
                row['note']='survivor 选择失败'; write_result(row); return row
            try:
                inputs.nth(0).fill(str(survivor))
            except Exception:
                row['note']='survivor 选择失败'; write_result(row); return row
            try:
                inputs.nth(1).fill(str(donor))
            except Exception:
                row['note']='donor 选择失败'; write_result(row); return row
            shot(page,f'before_preview_{survivor}_{donor}')
            try:
                txt=safe_preview_click(page)
                if debug: print('[debug] clicked button=',txt)
            except Exception as e:
                row['note']=str(e); shot(page,f'preview_error_{survivor}_{donor}'); write_result(row); return row
        shot(page,f'after_preview_{survivor}_{donor}')
        try:
            rs=read_result(page,20); row['result_slop']=rs; row['status']='ok'; row['note']='ok'
        except Exception as e:
            row['note']=str(e); shot(page,f'preview_error_{survivor}_{donor}')
        write_result(row)
        if keep_open:
            print('按 Enter 关闭浏览器...'); input()
        browser.close()
    return row

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--survivor',type=int,required=True)
    ap.add_argument('--donor',type=int,required=True)
    ap.add_argument('--manual',action='store_true')
    ap.add_argument('--debug',action='store_true')
    ap.add_argument('--headful',action='store_true')
    ap.add_argument('--keep-open',action='store_true')
    a=ap.parse_args()
    r=run(a.survivor,a.donor,a.manual,a.debug,a.headful,a.keep_open)
    print(r)
