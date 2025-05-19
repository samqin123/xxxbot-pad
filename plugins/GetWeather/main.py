import sys
import subprocess
import importlib.util
import asyncio
import logging
import time
import os
import tomllib
import aiohttp
import jwt
import jieba

from WechatAPI import WechatAPIClient
from utils.decorators import *
from utils.plugin_base import PluginBase

# 检查并安装必要的依赖
def check_and_install_dependencies():
    """检查并安装必要的依赖"""
    required_packages = {
        'aiohttp': 'aiohttp',
        'PyJWT': 'PyJWT',
        'cryptography': 'cryptography',
        'jieba': 'jieba'
    }

    for package, import_name in required_packages.items():
        if importlib.util.find_spec(import_name) is None:
            print(f"正在安装依赖: {package}")
            try:
                subprocess.check_call([
                    sys.executable, 
                    "-m", 
                    "pip", 
                    "install", 
                    package,
                    "-i", 
                    "https://pypi.tuna.tsinghua.edu.cn/simple",
                    "--trusted-host", 
                    "pypi.tuna.tsinghua.edu.cn"
                ])
                print(f"成功安装 {package}")
            except subprocess.CalledProcessError as e:
                print(f"安装 {package} 失败: {str(e)}")
                raise RuntimeError(f"无法安装必要的依赖: {package}")

# 安装依赖
check_and_install_dependencies()

class GetWeather(PluginBase):
    """天气查询插件"""
    
    name = "GetWeather"
    description = "获取实时天气和天气预报"
    author = "samqin-小x宝社区-服务癌症和罕见病患者的开源公益社区欢迎加入！"
    version = "1.0.10"
    
    # Change Log
    changes = [
        "1.0.10: 更新JWT生成逻辑，使用新的API认证方式",
        "1.0.9: 添加依赖版本检查",
        "1.0.8: 优化依赖安装逻辑",
        "1.0.7: 修复依赖导入顺序问题",
        "1.0.6: 更新JWT生成方法",
        "1.0.5: 添加JWT生成功能",
        "1.0.4: 添加自动安装依赖功能",
        "1.0.3: 添加天气API调用",
        "1.0.2: 添加城市查询功能",
        "1.0.1: 添加基础命令解析",
        "1.0.0: 初始版本"
    ]

    def __init__(self):
        """初始化插件"""
        super().__init__()
        
        # 加载配置
        with open("plugins/GetWeather/config.toml", "rb") as f:
            plugin_config = tomllib.load(f)
        
        config = plugin_config.get("GetWeather", {})
        if not config:
            raise ValueError("配置文件中缺少GetWeather节")
            
        # 验证必要的配置项
        required_configs = ["api-host", "api-key", "jwt-kid", "jwt-sub"]
        missing_configs = [key for key in required_configs if key not in config]
        if missing_configs:
            raise ValueError(f"配置文件缺少必要的配置项: {', '.join(missing_configs)}")
            
        # 设置配置
        self.api_host = config["api-host"]
        self.private_key = config["api-key"]
        self.jwt_kid = config["jwt-kid"]
        self.jwt_sub = config["jwt-sub"]
        
        # 设置日志
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.INFO)
        
        # 如果没有处理器，添加一个
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
        self.logger.info(f"插件 {self.name} v{self.version} 初始化完成")

    def generate_jwt_token(self):
        """生成JWT token"""
        try:
            # 构建payload
            payload = {
                'iat': int(time.time()) - 30,  # 当前时间前30秒
                'exp': int(time.time()) + 900,  # 15分钟后过期
                'sub': self.jwt_sub
            }
            
            # 构建headers
            headers = {
                'kid': self.jwt_kid
            }
            
            # 记录详细信息
            self.logger.info("JWT生成信息:")
            self.logger.info(f"当前时间戳: {int(time.time())}")
            self.logger.info(f"iat时间戳: {payload['iat']}")
            self.logger.info(f"exp时间戳: {payload['exp']}")
            self.logger.info(f"JWT Headers: {headers}")
            self.logger.info(f"JWT Payload: {payload}")
            
            # 生成token
            token = jwt.encode(payload, self.private_key, algorithm='EdDSA', headers=headers)
            self.logger.info(f"生成的Token: {token}")
            return token
            
        except Exception as e:
            self.logger.error(f"生成JWT token失败: {str(e)}")
            raise

    @on_text_message
    async def handle_text(self, bot: WechatAPIClient, message: dict):
        """处理文本消息"""
        if "天气" not in message["Content"]:
            return

        # 如果消息被其他插件处理过，直接返回
        if message.get("_processed", False):
            return

        # 标记消息已处理
        message["_processed"] = True

        command = list(jieba.cut(message["Content"]))

        if len(command) == 1:
            await bot.send_at_message(message["FromWxid"], "\n请指定城市名称，例如：天气 北京", [message["SenderWxid"]])
            return
        elif len(command) > 3:
            return

        # 移除"天气"关键词
        command = [word for word in command if word != "天气"]
        request_loc = "".join(command)

        try:
            # 生成JWT token
            token = self.generate_jwt_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate, br"
            }

            # 使用JWT认证请求城市查询API
            geo_api_url = f'{self.api_host}/geo/v2/city/lookup?location={request_loc}'
            self.logger.info(f"请求城市查询API: {geo_api_url}")

            async with aiohttp.ClientSession() as session:
                async with session.get(geo_api_url, headers=headers) as response:
                    if response.status != 200:
                        self.logger.error(f"城市查询API请求失败: {response.status}")
                        await bot.send_at_message(message["FromWxid"], "\n⚠️请求失败，请稍后重试", [message["SenderWxid"]])
                        return
                    
                    geoapi_json = await response.json()
                    self.logger.debug(f"城市查询API响应: {geoapi_json}")

            if geoapi_json['code'] == '404':
                self.logger.info(f"未找到城市: {request_loc}")
                await bot.send_at_message(message["FromWxid"], "\n⚠️查无此地！", [message["SenderWxid"]])
                return

            elif geoapi_json['code'] != '200':
                self.logger.error(f"城市查询API请求失败: {geoapi_json}")
                await bot.send_at_message(message["FromWxid"], f"\n⚠️请求失败\n{geoapi_json}", [message["SenderWxid"]])
                return

            country = geoapi_json["location"][0]["country"]
            adm1 = geoapi_json["location"][0]["adm1"]
            adm2 = geoapi_json["location"][0]["adm2"]
            city_id = geoapi_json["location"][0]["id"]

            # 请求现在天气api
            now_weather_api_url = f'{self.api_host}/v7/weather/now?location={city_id}'
            async with aiohttp.ClientSession() as session:
                async with session.get(now_weather_api_url, headers=headers) as response:
                    if response.status != 200:
                        self.logger.error(f"现在天气API请求失败: {response.status}")
                        await bot.send_at_message(message["FromWxid"], "\n⚠️获取天气信息失败，请稍后重试", [message["SenderWxid"]])
                        return
                    now_weather_api_json = await response.json()

            # 请求预报天气api
            weather_forecast_api_url = f'{self.api_host}/v7/weather/7d?location={city_id}'
            async with aiohttp.ClientSession() as session:
                async with session.get(weather_forecast_api_url, headers=headers) as response:
                    if response.status != 200:
                        self.logger.error(f"预报天气API请求失败: {response.status}")
                        await bot.send_at_message(message["FromWxid"], "\n⚠️获取天气预报失败，请稍后重试", [message["SenderWxid"]])
                        return
                    weather_forecast_api_json = await response.json()

            out_message = self.compose_weather_message(country, adm1, adm2, now_weather_api_json, weather_forecast_api_json)
            await bot.send_at_message(message["FromWxid"], "\n" + out_message, [message["SenderWxid"]])

        except Exception as e:
            self.logger.error(f"处理天气查询失败: {str(e)}")
            await bot.send_at_message(message["FromWxid"], f"\n⚠️处理天气查询失败: {str(e)}", [message["SenderWxid"]])
        
        # 返回 False 表示消息已处理，不需要传递给其他插件
        return False

    @staticmethod
    def compose_weather_message(country, adm1, adm2, now_weather_api_json, weather_forecast_api_json):
        """构建天气信息消息"""
        update_time = now_weather_api_json['updateTime']
        now = now_weather_api_json['now']
        
        message = (
            f"----- 小胰宝助手提醒您关注天气 -----\n"
            f"{country}{adm1}{adm2} 实时天气☁️\n"
            f"⏰更新时间：{update_time}\n\n"
            f"🌡️当前温度：{now['temp']}℃\n"
            f"🌡️体感温度：{now['feelsLike']}℃\n"
            f"☁️天气：{now['text']}\n"
            f"☀️紫外线指数：{weather_forecast_api_json['daily'][0]['uvIndex']}\n"
            f"🌬️风向：{now['windDir']}\n"
            f"🌬️风力：{now['windScale']}级\n"
            f"💦湿度：{now['humidity']}%\n"
            f"🌧️降水量：{now['precip']}mm/h\n"
            f"👀能见度：{now['vis']}km\n\n"
            f"☁️未来3天 {adm2} 天气：\n"
        )
        
        for day in weather_forecast_api_json['daily'][1:4]:
            date = '.'.join([i.lstrip('0') for i in day['fxDate'].split('-')[1:]])
            weather = day['textDay']
            max_temp = day['tempMax']
            min_temp = day['tempMin']
            uv_index = day['uvIndex']
            message += f'{date} {weather} 最高🌡️{max_temp}℃ 最低🌡️{min_temp}℃ ☀️紫外线:{uv_index}\n'

        return message
