# Slonks minimal merge tools

先打通单组 preview：
`python slonks_pair_preview.py --survivor 1139 --donor 583 --manual --headful --keep-open`

自动单组：
`python slonks_pair_preview.py --survivor 1139 --donor 583 --debug --headful --keep-open`

批量同级（不含市场/价格）：
`python slonks_find_best_merge.py --base 1139 --start-id 0 --end-id 200 --max-candidates 20 --debug`

输出：
- `pair_preview_result.csv`
- `ranked_results.csv`
- `scan_log.csv`
- `best_merge.txt`
- `screenshots/`
