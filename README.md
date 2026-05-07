# Slonks best merge finder (Python + Playwright)

## 第一次安装（Windows）
1. `python -m venv .venv`
2. `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
3. `.venv\Scripts\activate`
4. `pip install -r requirements.txt`
5. `playwright install chromium`

## 每次运行（Windows）
1. `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
2. `.venv\Scripts\activate`
3. `python slonks_find_best_merge.py --base 1139 --max-candidates 20 --debug`

## 手动候选模式
`python slonks_find_best_merge.py --base 1139 --candidates candidates.csv --debug`

## 常用参数
- `--rpc https://eth.llamarpc.com`
- `--timeout 10`
- `--start-id 0 --end-id 500`
- `--max-candidates 20`
- `--full-scan`
- `--headful`
- `--keep-open`

## 输出文件
- `ranked_results.csv`
- `best_merge.txt`
- `scan_log.csv`
