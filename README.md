# Slonks local simulator (RPC only)

第一步（先构建 palette，可恢复）：
`python slonks_local_simulator.py --build-palette --start-id 0 --end-id 500 --resume --rpc https://ethereum.publicnode.com`

第二步（单组验证）：
`python slonks_local_simulator.py --pair 1139 583 --rpc https://ethereum.publicnode.com`

批量同级：
`python slonks_local_simulator.py --base 1139 --start-id 0 --end-id 500 --max-candidates 50 --rpc https://ethereum.publicnode.com`

如果报：
`palette.json missing; run --build-palette first`
或
`palette incomplete: X/222 colors`
请继续执行 `--build-palette --resume`。

仅使用 eth_call / view，不连接钱包、不发送交易。


可尝试直接提取公开资料中的 palette（不走RPC扫图）：
`python slonks_local_simulator.py --extract-palette-web`
