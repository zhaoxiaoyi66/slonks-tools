# Slonks Phase2 Automation (Python + Playwright)

仅使用官方 https://slonks.xyz/merge-lab 的 Preview/Simulate（no-gas）结果，不连接钱包、不发交易。

## Windows 小白步骤
1. `python -m venv .venv`
2. `.venv\Scripts\activate`
3. `pip install -r requirements.txt`
4. `playwright install chromium`
5. `python slonks_phase2_automation.py --base 1139 --candidates candidates.csv --out pairs.csv`

## candidates.csv 格式
`token_id,price_eth,url,marketplace`

## 可选参数
- `--both-directions`：同时测试 candidate->base（默认关闭，避免烧 base）
- `--headless`：无头模式

输出：
- `pairs.csv`
- `ranked_pairs.csv`
- `merge_plan.csv`
