from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    _ORDER = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}

    def _rank(self):
        return {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}[self]

    def __lt__(self, other):
        return self._rank() < other._rank()

    def __le__(self, other):
        return self._rank() <= other._rank()

    def __gt__(self, other):
        return self._rank() > other._rank()

    def __ge__(self, other):
        return self._rank() >= other._rank()

    @property
    def display(self):
        icons = {RiskLevel.LOW: "🟢", RiskLevel.MEDIUM: "🟡", RiskLevel.HIGH: "🟠", RiskLevel.CRITICAL: "🔴"}
        return f"{icons[self]} {self.value.upper()}"


class RiskCategory(Enum):
    SHOAL = "浅滩风险"
    BRIDGE = "桥梁净高"
    SPEED_ZONE = "限速区域"
    NAV_BAN = "禁航时段"
    WEATHER = "气象风险"
    DRAFT = "吃水限制"
    GENERAL = "一般风险"


class ShipType(Enum):
    CARGO = "货船"
    TANKER = "油轮"
    CONTAINER = "集装箱船"
    BULK = "散货船"
    PASSENGER = "客船"
    TUG = "拖船"
    BARGE = "驳船"


@dataclass
class Waypoint:
    name: str
    lat: float
    lon: float
    arrival_time: Optional[str] = None
    speed_knots: Optional[float] = None
    notes: str = ""

    def distance_to(self, other: "Waypoint") -> float:
        import math
        R = 6371.0
        dlat = math.radians(other.lat - self.lat)
        dlon = math.radians(other.lon - self.lon)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(self.lat)) * math.cos(math.radians(other.lat))
             * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


@dataclass
class ShipProfile:
    ship_type: ShipType = ShipType.CARGO
    draft: float = 4.5
    mast_height: float = 18.0
    beam: float = 16.0
    length: float = 120.0
    max_speed: float = 12.0
    name: str = "默认船舶"


@dataclass
class Route:
    name: str
    waypoints: List[Waypoint] = field(default_factory=list)
    departure_port: str = ""
    arrival_port: str = ""
    date: str = ""

    def total_distance_nm(self) -> float:
        total = 0.0
        for i in range(len(self.waypoints) - 1):
            total += self.waypoints[i].distance_to(self.waypoints[i + 1])
        return total * 0.539957

    def estimated_time_hours(self, ship: ShipProfile) -> float:
        dist = self.total_distance_nm()
        avg_speed = ship.max_speed * 0.85
        if avg_speed <= 0:
            return float("inf")
        return dist / avg_speed


@dataclass
class RiskItem:
    level: RiskLevel
    category: RiskCategory
    description: str
    location: str = ""
    suggestion: str = ""
    segment_index: int = -1

    def to_dict(self):
        return {
            "level": self.level.value,
            "category": self.category.value,
            "description": self.description,
            "location": self.location,
            "suggestion": self.suggestion,
        }


@dataclass
class ShoalFeature:
    name: str
    lat: float
    lon: float
    min_depth: float
    radius_km: float = 1.0


@dataclass
class BridgeFeature:
    name: str
    lat: float
    lon: float
    clearance_height: float
    clearance_note: str = ""


@dataclass
class SpeedZone:
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    max_speed_knots: float
    reason: str = ""


@dataclass
class NavBanPeriod:
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float
    start_hour: int
    end_hour: int
    reason: str = ""
    months: List[int] = field(default_factory=list)


@dataclass
class WeatherCondition:
    wind_speed_ms: float
    wind_direction: int
    wave_height_m: float
    visibility_km: float
    precipitation: str = "无"
    description: str = ""

    def risk_level(self) -> RiskLevel:
        if self.wave_height_m > 3.0 or self.wind_speed_ms > 17.1 or self.visibility_km < 0.5:
            return RiskLevel.CRITICAL
        elif self.wave_height_m > 2.0 or self.wind_speed_ms > 10.7 or self.visibility_km < 1.0:
            return RiskLevel.HIGH
        elif self.wave_height_m > 1.0 or self.wind_speed_ms > 5.5 or self.visibility_km < 3.0:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


@dataclass
class CheckResult:
    route_name: str
    risks: List[RiskItem] = field(default_factory=list)
    total_distance_nm: float = 0.0
    estimated_time_hours: float = 0.0
    weather: Optional[WeatherCondition] = None

    def max_risk_level(self) -> RiskLevel:
        if not self.risks:
            return RiskLevel.LOW
        return max(self.risks, key=lambda r: r.level).level

    def risks_by_level(self) -> dict:
        result = {level: [] for level in RiskLevel}
        for r in self.risks:
            result[r.level].append(r)
        return result

    def summary(self) -> str:
        lines = []
        lines.append(f"航线: {self.route_name}")
        lines.append(f"总航程: {self.total_distance_nm:.1f} 海里")
        lines.append(f"预计用时: {self.estimated_time_hours:.1f} 小时")
        lines.append(f"最高风险等级: {self.max_risk_level().display}")
        by_level = self.risks_by_level()
        lines.append(f"风险统计: 严重 {len(by_level[RiskLevel.CRITICAL])} | "
                      f"高 {len(by_level[RiskLevel.HIGH])} | "
                      f"中 {len(by_level[RiskLevel.MEDIUM])} | "
                      f"低 {len(by_level[RiskLevel.LOW])}")
        return "\n".join(lines)
