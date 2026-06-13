#!/usr/bin/env python3
import argparse
import json
import re
import sys
from models import (
    Route, Waypoint, ShipProfile, ShipType, RiskLevel
)
from waterway_db import WaterwayDB
from risk_engine import RiskEngine
from weather import WeatherService
from reporter import Reporter


def validate_route_file(filepath: str):
    errors = []
    warnings = []
    data = None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, [f"文件不存在: {filepath}"], []
    except json.JSONDecodeError as e:
        return None, [f"JSON 解析失败: {e}"], []

    if not isinstance(data, dict):
        return None, ["文件顶层不是 JSON 对象"], []

    if not data.get("name"):
        warnings.append("航线缺少 name 字段，将使用默认名称")

    raw_waypoints = data.get("waypoints", [])
    if not raw_waypoints:
        return data, ["航线 waypoints 为空，无法构成有效航线"], warnings

    valid_waypoints = []
    for idx, wp in enumerate(raw_waypoints):
        tag = f"航点 #{idx + 1}" + (f"({wp.get('name', '')})" if wp.get("name") else "")

        if not isinstance(wp, dict):
            errors.append(f"{tag}: 不是有效的 JSON 对象，请检查格式")
            continue

        missing = []
        if "name" not in wp or not wp["name"]:
            missing.append("name")
        if "lat" not in wp:
            missing.append("lat")
        if "lon" not in wp:
            missing.append("lon")

        if missing:
            errors.append(f"{tag}: 缺少必填字段 {', '.join(missing)}，"
                          f"请补充后重新检查")
            continue

        try:
            lat = float(wp["lat"])
        except (ValueError, TypeError):
            errors.append(f"{tag}: lat 值 '{wp['lat']}' 不是有效数字，应为 -90~90 的浮点数")
            continue
        try:
            lon = float(wp["lon"])
        except (ValueError, TypeError):
            errors.append(f"{tag}: lon 值 '{wp['lon']}' 不是有效数字，应为 -180~180 的浮点数")
            continue

        if not (-90 <= lat <= 90):
            errors.append(f"{tag}: lat={lat} 超出范围，纬度应为 -90~90，请核实坐标")
            continue
        if not (-180 <= lon <= 180):
            errors.append(f"{tag}: lon={lon} 超出范围，经度应为 -180~180，请核实坐标")
            continue

        if wp.get("arrival_time"):
            t = wp["arrival_time"]
            m = re.match(r"^(\d{1,2}):(\d{2})(:\d{2})?$", str(t))
            if not m:
                errors.append(f"{tag}: arrival_time '{t}' 格式不对，应为 HH:MM 或 HH:MM:SS")
                continue
            hh, mm = int(m.group(1)), int(m.group(2))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                errors.append(f"{tag}: arrival_time '{t}' 时/分超出范围，应为 00:00~23:59")
                continue

        if wp.get("speed_knots") is not None:
            try:
                spd = float(wp["speed_knots"])
                if spd <= 0:
                    warnings.append(f"{tag}: speed_knots={spd} 不合理，应为正数")
            except (ValueError, TypeError):
                warnings.append(f"{tag}: speed_knots 值 '{wp['speed_knots']}' 不是有效数字")

        valid_waypoints.append(Waypoint(
            name=wp["name"],
            lat=lat,
            lon=lon,
            arrival_time=wp.get("arrival_time"),
            speed_knots=wp.get("speed_knots"),
            notes=wp.get("notes", ""),
        ))

    return data, errors, warnings


def load_route(filepath: str) -> Route:
    data, errors, warnings = validate_route_file(filepath)

    if data is None:
        print("❌ 航线文件无法加载:\n")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)

    if errors:
        print("❌ 航线文件存在数据问题，请修正后重试:\n")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)

    if warnings:
        print("⚠️  航线文件存在以下提醒:\n")
        for w in warnings:
            print(f"  • {w}")
        print()

    waypoints = []
    for wp in data.get("waypoints", []):
        waypoints.append(Waypoint(
            name=wp["name"],
            lat=float(wp["lat"]),
            lon=float(wp["lon"]),
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


def cmd_validate(args):
    data, errors, warnings = validate_route_file(args.route)

    if data is None:
        print("\n❌ 航线文件无法加载:\n")
        for e in errors:
            print(f"  • {e}")
        print("\n  请修正文件后重新验证。")
        sys.exit(1)

    print(f"\n{'=' * 55}")
    print(f"  航线数据质量检查")
    print(f"{'=' * 55}")
    print(f"  文件: {args.route}")
    print(f"  航线名称: {data.get('name', '(未命名)')}")

    raw_wps = data.get("waypoints", [])
    valid_wps = []
    for idx, wp in enumerate(raw_wps):
        if not isinstance(wp, dict):
            continue
        if "name" not in wp or "lat" not in wp or "lon" not in wp:
            continue
        try:
            lat = float(wp["lat"])
            lon = float(wp["lon"])
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                valid_wps.append(Waypoint(
                    name=wp["name"], lat=lat, lon=lon,
                    arrival_time=wp.get("arrival_time"),
                    speed_knots=wp.get("speed_knots"),
                    notes=wp.get("notes", ""),
                ))
        except (ValueError, TypeError):
            continue

    print(f"\n── 基本信息 ──")
    print(f"  航点总数: {len(raw_wps)}")
    print(f"  有效航点: {len(valid_wps)}")

    if data.get("departure_port"):
        print(f"  出发港: {data['departure_port']}")
    else:
        print(f"  出发港: (未填写)")

    if data.get("arrival_port"):
        print(f"  到达港: {data['arrival_port']}")
    else:
        print(f"  到达港: (未填写)")

    if data.get("date"):
        print(f"  计划日期: {data['date']}")
    else:
        print(f"  计划日期: (未填写)")

    if len(valid_wps) >= 2:
        tmp_route = Route(name=data.get("name", ""), waypoints=valid_wps)
        dist = tmp_route.total_distance_nm()
        print(f"  总距离: {dist:.1f} 海里")
    else:
        print(f"  总距离: (有效航点不足，无法计算)")

    print(f"\n── 航点明细 ──")
    for idx, wp in enumerate(raw_wps):
        tag = f"#{idx + 1}"
        if not isinstance(wp, dict):
            print(f"  {tag} ❌ 不是有效的JSON对象")
            continue
        name = wp.get("name", "")
        lat_val = wp.get("lat", "")
        lon_val = wp.get("lon", "")
        arr = wp.get("arrival_time", "")
        spd = wp.get("speed_knots", "")
        print(f"  {tag} {name:<12s}  纬度={str(lat_val):<10s}  经度={str(lon_val):<10s}  "
              f"到港={str(arr):<8s}  航速={str(spd)}")

    missing_fields = []
    for idx, wp in enumerate(raw_wps):
        if not isinstance(wp, dict):
            continue
        tag = f"航点#{idx + 1}({wp.get('name', '?')})"
        if not wp.get("name"):
            missing_fields.append(f"{tag}: 缺少 name")
        if wp.get("lat") is None:
            missing_fields.append(f"{tag}: 缺少 lat")
        if wp.get("lon") is None:
            missing_fields.append(f"{tag}: 缺少 lon")
        if not wp.get("arrival_time"):
            missing_fields.append(f"{tag}: 缺少 arrival_time（不影响评估，但建议填写）")

    if missing_fields:
        print(f"\n── 缺失字段 ──")
        for m in missing_fields:
            print(f"  • {m}")

    duplicates = []
    seen = set()
    for idx, wp in enumerate(raw_wps):
        if not isinstance(wp, dict):
            continue
        key = (round(float(wp.get("lat", 0)), 4), round(float(wp.get("lon", 0)), 4))
        if key in seen:
            name = wp.get("name", "?")
            duplicates.append(f"航点#{idx + 1}({name}) 与前面航点坐标重复")
        seen.add(key)

    if duplicates:
        print(f"\n── 重复航点 ──")
        for d in duplicates:
            print(f"  • {d}")

    if len(valid_wps) >= 2:
        print(f"\n── 异常航段 ──")
        found_anomaly = False
        for i in range(len(valid_wps) - 1):
            dist_km = valid_wps[i].distance_to(valid_wps[i + 1])
            dist_nm = dist_km * 0.539957
            if dist_nm > 200:
                found_anomaly = True
                print(f"  ⚠️  {valid_wps[i].name} → {valid_wps[i+1].name}: "
                      f"{dist_nm:.0f} 海里（跨度异常大，建议增加中间航点）")
            elif dist_nm < 0.1:
                found_anomaly = True
                print(f"  ⚠️  {valid_wps[i].name} → {valid_wps[i+1].name}: "
                      f"{dist_nm:.3f} 海里（距离极近，可能重复）")
        if not found_anomaly:
            print(f"  ✅ 未发现异常航段")

    error_count = len(errors)
    warning_count = len(warnings)

    print(f"\n── 检查结论 ──")
    if error_count == 0:
        print(f"  ✅ 航线数据质量合格")
        if warning_count > 0:
            print(f"  ℹ️  有 {warning_count} 条提醒（不影响评估，建议优化）")
    else:
        print(f"  ❌ 发现 {error_count} 个错误，需修正后才能进行风险评估")
        for e in errors:
            print(f"     • {e}")
    if warnings:
        print(f"\n── 提醒 ──")
        for w in warnings:
            print(f"  ℹ️  {w}")

    print()
    if error_count > 0:
        sys.exit(1)


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
        date_str = args.date or route.date or "2026-06-13"
        weather = ws.get_route_aggregate_weather(date_str, route.waypoints, args.port or "")

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

    weather_a = None
    weather_b = None
    date_str = args.date or route_a.date or "2026-06-13"

    if args.weather:
        ws = WeatherService()
        weather_a = ws.get_route_aggregate_weather(date_str, route_a.waypoints, args.port or "")
        weather_b = ws.get_route_aggregate_weather(date_str, route_b.waypoints, args.port or "")

    result_a = engine.check_route(route_a, ship, weather_a)
    result_b = engine.check_route(route_b, ship, weather_b)

    comparison = engine.compare_routes(route_a, route_b, ship,
                                        weather_a=weather_a, weather_b=weather_b)

    print("\n" + "=" * 55)
    print("  航线对比分析")
    print("=" * 55)

    print(f"\n── 航线A: {route_a.name} ──")
    print(result_a.summary())
    if weather_a:
        print(f"  天气: 风速 {weather_a.wind_speed_ms}m/s  "
              f"浪高 {weather_a.wave_height_m}m  "
              f"能见度 {weather_a.visibility_km}km  "
              f"风险 {weather_a.risk_level().display}")

    print(f"\n── 航线B: {route_b.name} ──")
    print(result_b.summary())
    if weather_b:
        print(f"  天气: 风速 {weather_b.wind_speed_ms}m/s  "
              f"浪高 {weather_b.wave_height_m}m  "
              f"能见度 {weather_b.visibility_km}km  "
              f"风险 {weather_b.risk_level().display}")

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
        date_str = args.date or route.date or "2026-06-13"
        weather = ws.get_route_aggregate_weather(date_str, route.waypoints, args.port or "")

    compare_data = None
    if args.compare_route:
        route_b = load_route(args.compare_route)
        if args.date:
            route_b.date = args.date
        weather_b = None
        if args.no_weather is False:
            ws = WeatherService()
            weather_b = ws.get_route_aggregate_weather(
                args.date or route_b.date or "2026-06-13",
                route_b.waypoints, args.port or "")
        comparison = engine.compare_routes(route, route_b, ship,
                                            weather_a=weather, weather_b=weather_b)
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
  python route_risk.py validate route_a.json
  python route_risk.py check route_a.json --draft 5.0 --date 2026-06-15
  python route_risk.py compare route_a.json route_b.json --weather
  python route_risk.py weather --route route_a.json --date 2026-06-15
  python route_risk.py report route_a.json --format markdown --output report.md
        """,
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    p_validate = subparsers.add_parser("validate", help="检查航线文件数据质量")
    p_validate.add_argument("route", help="航线文件路径 (JSON)")

    p_check = subparsers.add_parser("check", help="检查单条航线风险")
    p_check.add_argument("route", help="航线文件路径 (JSON)")
    p_check.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_check.add_argument("--port", help="港口名称")
    p_check.add_argument("--weather", action="store_true", help="叠加天气风险评估")
    p_check.add_argument("--waterway-db", help="自定义航道数据库文件 (JSON)")
    add_ship_args(p_check)

    p_compare = subparsers.add_parser("compare", help="对比两条备选航线")
    p_compare.add_argument("route_a", help="航线A文件路径 (JSON)")
    p_compare.add_argument("route_b", help="航线B文件路径 (JSON)")
    p_compare.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_compare.add_argument("--port", help="港口名称")
    p_compare.add_argument("--weather", action="store_true", help="叠加天气风险评估")
    p_compare.add_argument("--waterway-db", help="自定义航道数据库文件 (JSON)")
    add_ship_args(p_compare)

    p_weather = subparsers.add_parser("weather", help="查看航线/区域天气")
    p_weather.add_argument("--route", help="航线文件路径，查看沿线天气")
    p_weather.add_argument("--date", help="日期 (YYYY-MM-DD, 默认今天)")
    p_weather.add_argument("--port", help="港口名称")
    p_weather.add_argument("--lat", type=float, help="纬度 (未指定航线时使用)")
    p_weather.add_argument("--lon", type=float, help="经度 (未指定航线时使用)")

    p_report = subparsers.add_parser("report", help="生成航前检查报告")
    p_report.add_argument("route", help="航线文件路径 (JSON)")
    p_report.add_argument("--date", help="计划开航日期 (YYYY-MM-DD)")
    p_report.add_argument("--port", help="港口名称")
    p_report.add_argument("--format", default="text",
                          choices=["text", "json", "csv", "markdown"],
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
        "validate": cmd_validate,
        "check": cmd_check,
        "compare": cmd_compare,
        "weather": cmd_weather,
        "report": cmd_report,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
