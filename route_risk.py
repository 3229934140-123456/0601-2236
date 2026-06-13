#!/usr/bin/env python3
import argparse
import json
import sys
from models import (
    Route, Waypoint, ShipProfile, ShipType, RiskLevel
)
from waterway_db import WaterwayDB
from risk_engine import RiskEngine
from weather import WeatherService
from reporter import Reporter


def load_route(filepath: str) -> Route:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    waypoints = []
    for wp in data.get("waypoints", []):
        waypoints.append(Waypoint(
            name=wp["name"],
            lat=wp["lat"],
            lon=wp["lon"],
            arrival_time=wp.get("arrival_time"),
            speed_knots=wp.get("speed_knots"),
            notes=wp.get("notes", ""),
        ))
    return Route(
        name=data.get("name", "未命名航线"),
        waypoints=waypoints,
        departure_port=data.get("departure_port", ""),
        arrival_port=data.get("arrival_port", ""),
        date=data.get("date", ""),
    )


def build_ship(args) -> ShipProfile:
    ship_type_map = {t.value: t for t in ShipType}
    st = ship_type_map.get(getattr(args, "ship_type", "货船"), ShipType.CARGO)
    return ShipProfile(
        ship_type=st,
        draft=getattr(args, "draft", 4.5),
        mast_height=getattr(args, "mast_height", 18.0),
        beam=getattr(args, "beam", 16.0),
        length=getattr(args, "length", 120.0),
        max_speed=getattr(args, "max_speed", 12.0),
        name=getattr(args, "ship_name", "默认船舶"),
    )


def add_ship_args(parser):
    parser.add_argument("--ship-type", default="货船",
                        choices=[t.value for t in ShipType],
                        help="船型 (默认: 货船)")
    parser.add_argument("--draft", type=float, default=4.5,
                        help="船舶吃水/米 (默认: 4.5)")
    parser.add_argument("--mast-height", type=float, default=18.0,
                        help="桅杆高度/米 (默认: 18.0)")
    parser.add_argument("--beam", type=float, default=16.0,
                        help="船宽/米 (默认: 16.0)")
    parser.add_argument("--length", type=float, default=120.0,
                        help="船长/米 (默认: 120.0)")
    parser.add_argument("--max-speed", type=float, default=12.0,
                        help="最大航速/节 (默认: 12.0)")
    parser.add_argument("--ship-name", default="默认船舶",
                        help="船名")


def cmd_check(args):
    db = WaterwayDB()
    if args.waterway_db:
        db.load_custom(args.waterway_db)
    engine = RiskEngine(db)
    ship = build_ship(args)
    route = load_route(args.route)
    if args.date:
        route.date = args.date

    weather = None
    if args.weather:
        ws = WeatherService()
        mid = len(route.waypoints) // 2
        mid_wp = route.waypoints[mid]
        weather = ws.get_weather(args.date or route.date or "2026-06-13",
                                 mid_wp.lat, mid_wp.lon, args.port or "")

    result = engine.check_route(route, ship, weather)

    print("\n" + "=" * 55)
    print("  航线风险评估结果")
    print("=" * 55)
    print(result.summary())

    if result.risks:
        print("\n── 风险列表 ──")
        for i, r in enumerate(sorted(result.risks, key=lambda x: x.level, reverse=True), 1):
            print(f"\n  #{i} {r.level.display} [{r.category.value}]")
            print(f"      位置: {r.location or '全线'}")
            print(f"      描述: {r.description}")
            print(f"      建议: {r.suggestion}")
    else:
        print("\n  未发现风险项，航线安全。")

    print("\n── 开航建议 ──")
    overall = result.max_risk_level()
    if overall == RiskLevel.CRITICAL:
        print("  ⛔ 存在严重风险，不建议开航！")
    elif overall == RiskLevel.HIGH:
        print("  ⚠️  存在高风险，建议处理后再开航。")
    elif overall == RiskLevel.MEDIUM:
        print("  ✅ 中度风险，注意安全后可开航。")
    else:
        print("  ✅ 风险可控，可按计划开航。")
    print()


def cmd_compare(args):
    db = WaterwayDB()
    if args.waterway_db:
        db.load_custom(args.waterway_db)
    engine = RiskEngine(db)
    ship = build_ship(args)
    route_a = load_route(args.route_a)
    route_b = load_route(args.route_b)
    if args.date:
        route_a.date = args.date
        route_b.date = args.date

    weather = None
    if args.weather:
        ws = WeatherService()
        date_str = args.date or route_a.date or "2026-06-13"
        mid_a = route_a.waypoints[len(route_a.waypoints) // 2]
        mid_b = route_b.waypoints[len(route_b.waypoints) // 2]
        weather_a = ws.get_weather(date_str, mid_a.lat, mid_a.lon, args.port or "")
        weather_b = ws.get_weather(date_str, mid_b.lat, mid_b.lon, args.port or "")
        weather = weather_a

    result_a = engine.check_route(route_a, ship, weather)
    result_b = engine.check_route(route_b, ship,
                                   weather if not args.weather else
                                   WeatherService().get_weather(
                                       args.date or route_b.date or "2026-06-13",
                                       route_b.waypoints[len(route_b.waypoints) // 2].lat,
                                       route_b.waypoints[len(route_b.waypoints) // 2].lon,
                                       args.port or ""))

    comparison = engine.compare_routes(route_a, route_b, ship, weather)

    print("\n" + "=" * 55)
    print("  航线对比分析")
    print("=" * 55)

    print(f"\n── 航线A: {route_a.name} ──")
    print(result_a.summary())

    print(f"\n── 航线B: {route_b.name} ──")
    print(result_b.summary())

    print(f"\n── 对比结论 ──")
    print(comparison["recommendation"])
    print()


def cmd_weather(args):
    ws = WeatherService()
    date_str = args.date or "2026-06-13"
    port = args.port or ""

    if args.route:
        route = load_route(args.route)
        print(f"\n{'=' * 55}")
        print(f"  航线天气预报 — {route.name}")
        print(f"  日期: {date_str}")
        print(f"{'=' * 55}")
        route_weather = ws.get_route_weather(date_str, route.waypoints, port)
        for item in route_weather:
            w = item["weather"]
            print(f"\n  【{item['waypoint']}】")
            print(ws.format_weather(w))
        print()
    else:
        lat = args.lat or 31.23
        lon = args.lon or 121.47
        weather = ws.get_weather(date_str, lat, lon, port)
        loc = port or f"({lat}, {lon})"
        print(f"\n{'=' * 55}")
        print(f"  天气预报 — {loc}")
        print(f"  日期: {date_str}")
        print(f"{'=' * 55}")
        print(ws.format_weather(weather))
        print()


def cmd_report(args):
    db = WaterwayDB()
    if args.waterway_db:
        db.load_custom(args.waterway_db)
    engine = RiskEngine(db)
    ship = build_ship(args)
    route = load_route(args.route)
    if args.date:
        route.date = args.date

    weather = None
    if args.no_weather is False:
        ws = WeatherService()
        mid = len(route.waypoints) // 2
        mid_wp = route.waypoints[mid]
        weather = ws.get_weather(args.date or route.date or "2026-06-13",
                                 mid_wp.lat, mid_wp.lon, args.port or "")

    compare_data = None
    if args.compare_route:
        route_b = load_route(args.compare_route)
        if args.date:
            route_b.date = args.date
        result_b = engine.check_route(route_b, ship, weather)
        comparison = engine.compare_routes(route, route_b, ship, weather)
        compare_data = comparison

    result = engine.check_route(route, ship, weather)
    reporter = Reporter(fmt=args.format)
    report_text = reporter.generate(result, ship=ship, route=route,
                                     compare_data=compare_data)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_text)
        print(f"报告已保存至: {args.output}")
    else:
        print(report_text)


def main():
    parser = argparse.ArgumentParser(
        prog="route_risk",
        description="水路运输航线风险评估工具 — 航前快速检查计划航线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python route_risk.py check route_a.json --draft 5.0 --date 2026-06-15
  python route_risk.py compare route_a.json route_b.json --weather
  python route_risk.py weather --route route_a.json --date 2026-06-15
  python route_risk.py report route_a.json --format json --output report.json
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── check ──
    p_check = subparsers.add_parser("check", help="检查单条航线风险")
    p_check.add_argument("route", help="航线文件路径 (JSON)")
    p_check.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_check.add_argument("--port", help="港口名称")
    p_check.add_argument("--weather", action="store_true", help="叠加天气风险评估")
    p_check.add_argument("--waterway-db", help="自定义航道数据库文件 (JSON)")
    add_ship_args(p_check)

    # ── compare ──
    p_compare = subparsers.add_parser("compare", help="对比两条备选航线")
    p_compare.add_argument("route_a", help="航线A文件路径 (JSON)")
    p_compare.add_argument("route_b", help="航线B文件路径 (JSON)")
    p_compare.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_compare.add_argument("--port", help="港口名称")
    p_compare.add_argument("--weather", action="store_true", help="叠加天气风险评估")
    p_compare.add_argument("--waterway-db", help="自定义航道数据库文件 (JSON)")
    add_ship_args(p_compare)

    # ── weather ──
    p_weather = subparsers.add_parser("weather", help="查看航线/区域天气")
    p_weather.add_argument("--route", help="航线文件路径，查看沿线天气")
    p_weather.add_argument("--date", help="日期 (YYYY-MM-DD, 默认今天)")
    p_weather.add_argument("--port", help="港口名称")
    p_weather.add_argument("--lat", type=float, help="纬度 (未指定航线时使用)")
    p_weather.add_argument("--lon", type=float, help="经度 (未指定航线时使用)")

    # ── report ──
    p_report = subparsers.add_parser("report", help="生成航前检查报告")
    p_report.add_argument("route", help="航线文件路径 (JSON)")
    p_report.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_report.add_argument("--port", help="港口名称")
    p_report.add_argument("--format", default="text", choices=["text", "json", "csv"],
                          help="报告格式 (默认: text)")
    p_report.add_argument("--output", help="输出文件路径 (不指定则打印到终端)")
    p_report.add_argument("--no-weather", action="store_true",
                          help="不包含天气信息")
    p_report.add_argument("--compare-route", help="对比航线文件路径")
    p_report.add_argument("--waterway-db", help="自定义航道数据库文件 (JSON)")
    add_ship_args(p_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd_map = {
        "check": cmd_check,
        "compare": cmd_compare,
        "weather": cmd_weather,
        "report": cmd_report,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
