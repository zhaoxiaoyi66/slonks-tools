# Slonks local simulator (no Playwright)

单组验证：
`python slonks_local_simulator.py --pair 1139 583`

批量同级：
`python slonks_local_simulator.py --base 1139 --start-id 0 --end-id 500 --max-candidates 50`

输出：
- `ranked_results.csv`
- `best_merge.txt`
- `scan_log.csv`
- `palette.json`
- `token_cache.json`

仅使用 `eth_call/view`，不连接钱包，不发送交易。
