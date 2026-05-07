# Slonks local simulator (RPC only)

第一次先构建 palette：
`python slonks_local_simulator.py --build-palette --rpc https://ethereum.publicnode.com`

然后测试单组：
`python slonks_local_simulator.py --pair 1139 583 --rpc https://ethereum.publicnode.com`

批量同级：
`python slonks_local_simulator.py --base 1139 --start-id 0 --end-id 500 --max-candidates 50 --rpc https://ethereum.publicnode.com`

如果报 palette 缺失：
`palette.json missing or incomplete; run --build-palette first or use better RPC`

仅使用 eth_call / view，不连接钱包、不发送交易。
