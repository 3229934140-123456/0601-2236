import math
import random
from datetime import datetime
from typing import List, Optional
from models import (
    Route, ShipProfile, Waypoint, RiskItem, RiskLevel, RiskCategory,
    CheckResult, WeatherCondition
)
from waterway_db import WaterwayDB


class RiskEngine:
    SAFETY_MARGIN_SHOAL = 0.5
    SAFETY_MARGIN_BRIDGE = 1.0

    def __init__(self, db: WaterwayDB):
        self.db = db

    def check_route(self, route: Route, ship: ShipProfile,
                    weather: Optional[WeatherCondition] = None) -> CheckResult:
        risks: List[RiskItem] = []

        for i, wp in enumerate(route.waypoints):
            self._check_shoals(wp, ship, risks, i)
            self._check_bridges(wp, ship, risks, i)
            self._check_speed_zones(wp, ship, risks, i)
            self._check_nav_bans(wp, route, risks, i)
            self._check_draft_at_point(wp, ship, risks, i)

        if weather:
            self._check_weather(weather, ship, risks)

        self._check_route_continuity(route, ship, risks)

        return CheckResult(
            route_name=route.name,
            risks=risks,
            total_distance_nm=route.total_distance_nm(),
            estimated_time_hours=route.estimated_time_hours(ship),
            weather=weather,
        )

    def _check_shoals(self, wp: Waypoint, ship: ShipProfile,
                      risks: List[RiskItem], seg_idx: int):
        nearby = self.db.find_nearby_shoals(wp.lat, wp.lon, radius_km=3.0)
        for shoal in nearby:
            clearance = shoal.min_depth - ship.draft
            if clearance < 0:
                risks.append(RiskItem(
                    level=RiskLevel.CRITICAL,
                    category=RiskCategory.SHOAL,
                    description=f"航经 {shoal.name}，最小水深 {shoal.min_depth}m，"
                                f"船舶吃水 {ship.draft}m，严重搁浅风险",
                    location=wp.name,
                    suggestion=f"立即绕行避开 {shoal.name}，或减载至吃水小于 {shoal.min_depth}m",
                    segment_index=seg_idx,
                ))
            elif clearance < self.SAFETY_MARGIN_SHOAL:
                risks.append(RiskItem(
                    level=RiskLevel.HIGH,
                    category=RiskCategory.SHOAL,
                    description=f"航经 {shoal.name}，最小水深 {shoal.min_depth}m，"
                                f"富余水深仅 {clearance:.1f}m（安全裕度 {self.SAFETY_MARGIN_SHOAL}m）",
                    location=wp.name,
                    suggestion=f"减载降低吃水至 {shoal.min_depth - self.SAFETY_MARGIN_SHOAL:.1f}m 以下，"
                               f"或选择深水航道绕行 {shoal.name}",
                    segment_index=seg_idx,
                ))
            elif clearance < self.SAFETY_MARGIN_SHOAL * 2:
                risks.append(RiskItem(
                    level=RiskLevel.MEDIUM,
                    category=RiskCategory.SHOAL,
                    description=f"航经 {shoal.name}，水深 {shoal.min_depth}m，"
                                f"富余水深 {clearance:.1f}m，需谨慎驾驶",
                    location=wp.name,
                    suggestion=f"通过 {shoal.name} 时减速慢行，注意潮汐变化",
                    segment_index=seg_idx,
                ))

    def _check_bridges(self, wp: Waypoint, ship: ShipProfile,
                       risks: List[RiskItem], seg_idx: int):
        nearby = self.db.find_nearby_bridges(wp.lat, wp.lon, radius_km=2.0)
        for bridge in nearby:
            clearance = bridge.clearance_height - ship.mast_height
            if clearance < 0:
                risks.append(RiskItem(
                    level=RiskLevel.CRITICAL,
                    category=RiskCategory.BRIDGE,
                    description=f"通过 {bridge.name}，净高 {bridge.clearance_height}m，"
                                f"桅杆高度 {ship.mast_height}m，无法通过",
                    location=wp.name,
                    suggestion=f"选择其他航线绕行 {bridge.name}，或降低桅杆/等水位上涨",
                    segment_index=seg_idx,
                ))
            elif clearance < self.SAFETY_MARGIN_BRIDGE:
                risks.append(RiskItem(
                    level=RiskLevel.HIGH,
                    category=RiskCategory.BRIDGE,
                    description=f"通过 {bridge.name}，净高 {bridge.clearance_height}m，"
                                f"桅杆高度 {ship.mast_height}m，富余仅 {clearance:.1f}m",
                    location=wp.name,
                    suggestion=f"通过 {bridge.name} 前确认水位，减速慢行，必要时等待高水位时段",
                    segment_index=seg_idx,
                ))
            elif clearance < self.SAFETY_MARGIN_BRIDGE * 2:
                risks.append(RiskItem(
                    level=RiskLevel.MEDIUM,
                    category=RiskCategory.BRIDGE,
                    description=f"通过 {bridge.name}，净高 {bridge.clearance_height}m，"
                                f"富余 {clearance:.1f}m，需注意水位变化",
                    location=wp.name,
                    suggestion=f"通过 {bridge.name} 时居中航行，注意观察净高标尺",
                    segment_index=seg_idx,
                ))

    def _check_speed_zones(self, wp: Waypoint, ship: ShipProfile,
                           risks: List[RiskItem], seg_idx: int):
        zones = self.db.find_speed_zones(wp.lat, wp.lon)
        for zone in zones:
            if ship.max_speed > zone.max_speed_knots:
                risks.append(RiskItem(
                    level=RiskLevel.MEDIUM,
                    category=RiskCategory.SPEED_ZONE,
                    description=f"进入限速区 {zone.name}，限速 {zone.max_speed_knots} 节"
                                f"（{zone.reason}）",
                    location=wp.name,
                    suggestion=f"在 {zone.name} 航段将船速控制在 {zone.max_speed_knots} 节以下",
                    segment_index=seg_idx,
                ))

    def _check_nav_bans(self, wp: Waypoint, route: Route,
                        risks: List[RiskItem], seg_idx: int):
        month = 0
        hour = -1
        if route.date:
            try:
                dt = datetime.strptime(route.date, "%Y-%m-%d")
                month = dt.month
            except ValueError:
                pass
        if wp.arrival_time:
            try:
                h = int(wp.arrival_time.split(":")[0])
                hour = h
            except (ValueError, IndexError):
                pass
        bans = self.db.find_nav_bans(wp.lat, wp.lon, month=month, hour=hour)
        for ban in bans:
            risks.append(RiskItem(
                level=RiskLevel.HIGH,
                category=RiskCategory.NAV_BAN,
                description=f"航经禁航区域 {ban.name}（{ban.reason}），"
                            f"禁航时段 {ban.start_hour:02d}:00-{ban.end_hour:02d}:00",
                location=wp.name,
                suggestion=f"调整开航时间避开 {ban.name} 禁航时段，或选择替代航线",
                segment_index=seg_idx,
            ))

    def _check_draft_at_point(self, wp: Waypoint, ship: ShipProfile,
                              risks: List[RiskItem], seg_idx: int):
        if ship.draft > 9.0:
            risks.append(RiskItem(
                level=RiskLevel.MEDIUM,
                category=RiskCategory.DRAFT,
                description=f"船舶吃水 {ship.draft}m 较大，部分内河航段可能受限",
                location=wp.name,
                suggestion="确认沿途航道维护水深满足吃水要求，必要时申请深水航道",
                segment_index=seg_idx,
            ))

    def _check_weather(self, weather: WeatherCondition, ship: ShipProfile,
                       risks: List[RiskItem]):
        level = weather.risk_level()
        if level == RiskLevel.CRITICAL:
            risks.append(RiskItem(
                level=RiskLevel.CRITICAL,
                category=RiskCategory.WEATHER,
                description=f"恶劣天气: 风速 {weather.wind_speed_ms}m/s, "
                            f"浪高 {weather.wave_height_m}m, "
                            f"能见度 {weather.visibility_km}km — 建议停航",
                location="全线",
                suggestion="推迟开航，等待天气好转，或选择避风锚地待命",
            ))
        elif level == RiskLevel.HIGH:
            risks.append(RiskItem(
                level=RiskLevel.HIGH,
                category=RiskCategory.WEATHER,
                description=f"不良天气: 风速 {weather.wind_speed_ms}m/s, "
                            f"浪高 {weather.wave_height_m}m, "
                            f"能见度 {weather.visibility_km}km",
                location="全线",
                suggestion="加固绑扎，降低航速，加强瞭望，必要时就近避风",
            ))
        elif level == RiskLevel.MEDIUM:
            risks.append(RiskItem(
                level=RiskLevel.MEDIUM,
                category=RiskCategory.WEATHER,
                description=f"天气注意: 风速 {weather.wind_speed_ms}m/s, "
                            f"浪高 {weather.wave_height_m}m, "
                            f"能见度 {weather.visibility_km}km",
                location="全线",
                suggestion="注意横风横浪航段，保持适当航速",
            ))

    def _check_route_continuity(self, route: Route, ship: ShipProfile,
                                risks: List[RiskItem]):
        if len(route.waypoints) < 2:
            risks.append(RiskItem(
                level=RiskLevel.MEDIUM,
                category=RiskCategory.GENERAL,
                description="航线点不足两个，无法构成有效航线",
                suggestion="至少需要起止两个航线点",
            ))
            return
        for i in range(len(route.waypoints) - 1):
            dist = route.waypoints[i].distance_to(route.waypoints[i + 1])
            if dist > 200:
                risks.append(RiskItem(
                    level=RiskLevel.MEDIUM,
                    category=RiskCategory.GENERAL,
                    description=f"航段 {route.waypoints[i].name}→{route.waypoints[i+1].name} "
                                f"跨度 {dist:.0f}km，建议增加中间航路点",
                    location=f"{route.waypoints[i].name}-{route.waypoints[i+1].name}",
                    suggestion="在长航段中增加转向点或检查点，便于风险逐段评估",
                    segment_index=i,
                ))

    def compare_routes(self, route_a: Route, route_b: Route,
                       ship: ShipProfile,
                       weather: Optional[WeatherCondition] = None) -> dict:
        result_a = self.check_route(route_a, ship, weather)
        result_b = self.check_route(route_b, ship, weather)
        return {
            "route_a": {"name": route_a.name, "result": result_a},
            "route_b": {"name": route_b.name, "result": result_b},
            "recommendation": self._recommend(result_a, result_b, route_a, route_b),
        }

    def _recommend(self, res_a: CheckResult, res_b: CheckResult,
                   route_a: Route, route_b: Route) -> str:
        score_a = self._score(res_a)
        score_b = self._score(res_b)
        lines = []
        if score_a < score_b:
            lines.append(f"推荐航线: {route_a.name}（综合风险评分更低）")
        elif score_b < score_a:
            lines.append(f"推荐航线: {route_b.name}（综合风险评分更低）")
        else:
            lines.append("两条航线综合风险评分相近")
        lines.append(f"  {route_a.name}: 评分 {score_a}, "
                      f"风险项 {len(res_a.risks)}, "
                      f"航程 {res_a.total_distance_nm:.1f}nm, "
                      f"用时 {res_a.estimated_time_hours:.1f}h")
        lines.append(f"  {route_b.name}: 评分 {score_b}, "
                      f"风险项 {len(res_b.risks)}, "
                      f"航程 {res_b.total_distance_nm:.1f}nm, "
                      f"用时 {res_b.estimated_time_hours:.1f}h")
        return "\n".join(lines)

    def _score(self, result: CheckResult) -> int:
        weights = {RiskLevel.LOW: 1, RiskLevel.MEDIUM: 3, RiskLevel.HIGH: 8, RiskLevel.CRITICAL: 20}
        return sum(weights.get(r.level, 0) for r in result.risks)
