import json
from datetime import datetime
from typing import Optional
from models import CheckResult, RiskLevel, RiskCategory


class Reporter:
    def __init__(self, fmt: str = "text"):
        self.fmt = fmt.lower()

    def generate(self, result: CheckResult, ship=None, route=None,
                 compare_data: Optional[dict] = None) -> str:
        if self.fmt == "json":
            return self._json_report(result, ship, route, compare_data)
        elif self.fmt == "csv":
            return self._csv_report(result)
        else:
            return self._text_report(result, ship, route, compare_data)

    def _text_report(self, result: CheckResult, ship=None, route=None,
                     compare_data: Optional[dict] = None) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sep = "=" * 60
        lines = [
            sep,
            "         水路运输航线风险评估 — 航前检查报告",
            sep,
            f"生成时间: {now}",
            f"航线名称: {result.route_name}",
        ]
        if route:
            lines.append(f"出发港: {route.departure_port}    到达港: {route.arrival_port}")
            if route.date:
                lines.append(f"计划日期: {route.date}")
        if ship:
            lines.append(f"船型: {ship.ship_type.value}  船名: {ship.name}")
            lines.append(f"吃水: {ship.draft}m  桅杆高: {ship.mast_height}m  "
                          f"最大航速: {ship.max_speed}节")
        lines.append("")
        lines.append(f"总航程: {result.total_distance_nm:.1f} 海里")
        lines.append(f"预计用时: {result.estimated_time_hours:.1f} 小时")
        lines.append(f"最高风险等级: {result.max_risk_level().display}")

        if result.weather:
            lines.append("")
            lines.append("-" * 40)
            lines.append("【天气概况】")
            lines.append(f"  风速: {result.weather.wind_speed_ms}m/s  "
                          f"风向: {result.weather.wind_direction}°")
            lines.append(f"  浪高: {result.weather.wave_height_m}m")
            lines.append(f"  能见度: {result.weather.visibility_km}km")
            lines.append(f"  降水: {result.weather.precipitation}")
            lines.append(f"  气象风险: {result.weather.risk_level().display}")

        by_level = result.risks_by_level()
        lines.append("")
        lines.append("-" * 40)
        lines.append("【风险统计】")
        lines.append(f"  严重(CRITICAL): {len(by_level[RiskLevel.CRITICAL])} 项")
        lines.append(f"  高(HIGH):       {len(by_level[RiskLevel.HIGH])} 项")
        lines.append(f"  中(MEDIUM):     {len(by_level[RiskLevel.MEDIUM])} 项")
        lines.append(f"  低(LOW):        {len(by_level[RiskLevel.LOW])} 项")

        if result.risks:
            lines.append("")
            lines.append("-" * 40)
            lines.append("【风险详情】")
            for i, r in enumerate(sorted(result.risks, key=lambda x: x.level, reverse=True), 1):
                lines.append(f"")
                lines.append(f"  #{i} [{r.level.display}] [{r.category.value}]")
                lines.append(f"  位置: {r.location or '全线'}")
                lines.append(f"  描述: {r.description}")
                lines.append(f"  建议: {r.suggestion}")

        if compare_data:
            lines.append("")
            lines.append("-" * 40)
            lines.append("【航线对比】")
            lines.append(compare_data.get("recommendation", ""))

        lines.append("")
        lines.append("-" * 40)
        lines.append("【调整建议汇总】")
        suggestions = [r.suggestion for r in result.risks if r.level >= RiskLevel.HIGH]
        if suggestions:
            for i, s in enumerate(suggestions, 1):
                lines.append(f"  {i}. {s}")
        else:
            lines.append("  无高风险及以上项，航线可按计划执行。")

        overall = result.max_risk_level()
        lines.append("")
        lines.append("-" * 40)
        lines.append("【开航建议】")
        if overall == RiskLevel.CRITICAL:
            lines.append("  ⛔ 存在严重风险，不建议开航！请解决上述问题后重新评估。")
        elif overall == RiskLevel.HIGH:
            lines.append("  ⚠️  存在高风险，建议采取上述措施后再开航。")
        elif overall == RiskLevel.MEDIUM:
            lines.append("  ✅ 存在中度风险，注意上述事项后可谨慎开航。")
        else:
            lines.append("  ✅ 风险可控，可按计划开航。")

        lines.append(sep)
        return "\n".join(lines)

    def _json_report(self, result: CheckResult, ship=None, route=None,
                     compare_data: Optional[dict] = None) -> str:
        data = {
            "report_time": datetime.now().isoformat(),
            "route_name": result.route_name,
            "total_distance_nm": round(result.total_distance_nm, 2),
            "estimated_time_hours": round(result.estimated_time_hours, 2),
            "max_risk_level": result.max_risk_level().value,
            "risk_summary": {
                "critical": len([r for r in result.risks if r.level == RiskLevel.CRITICAL]),
                "high": len([r for r in result.risks if r.level == RiskLevel.HIGH]),
                "medium": len([r for r in result.risks if r.level == RiskLevel.MEDIUM]),
                "low": len([r for r in result.risks if r.level == RiskLevel.LOW]),
            },
            "risks": [r.to_dict() for r in sorted(result.risks, key=lambda x: x.level, reverse=True)],
            "suggestions": [r.suggestion for r in result.risks if r.level >= RiskLevel.HIGH],
        }
        if result.weather:
            data["weather"] = {
                "wind_speed_ms": result.weather.wind_speed_ms,
                "wind_direction": result.weather.wind_direction,
                "wave_height_m": result.weather.wave_height_m,
                "visibility_km": result.weather.visibility_km,
                "precipitation": result.weather.precipitation,
                "risk_level": result.weather.risk_level().value,
            }
        if ship:
            data["ship"] = {
                "type": ship.ship_type.value,
                "name": ship.name,
                "draft": ship.draft,
                "mast_height": ship.mast_height,
                "max_speed": ship.max_speed,
            }
        if route:
            data["route_info"] = {
                "departure_port": route.departure_port,
                "arrival_port": route.arrival_port,
                "date": route.date,
                "waypoints": [{"name": w.name, "lat": w.lat, "lon": w.lon}
                              for w in route.waypoints],
            }
        if compare_data:
            data["comparison"] = compare_data.get("recommendation", "")
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _csv_report(self, result: CheckResult) -> str:
        lines = ["序号,风险等级,风险类别,位置,描述,建议"]
        for i, r in enumerate(sorted(result.risks, key=lambda x: x.level, reverse=True), 1):
            desc = r.description.replace(",", "，").replace("\n", " ")
            sug = r.suggestion.replace(",", "，").replace("\n", " ")
            loc = r.location.replace(",", "，")
            lines.append(f"{i},{r.level.value},{r.category.value},{loc},{desc},{sug}")
        return "\n".join(lines)
