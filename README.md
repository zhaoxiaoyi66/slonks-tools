# Slonks listing monitor

## 安装依赖（Windows）
`pip install -r requirements.txt`

## 运行一次
`python slonks_listing_monitor.py --base 1139 --once --top 10`

## 每 60 秒监控
`python slonks_listing_monitor.py --base 1139 --interval 60 --top 10`

## 限制价格
`python slonks_listing_monitor.py --base 1139 --max-price 0.3 --top 10`

## 手动 CSV fallback
`python slonks_listing_monitor.py --listings listings.csv --once`

CSV: `token_id,price_eth,url,marketplace`

输出文件：
- `listing_hits.csv`
- `seen_alerts.json`
