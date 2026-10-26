#!/usr/bin/env python3
"""research-tools 统一入口。

用法示例：
  python cli.py sem   input.png -o out/sem --cmap viridis
  python cli.py eis   data.csv -o out/eis --fit cpe --color '#0072B2'
  python cli.py polar data.csv -o out/polar --mode tafel --auto-tafel
  python cli.py ocp   data.csv -o out/ocp
  python cli.py pull  data.csv -o out/pull --colors '#0072B2,#E69F00'
  python cli.py demo  # 生成 DEMO 数据并出图
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SUB = {
    "sem": ("sem_pseudocolor", "main"),
    "eis": ("eis_plot", "main"),
    "polar": ("polarization_plot", "main"),
    "ocp": ("ocp_plot", "main"),
    "pull": ("pull_off_bar", "main"),
}


def _print_root_help() -> None:
    print(
        "usage: cli.py {sem,eis,polar,ocp,pull,demo} ...\n\n"
        "实验室通用科研出图工具 v0.3\n\n"
        "  sem    SEM 灰度伪彩（--cmap / -c）\n"
        "  eis    EIS 拟合 + Nyquist/Bode（coating/lr_cpe/cpe…；残差图；参数表）\n"
        "  polar  极化曲线（--auto-tafel / --mode）\n"
        "  ocp    开路电位 E–t\n"
        "  pull   拉拔柱状图（--color / --colors / --palette）\n"
        "  demo   生成 DEMO 合成数据并出图\n\n"
        "子命令详细参数：python cli.py <cmd> --help\n"
        "颜色示例：python cli.py eis data.csv -o out --color '#0072B2'\n"
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        _print_root_help()
        return 0

    cmd, rest = argv[0], argv[1:]

    if cmd == "demo":
        from demo.generate_demo import main as demo_main

        return demo_main()

    if cmd in _SUB:
        # 将裸 --help / -h 交给子模块，避免被本层吞掉
        if not rest or rest == ["-h"] or rest == ["--help"]:
            rest = ["--help"]
        mod_name, fn_name = _SUB[cmd]
        mod = __import__(mod_name)
        return getattr(mod, fn_name)(rest)

    print(f"未知子命令: {cmd}\n", file=sys.stderr)
    _print_root_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
