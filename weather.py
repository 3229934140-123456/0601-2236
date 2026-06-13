import math
import random
from datetime import datetime
from typing import Optional
from models import WeatherCondition, RiskLevel


class WeatherService:
    SEASONAL_PROFILES = {
        "spring": {"wind_range": (2.0, 8.0), "wave_range": (0.3, 1.2), "vis_range": (3.0, 15.0),
                   "precip_options": ["无", "小雨", "雾"]},
        "summer": {"wind_range": (3.0, 12.0), "wave_range": (0.5, 2.5), "vis_range": (2.0, 20.0),
                   "precip_options": ["无", "雷阵雨", "暴雨", "大雨"]},
        "autumn": {"wind_range": (2.5, 10.0), "wave_range": (0.4, 1.8), "vis_range": (3.0, 18.0),
                   "precip_options": ["无", "小雨", "雾"]},
        "winter": {"wind_range": (4.0, 15.0), "wave_range": (0.8, 3.0), "vis_range": (1.0, 10.0),
                   "precip_options": ["无", "小雪", "雾", "大风"]},
    }

    def get_weather(self, date_str: str, lat: float, lon: float,
                    port: str = "") -> WeatherCondition:
        month = 6
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                month = dt.month
            except ValueError:
                pass

        if month in (3, 4, 5):
            season = "spring"
        elif month in (6, 7, 8):
            season = "summer"
        elif month in (9, 10, 11):
            season = "autumn"
        else:
            season = "winter"

        profile = self.SEASONAL_PROFILES[season]
        seed = hash(f"{date_str}-{lat:.2f}-{lon:.2f}-{port}")
        rng = random.Random(seed)

        wind = round(rng.uniform(*profile["wind_range"]), 1)
        wave = round(rng.uniform(*profile["wave_range"]), 1)
        vis = round(rng.uniform(*profile["vis_range"]), 1)
        wind_dir = rng.randint(0, 359)
        precip = rng.choice(profile["precip_options"])

        desc_parts = []
        if wind > 10.7:
            desc_parts.append("大风")
        elif wind > 5.5:
            desc_parts.append("有风")
        if wave > 2.0:
            desc_parts.append("大浪")
        if vis < 1.0:
            desc_parts.append("浓雾")
        elif vis < 3.0:
            desc_parts.append("轻雾")
        if precip != "无":
            desc_parts.append(precip)
        if not desc_parts:
            desc_parts.append("天气良好")
        description = "，".join(desc_parts)

        return WeatherCondition(
            wind_speed_ms=wind,
            wind_direction=wind_dir,
            wave_height_m=wave,
            visibility_km=vis,
            precipitation=precip,
            description=description,
        )

    def get_route_weather(self, date_str: str,
                          waypoints: list, port: str = "") -> list:
        results = []
        for wp in waypoints:
            w = self.get_weather(date_str, wp.lat, wp.lon, port)
            results.append({"waypoint": wp.name, "weather": w})
        return results

    def format_weather(self, weather: WeatherCondition) -> str:
        lines = [
            f"  风速: {weather.wind_speed_ms} m/s  风向: {weather.wind_direction}°",
            f"  浪高: {weather.wave_height_m} m",
            f"  能见度: {weather.visibility_km} km",
            f"  降水: {weather.precipitation}",
            f"  概况: {weather.description}",
            f"  风险等级: {weather.risk_level().display}",
        ]
        return "\n".join(lines)

    @staticmethod
    def wind_dir_name(deg: int) -> str:
        dirs = ["北", "北东北", "东北", "东东北", "东", "东东南", "东南", "南东南",
                "南", "南西南", "西南", "西西南", "西", "西西北", "西北", "北西北"]
        idx = round(deg / 22.5) % 16
        return dirs[idx]
