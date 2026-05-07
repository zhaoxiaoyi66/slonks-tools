# Slonks best merge finder (Python + Playwright)

## Windows 小白运行
1. `python -m venv .venv`
2. `.venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `playwright install chromium`
5. `python slonks_find_best_merge.py --base 1139`

## 常用参数
- `--max-candidates 100`（默认）
- `--full-scan` 扫描全部同级候选
- `--headful` 调试显示浏览器
- `--keep-open` 结束后不立即关浏览器

输出文件：
- `ranked_results.csv`
- `scan_log.csv`
- `best_merge.txt`
