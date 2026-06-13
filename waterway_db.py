import json
from typing import List, Optional
from models import ShoalFeature, BridgeFeature, SpeedZone, NavBanPeriod, Route, Waypoint, ShipProfile


class WaterwayDB:
    def __init__(self):
        self.shoals: List[ShoalFeature] = []
        self.bridges: List[BridgeFeature] = []
        self.speed_zones: List[SpeedZone] = []
        self.nav_bans: List[NavBanPeriod] = []
        self._load_default_data()

    def _load_default_data(self):
        self.shoals = [
            ShoalFeature("白茆沙浅滩", 31.65, 121.85, 3.5, 2.0),
            ShoalFeature("通州沙浅滩", 31.95, 120.95, 4.0, 1.5),
            ShoalFeature("福姜沙浅滩", 32.05, 120.45, 3.2, 1.8),
            ShoalFeature("江阴浅滩", 31.90, 120.25, 4.5, 1.2),
            ShoalFeature("南京大桥上游浅滩", 32.10, 118.75, 3.8, 1.5),
            ShoalFeature("芜湖水道浅滩", 31.35, 118.40, 3.0, 2.0),
            ShoalFeature("太子矶浅滩", 30.75, 117.70, 3.3, 1.5),
            ShoalFeature("鄱阳湖口浅滩", 29.75, 116.20, 2.8, 2.5),
            ShoalFeature("戴家洲浅滩", 30.35, 115.30, 3.6, 1.8),
            ShoalFeature("武汉白沙洲浅滩", 30.50, 114.25, 4.2, 1.5),
            ShoalFeature("嘉鱼浅滩", 30.05, 113.85, 3.4, 1.2),
            ShoalFeature("荆州浅滩", 30.35, 112.25, 3.0, 2.0),
            ShoalFeature("宜昌浅滩", 30.70, 111.30, 3.5, 1.5),
        ]
        self.bridges = [
            BridgeFeature("苏通长江大桥", 31.80, 121.00, 22.0, "设计通航净高22m"),
            BridgeFeature("沪苏通长江公铁大桥", 31.95, 120.65, 28.0, "设计通航净高28m"),
            BridgeFeature("江阴长江大桥", 31.95, 120.25, 50.0, "悬索桥净高充足"),
            BridgeFeature("泰州长江大桥", 32.20, 119.95, 50.0, "悬索桥净高充足"),
            BridgeFeature("润扬长江大桥", 32.20, 119.40, 50.0, "悬索桥净高充足"),
            BridgeFeature("南京长江大桥", 32.10, 118.78, 24.0, "历史限高24m，大型船舶需注意"),
            BridgeFeature("南京长江二桥", 32.12, 118.82, 30.0, "通航净高30m"),
            BridgeFeature("芜湖长江大桥", 31.35, 118.38, 24.0, "通航净高24m"),
            BridgeFeature("铜陵长江大桥", 30.85, 117.65, 24.0, "通航净高24m"),
            BridgeFeature("安庆长江大桥", 30.50, 117.05, 24.0, "通航净高24m"),
            BridgeFeature("九江长江大桥", 29.75, 116.00, 24.0, "通航净高24m"),
            BridgeFeature("黄石长江大桥", 30.25, 115.05, 24.0, "通航净高24m"),
            BridgeFeature("武汉长江大桥", 30.55, 114.28, 18.0, "历史桥梁净高仅18m，高桅杆船舶禁行"),
            BridgeFeature("武汉长江二桥", 30.58, 114.32, 22.0, "通航净高22m"),
            BridgeFeature("宜昌长江公路大桥", 30.65, 111.35, 24.0, "通航净高24m"),
        ]
        self.speed_zones = [
            SpeedZone("南京大桥航段", 32.05, 32.15, 118.70, 118.85, 8.0, "桥区航段限速"),
            SpeedZone("武汉港区", 30.50, 30.60, 114.20, 114.35, 6.0, "港区限速"),
            SpeedZone("上海港入口", 31.30, 31.45, 121.50, 121.90, 8.0, "港口入口限速"),
            SpeedZone("苏通大桥航段", 31.75, 31.85, 120.90, 121.10, 8.0, "桥区航段限速"),
            SpeedZone("芜湖港区", 31.30, 31.40, 118.30, 118.50, 6.0, "港区限速"),
            SpeedZone("九江港区", 29.70, 29.80, 115.95, 116.10, 6.0, "港区限速"),
        ]
        self.nav_bans = [
            NavBanPeriod("苏通大桥维护禁航", 31.75, 31.85, 120.90, 121.10,
                         2, 5, "桥区定期维护", months=[3, 6, 9, 12]),
            NavBanPeriod("南京大桥夜间禁航", 32.05, 32.15, 118.70, 118.85,
                         22, 5, "夜间通航管制", months=[]),
            NavBanPeriod("武汉大桥潮汐禁航", 30.53, 30.58, 114.25, 114.32,
                         0, 3, "低潮期禁航", months=[1, 2, 11, 12]),
            NavBanPeriod("上海港雾季禁航", 31.30, 31.45, 121.50, 121.90,
                         0, 6, "大雾能见度不足禁航", months=[3, 4]),
        ]

    def load_custom(self, filepath: str):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for s in data.get("shoals", []):
            self.shoals.append(ShoalFeature(**s))
        for b in data.get("bridges", []):
            self.bridges.append(BridgeFeature(**b))
        for sz in data.get("speed_zones", []):
            self.speed_zones.append(SpeedZone(**sz))
        for nb in data.get("nav_bans", []):
            self.nav_bans.append(NavBanPeriod(**nb))

    def find_nearby_shoals(self, lat: float, lon: float, radius_km: float = 3.0) -> List[ShoalFeature]:
        import math
        result = []
        for s in self.shoals:
            dlat = math.radians(s.lat - lat)
            dlon = math.radians(s.lon - lon)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(s.lat)) * math.sin(dlon / 2) ** 2
            dist = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            if dist <= radius_km + s.radius_km:
                result.append(s)
        return result

    def find_nearby_bridges(self, lat: float, lon: float, radius_km: float = 3.0) -> List[BridgeFeature]:
        import math
        result = []
        for b in self.bridges:
            dlat = math.radians(b.lat - lat)
            dlon = math.radians(b.lon - lon)
            a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(b.lat)) * math.sin(dlon / 2) ** 2
            dist = 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            if dist <= radius_km:
                result.append(b)
        return result

    def find_speed_zones(self, lat: float, lon: float) -> List[SpeedZone]:
        return [sz for sz in self.speed_zones
                if sz.lat_min <= lat <= sz.lat_max and sz.lon_min <= lon <= sz.lon_max]

    def find_nav_bans(self, lat: float, lon: float, month: int = 0, hour: int = -1) -> List[NavBanPeriod]:
        result = []
        for nb in self.nav_bans:
            if not (nb.lat_min <= lat <= nb.lat_max and nb.lon_min <= lon <= nb.lon_max):
                continue
            if nb.months and month > 0 and month not in nb.months:
                continue
            if hour >= 0:
                if nb.start_hour <= nb.end_hour:
                    if not (nb.start_hour <= hour < nb.end_hour):
                        continue
                else:
                    if not (hour >= nb.start_hour or hour < nb.end_hour):
                        continue
            result.append(nb)
        return result
