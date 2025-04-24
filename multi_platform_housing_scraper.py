#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os
import re
import webbrowser
import logging
from datetime import datetime
from fake_useragent import UserAgent
import json
import sys
import numpy as np
import urllib.parse
import traceback
from openpyxl.utils import get_column_letter

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("housing_scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("housing_scraper")

# 设置更详细的调试级别
def set_debug_level(debug=False):
    """设置日志级别
    
    参数:
        debug: 是否开启调试模式
    """
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("调试模式已启用")
    else:
        logger.setLevel(logging.INFO)
        
# 自定义异常类
class ScraperException(Exception):
    """爬虫异常基类"""
    pass
    
class VerificationException(ScraperException):
    """验证失败异常"""
    pass
    
class ParsingException(ScraperException):
    """解析失败异常"""
    pass
    
class NetworkException(ScraperException):
    """网络请求异常"""
    pass

# 尝试导入自动验证处理器
try:
    from auto_verification import AutoVerificationHandler
    AUTO_VERIFICATION_AVAILABLE = True
except ImportError:
    AUTO_VERIFICATION_AVAILABLE = False
    logger.warning("自动验证模块未安装，验证码将需要手动处理")

# 城市代码映射表
CITY_CODES = {
    '郑州': 'zz',
    '北京': 'bj',
    '上海': 'sh',
    '广州': 'gz',
    '深圳': 'sz',
    '成都': 'cd',
    '杭州': 'hz',
    '武汉': 'wh',
    '南京': 'nj',
    '西安': 'xa'
}

# 房源类型URL模板
URL_TEMPLATES = {
    '安居客': {
        '新房': 'https://{city}.anjuke.com/new/all/p{page}',
        '二手房': 'https://{city}.anjuke.com/sale/p{page}',
        '租房': 'https://{city}.anjuke.com/rent/p{page}'
    },
    '58同城': {
        'new': 'https://{city}.58.com/loupan/',
        'second': 'https://{city}.58.com/ershoufang/',
        'rent': 'https://{city}.58.com/zufang/'
    },
    '贝壳找房': {
        '新房': 'https://{city}.fang.ke.com/loupan/pg{page}/',
        '二手房': 'https://{city}.ke.com/ershoufang/pg{page}/',
        '租房': 'https://{city}.zu.ke.com/zufang/pg{page}/'
    },
    '链家': {
        '新房': 'https://{city}.fang.lianjia.com/loupan/pg{page}/',
        '二手房': 'https://{city}.lianjia.com/ershoufang/pg{page}/',
        '租房': 'https://{city}.lianjia.com/zufang/pg{page}/'
    }
}

class MultiPlatformHousingScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.headers = {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        
        # 创建存放数据的目录
        self.data_dir = 'housing_data'
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # 设置输出目录
        self.output_dir = 'output_data'
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # 调试目录（已禁用保存）
        self.debug_dir = 'debug_pages'
        
        # 存储搜索结果
        self.house_data = []
        
        # 支持的平台
        self.platforms = {
            '1': {'name': '安居客', 'scraper': self.scrape_anjuke},
            '2': {'name': '58同城', 'scraper': self.scrape_58},
            '3': {'name': '贝壳找房', 'scraper': self.scrape_beike},
            '4': {'name': '链家', 'scraper': self.scrape_lianjia}
        }
        
        # 房源类型
        self.house_types = {
            '1': '新房',
            '2': '二手房',
            '3': '租房'
        }
        
        # 初始化自动验证处理器
        self.auto_verification_handler = None
        if AUTO_VERIFICATION_AVAILABLE:
            try:
                self.auto_verification_handler = AutoVerificationHandler(headless=False)
                logger.info("自动验证功能已启用")
            except Exception as e:
                logger.error(f"初始化自动验证处理器失败: {e}")
    
    def get_random_delay(self):
        """生成随机延迟时间，避免被网站反爬措施检测"""
        return random.uniform(1, 3)
    
    def update_headers(self):
        """更新随机User-Agent"""
        self.headers['User-Agent'] = self.ua.random
        return self.headers
    
    def check_verification(self, response_text, platform=None, url=None):
        """检查页面是否需要验证
        
        参数:
            response_text: 页面响应文本
            platform: 平台名称（可选）
            url: 请求的URL（可选）
            
        返回:
            bool: 是否需要验证
        """
        # 如果提供了URL，尝试从URL中推断平台
        if not platform and url:
            if "anjuke.com" in url:
                platform = "anjuke"
            elif "58.com" in url:
                platform = "58"
            elif "ke.com" in url or "beike" in url:
                platform = "beike"
            elif "lianjia.com" in url:
                platform = "lianjia"
        
        # 平台特定的验证检测
        if platform:
            if platform == "anjuke":
                # 安居客特定的验证检测
                anjuke_verification_keywords = [
                    "verify.anjuke.com", "安居客验证", "滑动完成拼图", "拖动滑块",
                    "请完成安全验证", "智能检测", "人机识别", "verify-slider"
                ]
                
                # 检测明确的验证页面URL和元素
                if "verify.anjuke.com" in response_text or "captcha-app" in response_text:
                    logger.info(f"检测到安居客验证页面URL")
                    return True
                
                # 更谨慎地检测关键词，至少需要两个关键词同时出现
                keyword_count = 0
                for keyword in anjuke_verification_keywords:
                    if keyword in response_text:
                        keyword_count += 1
                        logger.debug(f"检测到安居客验证关键词: {keyword}")
                
                if keyword_count >= 2:
                    logger.info(f"检测到多个安居客验证关键词: {keyword_count}个")
                    return True
                
                # 检查响应长度并查找正常页面元素的存在性
                if len(response_text) < 3000 and "anjuke.com" in response_text:
                    # 确保页面上有房源特征元素
                    normal_elements = [
                        "list-item", "houselist-item", "house-details", "item-mod",
                        "property-content", "property-info", "anjuke-logo", "房源信息", 
                        "property-item", "key-list"
                    ]
                    
                    found_elements = 0
                    for element in normal_elements:
                        if element in response_text:
                            found_elements += 1
                    
                    # 如果正常页面元素很少，可能是验证页面
                    if found_elements <= 2:
                        logger.warning(f"安居客页面缺少正常房源元素({found_elements}/{len(normal_elements)})，可能是验证页面")
                        
                        # 额外检查，验证页面通常包含的元素
                        verification_specific = ["验证", "captcha", "滑动", "拖动", "安全检测"]
                        for element in verification_specific:
                            if element in response_text:
                                logger.warning(f"安居客页面包含验证特征元素: {element}")
                                return True
                    else:
                        logger.info(f"安居客页面包含 {found_elements} 个正常元素，可能不是验证页面")
                
                return False
            
            elif platform == "58":
                # 58同城特定的验证检测
                tc58_verification_keywords = [
                    "callback.58.com/antibot", "validate.58.com", "安全认证",
                    "滑动验证", "请完成验证", "安全检测", "captcha.58.com"
                ]
                
                for keyword in tc58_verification_keywords:
                    if keyword in response_text:
                        logger.info(f"检测到58同城验证关键词: {keyword}")
                        return True
                
                # 检查58同城特有的验证页面特征
                if "antirobot" in response_text or "security-verification" in response_text:
                    logger.warning("58同城页面包含验证元素")
                    return True
                    
                return False
            
            elif platform == "beike" or platform == "lianjia":
                # 贝壳找房/链家特定的验证检测
                beike_verification_keywords = [
                    "captcha.lianjia", "verify.ke.com", "滑动验证", "拖动滑块",
                    "security-check", "human-verify", "验证中心", "人机验证",
                    "本次访问已触发人机验证", "请按指示操作", "CAPTCHA"
                ]
                
                # 检测明确的验证页面
                if "captcha.lianjia" in response_text or "verify.ke.com" in response_text:
                    logger.info(f"检测到链家/贝壳验证页面URL")
                    return True
                
                # 检测关键词
                for keyword in beike_verification_keywords:
                    if keyword in response_text:
                        logger.info(f"检测到链家/贝壳验证关键词: {keyword}")
                        return True
                
                # 检查页面内容长度和特征
                if len(response_text) < 5000 and ("ke.com" in response_text or "lianjia.com" in response_text):
                    # 链家/贝壳的验证页面通常非常短，并且缺少正常页面元素
                    normal_elements = ["ershoufang", "loupan", "zufang", "sellListContent", 
                                       "house-lst", "resblock-list", "resblock-name", "price"]
                    
                    found_elements = 0
                    for element in normal_elements:
                        if element in response_text:
                            found_elements += 1
                    
                    # 如果找不到足够多的正常元素，可能是验证页面
                    if found_elements <= 1:
                        # 额外验证：验证页面通常包含这些元素
                        captcha_elements = ["验证", "captcha", "verify", "人机", "滑动", "滑块"]
                        for element in captcha_elements:
                            if element in response_text:
                                logger.warning(f"链家/贝壳页面缺少正常元素且包含验证元素: {element}")
                                return True
                        
                        logger.warning(f"链家/贝壳页面内容异常简短且缺少正常元素")
                        if "<!DOCTYPE html>" in response_text and len(response_text.strip()) < 1000:
                            logger.warning("链家/贝壳页面可能是空白验证页面")
                            return True
                    else:
                        logger.info(f"链家/贝壳页面包含{found_elements}个正常元素，可能不是验证页面")
                
                return False
        
        # 通用验证词汇（所有平台都适用）
        verification_keywords = [
            "验证码", "人机验证", "安全验证", "滑动验证", "captcha", "verify", 
            "verification", "security check", "人机识别", "拖动滑块", "拼图",
            "请完成下列验证", "请进行验证", "安全检查", "安全认证", "请证明",
            "滑动完成拼图", "rotate", "旋转", "点击", "滑块", "slider"
        ]
        
        # HTML元素检测
        verification_elements = [
            'id="captcha"', 'class="captcha"', 'id="verify"', 'class="verify"',
            'nc_scale', 'nc-lang-cnt', 'class="slider"', 'id="slider"',
            'class="verification"', 'id="verification"', 'class="validate"',
            'geetest', 'class="gt_slider"', 'class="JDJRV-slide"', 'yidun_slider',
            'class="shumei_captcha"', 'class="vaptcha"', '网易易盾', 'tencent_captcha',
            'name="captcha"', 'class="puzzle"', 'class="antirobot"', 'callback.58.com/antibot'
        ]
        
        # 检查URL重定向
        verification_urls = [
            "callback.58.com/antibot", 
            "verify.anjuke.com", 
            "captcha", 
            "verify",
            "security-check",
            "validate.58.com"
        ]
        
        # 检查页面文本中的关键词
        for keyword in verification_keywords:
            if keyword in response_text:
                logger.info(f"检测到验证关键词: {keyword}")
                return True
                
        # 检查HTML元素
        for element in verification_elements:
            if element in response_text:
                logger.info(f"检测到验证元素: {element}")
                return True
                
        # 检查可能的重定向URL
        for url in verification_urls:
            if url in response_text:
                logger.info(f"检测到验证URL: {url}")
                return True
                
        # 检查内容长度，过短的页面很可能是验证页面
        if len(response_text) < 2000 and ("58.com" in response_text or "anjuke.com" in response_text):
            logger.warning(f"页面内容异常简短 ({len(response_text)} 字符)，可能是验证页面")
            
            # 进一步检查是否缺少正常页面应有的内容
            normal_content_markers = [
                "房源", "出租", "出售", "价格", "平米", "户型", "小区", 
                "房屋", "中介", "联系", "地址", "楼层", "二手房", "租房"
            ]
            
            # 检查常见的房源信息是否存在
            missing_markers = [marker for marker in normal_content_markers if marker not in response_text]
            if len(missing_markers) > len(normal_content_markers) / 2:
                logger.warning(f"页面缺少房源关键信息，可能是验证页面, 缺失标记: {missing_markers}")
                return True
        
        return False
    
    def handle_verification(self, platform=None, url=None):
        """处理验证码
        
        参数:
            platform: 平台名称，如"anjuke", "58"等
            url: 需要验证的URL
            
        返回:
            bool: 验证是否成功
        """
        if not url and platform:
            # 如果提供了平台但没有URL，尝试构造一个测试URL
            platforms_urls = {
                "anjuke": "https://www.anjuke.com/",
                "58": "https://www.58.com/",
                "beike": "https://www.ke.com/",
                "lianjia": "https://www.lianjia.com/"
            }
            url = platforms_urls.get(platform, "")
            
        if not url:
            logger.error("无法处理验证，未提供URL")
            return False
        
        # 确定平台类型，如果未提供
        if not platform:
            if "anjuke.com" in url:
                platform = "anjuke"
                logger.info("检测到安居客验证页面")
            elif "58.com" in url:
                platform = "58"
                logger.info("检测到58同城验证页面")
            elif "ke.com" in url or "beike" in url:
                platform = "beike"
                logger.info("检测到贝壳找房验证页面")
            elif "lianjia.com" in url:
                platform = "lianjia"
                logger.info("检测到链家验证页面")
        
        max_attempts = 2  # 增加到2次尝试
            
        # 如果启用了自动验证，尝试自动处理
        if self.auto_verification_handler:
            for attempt in range(max_attempts):
                logger.info(f"检测到网站需要人机验证，尝试自动验证 (尝试 {attempt+1}/{max_attempts})...")
                
                # 传递平台信息给验证处理器
                verification_success = False
                
                if platform == "anjuke":
                    # 安居客验证通常是滑块，需要特殊处理
                    verification_success = self.auto_verification_handler.handle_verification(url, platform)
                    logger.info("正在使用专门的安居客验证处理")
                elif platform == "58":
                    # 58同城验证通常是点选或滑块
                    verification_success = self.auto_verification_handler.handle_verification(url, platform)
                    logger.info("正在使用专门的58同城验证处理")
                elif platform in ["beike", "lianjia"]:
                    # 贝壳/链家验证通常是滑块
                    verification_success = self.auto_verification_handler.handle_verification(url, platform)
                    logger.info("正在使用专门的贝壳/链家验证处理")
                else:
                    # 其他平台使用通用验证处理
                    verification_success = self.auto_verification_handler.handle_verification(url, platform)
                
                if verification_success:
                    logger.info(f"{platform if platform else '未知平台'}自动验证成功")
                    
                    # 使用验证成功后的cookies更新请求头
                    cookies_dict = self.auto_verification_handler.get_cookies_dict()
                    if cookies_dict:
                        # 保存完整的cookies信息而不是只取部分
                        cookies_str = '; '.join([f"{k}={v}" for k, v in cookies_dict.items()])
                        self.headers.update({'Cookie': cookies_str})
                        logger.info(f"已更新Cookie: {len(cookies_dict)}个cookie值")
                        
                        # 更新User-Agent，匹配浏览器环境
                        browser_ua = self.auto_verification_handler.driver.execute_script("return navigator.userAgent")
                        if browser_ua:
                            self.headers['User-Agent'] = browser_ua
                            logger.info(f"已同步浏览器User-Agent: {browser_ua[:30]}...")
                    
                    # 增加验证成功后的等待时间，从3秒增加到10秒
                    logger.info("验证成功，等待10秒确保验证生效...")
                    time.sleep(10)
                    
                    # 额外验证，确保cookies已正确保存
                    test_response = None
                    try:
                        test_response = requests.get(url, headers=self.headers, timeout=10)
                        if self.check_verification(test_response.text, platform, url):
                            logger.warning("验证后仍然需要验证，尝试重新验证或使用不同方法")
                            # 重置cookie并尝试下一次验证
                            self.headers.pop('Cookie', None)
                            time.sleep(2)
                            continue
                        else:
                            logger.info("验证后访问成功，没有再次出现验证页面")
                            return True
                    except Exception as e:
                        logger.error(f"验证后测试访问失败: {e}")
                        # 继续返回真，因为验证过程本身是成功的
                    
                    return True
                else:
                    logger.warning(f"自动验证尝试 {attempt+1} 失败")
                    time.sleep(2)  # 等待一下再尝试
        
        # 如果自动验证失败或未启用，提供更具体的平台验证说明
        platform_name = {
            "anjuke": "安居客",
            "58": "58同城", 
            "beike": "贝壳找房",
            "lianjia": "链家"
        }.get(platform, "该网站")
        
        logger.info(f"检测到{platform_name}需要人机验证，将打开浏览器供您手动验证或选择跳过")
        print(f"\n[!] {platform_name}需要人机验证，请选择操作:")
        print(f"  1. 在浏览器中完成验证后回到控制台继续")
        print(f"  2. 跳过当前页面的验证，继续爬取下一页/下一平台")
        
        # 提供平台特定的验证提示
        if platform == "anjuke":
            print(f"  【安居客验证提示】通常是滑块拼图验证，拖动滑块完成拼图即可")
        elif platform == "58":
            print(f"  【58同城验证提示】可能是点选验证或滑块验证，按页面提示完成")
        elif platform in ["beike", "lianjia"]:
            print(f"  【贝壳/链家验证提示】通常是滑块验证，拖动滑块到指定位置")
        
        choice = input("请输入选项 (1/2): ").strip()
        
        if choice == '2':
            print(f"已选择跳过{platform_name}验证，继续爬取下一页/下一平台...")
            return False
        
        # 打开浏览器
        try:
            import webbrowser
            webbrowser.open(url)
            
            # 等待用户验证
            input(f"\n在浏览器中完成{platform_name}验证后，按回车键继续爬取...")
            print("继续爬取过程...")
            
            # 给一些延迟以确保验证会话有效，手动验证后也增加等待时间
            time.sleep(8)
            
            return True
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")
            print(f"\n[!] 无法自动打开浏览器，请手动访问以下链接并完成{platform_name}验证:")
            print(f"    {url}")
            input("\n按回车键继续爬取 (完成验证后)...")
            time.sleep(8)
            return True
    
    def scrape_anjuke(self, city, house_type, bedroom_num, livingroom_num, build_year, page_count):
        # 实现安居客爬取逻辑
        pass
    
    def scrape_58(self, city, house_type, bedroom_num, livingroom_num, build_year, page_count):
        """爬取58同城房源数据
        
        参数:
            city: 城市代码，如'bj'
            house_type: 房源类型，如'new'(新房),'second'(二手房),'rent'(租房)
            bedroom_num: 卧室数量筛选，None表示不限
            livingroom_num: 客厅数量筛选，None表示不限
            build_year: 建筑年份筛选，None表示不限
            page_count: 爬取页数
            
        返回:
            bool: 是否爬取成功
        """
        print(f"开始爬取58同城-{house_type}，城市: {city}")
        logger.info(f"开始爬取58同城-{house_type}，城市: {city}")
        
        # 检查筛选条件
        filter_conditions = []
        if bedroom_num is not None:
            filter_conditions.append(f"卧室数: {bedroom_num}")
        if livingroom_num is not None:
            filter_conditions.append(f"客厅数: {livingroom_num}")
        if build_year is not None:
            filter_conditions.append(f"建筑年份: {build_year}")
            
        if filter_conditions:
            logger.info(f"筛选条件: {', '.join(filter_conditions)}")
        
        # 当前平台和类型的URL模板
        url_template = URL_TEMPLATES['58同城'][house_type]
        base_url = url_template.format(city=city)
        
        total_items = 0
        
        try:
            # 爬取指定页数
            for page in range(1, page_count + 1):
                if page > 1:
                    # 构建翻页URL
                    if house_type == 'new':
                        # 新房翻页规则
                        page_url = f"{base_url}pn{page}/"
                    elif house_type == 'second':
                        # 二手房翻页规则 
                        page_url = f"{base_url}pn{page}/"
                    else:  # 租房
                        page_url = f"{base_url}pn{page}/"
                else:
                    page_url = base_url
                
                logger.info(f"爬取页面: {page}/{page_count}, URL: {page_url}")
                
                # 发送请求
                headers = self.update_headers()
                try:
                    response = requests.get(page_url, headers=headers, timeout=10)
                except Exception as e:
                    logger.error(f"请求页面失败: {e}")
                    continue
                
                # 检查是否需要验证
                if self.check_verification(response.text, "58", page_url):
                    logger.warning("检测到需要验证")
                    verify_success = self.handle_verification("58", page_url)
                    if not verify_success:
                        logger.warning("验证失败或用户选择跳过，继续下一页")
                        continue
                    
                    # 验证成功后重新请求页面
                    try:
                        headers = self.update_headers()
                        response = requests.get(page_url, headers=headers, timeout=10)
                    except Exception as e:
                        logger.error(f"验证后重新请求页面失败: {e}")
                        continue
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 根据房源类型选择不同的选择器
                if house_type == 'new':
                    # 新房选择器
                    items = soup.select('.list-item')
                    logger.info(f"找到 {len(items)} 个新房项目")
                    
                elif house_type == 'second':
                    # 二手房选择器
                    items = soup.select('.house-cell') or soup.select('.yezhu_item') or soup.select('.house-item')
                    logger.info(f"找到 {len(items)} 个二手房项目")
                    
                else:  # 租房
                    # 租房选择器
                    items = soup.select('.listCon > .listUl > li') or soup.select('.zu-itembox') or soup.select('.house-item')
                    logger.info(f"找到 {len(items)} 个租房项目")
                
                # 处理每个房源项
                for item in items:
                    try:
                        # 提取房源名称
                        name_elem = item.select_one('.title a') or item.select_one('.title') or item.select_one('h3')
                        house_name = name_elem.get_text(strip=True) if name_elem else "未知房源"
                        
                        # 提取价格
                        price_elem = item.select_one('.price') or item.select_one('.money')
                        price = price_elem.get_text(strip=True) if price_elem else "价格未知"
                        
                        # 提取地址/位置
                        address_elem = (
                            item.select_one('.address') or 
                            item.select_one('.add') or 
                            item.select_one('.area') or
                            item.select_one('.district')
                        )
                        address = address_elem.get_text(strip=True) if address_elem else "位置未知"
                        
                        # 提取户型，确保初始化为默认值
                        house_type_elem = (
                            item.select_one('.type') or 
                            item.select_one('.huxing') or
                            item.select_one('.room')
                        )
                        house_type_text = house_type_elem.get_text(strip=True) if house_type_elem else "户型未知"
                        
                        # 提取面积
                        area_elem = item.select_one('.area') or item.select_one('.meter')
                        area = area_elem.get_text(strip=True) if area_elem else "面积未知"
                        
                        # 提取建筑年份 - 确保始终有初始值
                        year = "未知"  
                        
                        info_list = item.select('.baseInfo li') or item.select('.info-tag span')
                        for info in info_list:
                            info_text = info.get_text(strip=True)
                            if '年' in info_text:
                                year_match = re.search(r'(\d{4})年', info_text)
                                if year_match:
                                    year = year_match.group(1)
                                    break
                        
                        # 提取详情页链接
                        link_elem = item.select_one('a[href]') or name_elem
                        detail_url = ""
                        if link_elem and link_elem.has_attr('href'):
                            href = link_elem['href']
                            if href.startswith('//'):
                                detail_url = 'https:' + href
                            elif href.startswith('/'):
                                detail_url = f'https://{city}.58.com{href}'
                            elif not href.startswith('http'):
                                detail_url = f'https://{city}.58.com/{href}'
                            else:
                                detail_url = href
                        
                        # 提取经纬度
                        lat, lng = self.extract_coordinates(item)
                        
                        # 提取户型图
                        layout_image = ""
                        try:
                            layout_image = self.extract_layout_image(item, detail_url)
                        except Exception as e:
                            logger.error(f"提取户型图错误: {str(e)}")
                            layout_image = ""
                        
                        # 筛选条件判断
                        if bedroom_num is not None:
                            bedroom_match = re.search(r'(\d+)室', house_type_text)
                            if bedroom_match:
                                if int(bedroom_match.group(1)) != bedroom_num:
                                    logger.debug(f"跳过房源 - 不符合卧室数量要求: {house_type_text}")
                                    continue
                        
                        if livingroom_num is not None:
                            livingroom_match = re.search(r'(\d+)厅', house_type_text)
                            if livingroom_match:
                                if int(livingroom_match.group(1)) != livingroom_num:
                                    logger.debug(f"跳过房源 - 不符合客厅数量要求: {house_type_text}")
                                    continue
                        
                        # 确保year变量始终被定义
                        if build_year is not None and year != "未知":
                            try:
                                year_int = int(year)
                                if year_int != build_year:
                                    logger.debug(f"跳过房源 - 不符合建筑年份要求: {year} != {build_year}")
                                    continue
                            except ValueError:
                                # 如果年份不是数字，则保留该房源
                                logger.debug(f"年份 '{year}' 不是有效的数字，保留该房源")
                                pass
                        
                        # 构建房源数据项
                        house_item = {
                            '平台': '58同城',
                            '城市': city,
                            '房源名称': house_name,
                            '价格': price,
                            '地址': address,
                            '户型': house_type_text,
                            '面积': area,
                            '建筑年份': year,
                            '类型': '新房' if house_type == 'new' else '二手房' if house_type == 'second' else '租房',
                            '纬度': lat,
                            '经度': lng,
                            '详情页': detail_url,
                            '户型图': layout_image
                        }
                        
                        # 添加到数据集
                        self.house_data.append(house_item)
                        total_items += 1
                        
                    except Exception as e:
                        logger.error(f"处理房源项时出错: {str(e)}")
                        continue
                
                # 随机延迟，避免被封
                delay = self.get_random_delay()
                logger.info(f"页面 {page}/{page_count} 爬取完成，延迟 {delay:.2f} 秒")
                time.sleep(delay)
            
            print(f"58同城爬取完成，共获取 {total_items} 条{house_type}数据")
            logger.info(f"58同城爬取完成，共获取 {total_items} 条{house_type}数据")
            return True
            
        except Exception as e:
            logger.error(f"爬取58同城数据时出错: {e}")
            print(f"爬取58同城数据时出错: {e}")
            return False
    
    def scrape_beike(self, city, house_type, bedroom_num, livingroom_num, build_year, page_count):
        # 实现贝壳找房爬取逻辑
        pass
    
    def scrape_lianjia(self, city, house_type, bedroom_num, livingroom_num, build_year, page_count):
        # 实现链家爬取逻辑
        pass
    
    def save_to_excel(self, filename=None):
        """将爬取的数据保存到Excel文件
        
        参数:
            filename: 文件名，默认为None（使用当前时间生成文件名）
        """
        if not self.house_data:
            print("没有数据可保存")
            return None
        
        # 如果未指定文件名，使用当前时间生成
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.output_dir}/house_data_{timestamp}.xlsx"
        else:
            # 确保文件名包含路径
            if not os.path.dirname(filename):
                filename = f"{self.output_dir}/{filename}"
            # 确保文件名以.xlsx结尾
            if not filename.endswith('.xlsx'):
                filename = f"{filename}.xlsx"
        
        # 创建输出目录
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        try:
            # 转换为DataFrame
            df = pd.DataFrame(self.house_data)
            
            # 确保所有必要的列都存在
            required_columns = ['平台', '城市', '房源名称', '价格', '地址', '户型', '面积', '建筑年份', '类型', '纬度', '经度', '详情页', '户型图']
            for col in required_columns:
                if col not in df.columns:
                    df[col] = ""
            
            # 将列重新排序
            df = df[required_columns]
            
            # 保存到Excel
            writer = pd.ExcelWriter(filename, engine='openpyxl')
            df.to_excel(writer, index=False, sheet_name='房源数据')
            
            # 自动调整列宽
            worksheet = writer.sheets['房源数据']
            for i, column in enumerate(df.columns):
                max_length = max(
                    df[column].astype(str).map(len).max(),
                    len(column)
                ) + 2
                # 限制最大宽度
                max_length = min(max_length, 50)
                worksheet.column_dimensions[get_column_letter(i + 1)].width = max_length
            
            writer.close()
            
            print(f"数据已保存到 {filename}")
            logger.info(f"数据已保存到 {filename}")
            return filename
        
        except Exception as e:
            print(f"保存数据时出错: {e}")
            logger.error(f"保存数据时出错: {e}")
            traceback.print_exc()
            return None
    
    def clear_data(self):
        """清除已爬取的数据"""
        self.house_data = []
        logger.info("已清除爬取的数据")
    
    def cleanup_old_files(self, max_age_days=7):
        """清理过期的调试文件和日志文件
        
        参数:
            max_age_days: 最大保留天数，超过此天数的文件将被删除
        """
        logger.info(f"开始清理超过{max_age_days}天的文件...")
        
        # 需要清理的目录
        dirs_to_clean = [
            'verification_debug'  # 验证截图
        ]
        
        # 需要清理的日志文件
        log_files = [
            'housing_scraper.log',
            'verification.log'
        ]
        
        # 计算截止时间戳
        current_time = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        
        # 清理目录中的旧文件
        for directory in dirs_to_clean:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        file_age = current_time - os.path.getmtime(filepath)
                        if file_age > max_age_seconds:
                            try:
                                os.remove(filepath)
                                logger.info(f"已删除过期文件: {filepath}")
                            except Exception as e:
                                logger.error(f"删除文件 {filepath} 失败: {e}")
        
        # 如果日志文件过大（超过5MB），截断日志文件
        for log_file in log_files:
            if os.path.exists(log_file) and os.path.getsize(log_file) > 5 * 1024 * 1024:  # 5MB
                try:
                    # 读取最后100行保留
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        last_lines = lines[-100:] if len(lines) > 100 else lines
                    
                    # 重写文件，只保留最后100行
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write("".join(last_lines))
                    
                    logger.info(f"日志文件 {log_file} 已截断，保留最后100行")
                except Exception as e:
                    logger.error(f"截断日志文件 {log_file} 失败: {e}")
        
        logger.info("文件清理完成")
    
    def analyze_data(self, save_report=True):
        """对爬取的数据进行简单分析
        
        参数:
            save_report: 是否保存分析报告到Excel
            
        返回:
            分析结果的字典
        """
        if not self.house_data:
            logger.warning("没有数据可供分析")
            return None
        
        logger.info("开始分析房源数据...")
        
        # 将数据转换为DataFrame
        df = pd.DataFrame(self.house_data)
        
        # 统一列名，确保后续分析不会出错
        if '面积' in df.columns and '面积(平方米)' not in df.columns:
            df.rename(columns={'面积': '面积(平方米)'}, inplace=True)
        
        # 可能的价格列名
        price_columns = ['价格', '单价', '总价']
        
        # 提取数值数据（价格、面积等）
        for col in df.columns:
            if any(price_name in col for price_name in price_columns):
                # 从价格文本中提取数字
                df[f'{col}_数值'] = df[col].apply(lambda x: self._extract_number(x) if isinstance(x, str) else x)
            
            if '面积' in col:
                # 从面积文本中提取数字
                df[f'{col}_数值'] = df[col].apply(lambda x: self._extract_number(x) if isinstance(x, str) else x)
        
        # 准备分析结果
        analysis_results = {
            '数据总览': {
                '总房源数': len(df),
                '平台分布': df['平台'].value_counts().to_dict(),
                '房源类型分布': df.get('类型', df.get('房源类型')).value_counts().to_dict()
            },
            '平台分析': {},
            '价格分析': {},
            '户型分析': {},
            '区域分析': {}
        }
        
        # 按平台分组统计
        for platform, group in df.groupby('平台'):
            analysis_results['平台分析'][platform] = {
                '房源数量': len(group),
                '房源类型分布': group.get('类型', group.get('房源类型')).value_counts().to_dict()
            }
            
            # 如果有价格列，计算价格统计信息
            price_numeric_cols = [col for col in group.columns if '价格' in col and '数值' in col]
            for price_col in price_numeric_cols:
                base_col = price_col.replace('_数值', '')
                try:
                    numeric_values = pd.to_numeric(group[price_col], errors='coerce')
                    valid_values = numeric_values.dropna()
                    
                    if not valid_values.empty:
                        analysis_results['平台分析'][platform][f'{base_col}统计'] = {
                            '最低价': valid_values.min(),
                            '最高价': valid_values.max(),
                            '平均价': valid_values.mean(),
                            '中位数': valid_values.median()
                        }
                except Exception as e:
                    logger.warning(f"计算{platform}的{base_col}统计信息时出错: {e}")
        
        # 户型分析
        if '户型' in df.columns:
            room_counts = {}
            for house_type in df['户型'].dropna().unique():
                if isinstance(house_type, str):
                    room_match = re.search(r'(\d+)室', house_type)
                    if room_match:
                        rooms = int(room_match.group(1))
                        room_counts[f'{rooms}室'] = room_counts.get(f'{rooms}室', 0) + 1
            
            analysis_results['户型分析']['室数分布'] = room_counts
        
        # 区域分析
        if '位置' in df.columns:
            # 尝试从位置字段提取区域信息
            regions = {}
            for location in df['位置'].dropna().unique():
                if isinstance(location, str):
                    # 提取常见区域模式，如xx区、xx路等
                    region_match = re.search(r'([^\s,，]+[区路街道])', location)
                    if region_match:
                        region = region_match.group(1)
                        regions[region] = regions.get(region, 0) + df[df['位置'].str.contains(region, na=False)].shape[0]
            
            # 取TOP 10区域
            top_regions = dict(sorted(regions.items(), key=lambda x: x[1], reverse=True)[:10])
            analysis_results['区域分析']['热门区域'] = top_regions
        
        # 价格区间分析
        for price_col in [col for col in df.columns if '价格' in col and '数值' in col]:
            base_col = price_col.replace('_数值', '')
            try:
                numeric_values = pd.to_numeric(df[price_col], errors='coerce')
                valid_values = numeric_values.dropna()
                
                if not valid_values.empty:
                    # 计算价格统计信息
                    analysis_results['价格分析'][base_col] = {
                        '最低价': valid_values.min(),
                        '最高价': valid_values.max(),
                        '平均价': valid_values.mean(),
                        '中位数': valid_values.median(),
                        '标准差': valid_values.std()
                    }
                    
                    # 计算价格区间分布
                    if len(valid_values) > 1:
                        # 按百分比生成5个区间
                        percentiles = [0, 20, 40, 60, 80, 100]
                        bins = [valid_values.quantile(p/100) for p in percentiles]
                        
                        # 确保bins是单调递增的
                        bins = sorted(set(bins))
                        
                        # 统计每个区间的房源数量
                        hist, bin_edges = np.histogram(valid_values, bins=bins)
                        
                        # 生成区间标签
                        bin_labels = [f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}" for i in range(len(bin_edges)-1)]
                        
                        # 将结果保存到分析结果
                        analysis_results['价格分析'][f'{base_col}区间分布'] = dict(zip(bin_labels, hist.tolist()))
            except Exception as e:
                logger.warning(f"计算{base_col}分析时出错: {e}")
        
        # 生成分析报告
        if save_report and analysis_results:
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                report_file = f"{self.data_dir}/房源数据分析报告_{timestamp}.xlsx"
                
                with pd.ExcelWriter(report_file) as writer:
                    # 总览
                    overview_data = pd.DataFrame([analysis_results['数据总览']])
                    overview_data.to_excel(writer, sheet_name='数据总览', index=False)
                    
                    # 平台分析
                    platform_data = []
                    for platform, stats in analysis_results['平台分析'].items():
                        row = {'平台': platform, '房源数量': stats['房源数量']}
                        
                        # 添加价格信息
                        for key, value in stats.items():
                            if '价格' in key and isinstance(value, dict):
                                for stat, stat_value in value.items():
                                    row[f"{key}_{stat}"] = stat_value
                        
                        platform_data.append(row)
                    
                    if platform_data:
                        pd.DataFrame(platform_data).to_excel(writer, sheet_name='平台分析', index=False)
                    
                    # 价格分析
                    price_data = []
                    for price_type, stats in analysis_results['价格分析'].items():
                        if '区间分布' not in price_type:
                            row = {'价格类型': price_type}
                            row.update(stats)
                            price_data.append(row)
                    
                    if price_data:
                        pd.DataFrame(price_data).to_excel(writer, sheet_name='价格分析', index=False)
                    
                    # 户型分析
                    if '室数分布' in analysis_results['户型分析']:
                        room_data = [{'户型': k, '数量': v} for k, v in analysis_results['户型分析']['室数分布'].items()]
                        if room_data:
                            pd.DataFrame(room_data).to_excel(writer, sheet_name='户型分析', index=False)
                    
                    # 区域分析
                    if '热门区域' in analysis_results['区域分析']:
                        region_data = [{'区域': k, '房源数量': v} for k, v in analysis_results['区域分析']['热门区域'].items()]
                        if region_data:
                            pd.DataFrame(region_data).to_excel(writer, sheet_name='区域分析', index=False)
                    
                    # 原始数据
                    df.to_excel(writer, sheet_name='原始数据', index=False)
                
                logger.info(f"分析报告已保存到: {report_file}")
                print(f"分析报告已保存到: {report_file}")
            
            except Exception as e:
                logger.error(f"保存分析报告时出错: {e}")
        
        return analysis_results
    
    def _extract_number(self, text):
        """从文本中提取数字
        
        参数:
            text: 源文本
            
        返回:
            float 或 None: 提取的数字，无法提取则返回None
        """
        if not text or not isinstance(text, str):
            return None
            
        try:
            # 匹配浮点数或整数
            match = re.search(r'(\d+\.?\d*)', text)
            if match:
                return float(match.group(1))
        except:
            pass
            
        return None
        
    def extract_coordinates(self, item):
        """提取房源的经纬度坐标
        
        参数:
            item: BeautifulSoup对象，表示房源项
            
        返回:
            tuple: (latitude, longitude) 纬度和经度，无法提取则为None
        """
        if item is None:
            return None, None
            
        try:
            # 检查item类型
            if not hasattr(item, 'prettify'):
                return None, None
                
            # 转换为字符串形式用于正则匹配
            item_str = item.prettify()
            
            # 常见经纬度表示形式
            patterns = [
                # 标准格式: lat:xx.xx, lng:yy.yy
                r'lat[itude]*["\s\'=:]+(-?\d+\.\d+)["\s\']*[,;\s]+lon[gitude]*["\s\'=:]+(-?\d+\.\d+)',
                
                # 百度地图格式: BMap.Point(xx.xx, yy.yy)
                r'BMap\.Point\((-?\d+\.\d+),\s*(-?\d+\.\d+)\)',
                
                # 坐标数组格式: [xx.xx, yy.yy]
                r'coordinate["\'=:\s]+\[(-?\d+\.\d+),\s*(-?\d+\.\d+)\]',
                
                # 位置数据格式: position:[xx.xx, yy.yy]
                r'position["\s\'=:\[{]+(-?\d+\.\d+)["\s\']*[,;\s]+(-?\d+\.\d+)',
                
                # resblock格式
                r'resblockPosition["\s\'=:\[{]+(-?\d+\.\d+)["\s\']*[,;\s]+(-?\d+\.\d+)',
                
                # 百度特定格式
                r'baidulat["\s\'=:]+(-?\d+\.\d+)["\s\']*[,;\s]+baidulon["\s\'=:]+(-?\d+\.\d+)',
                
                # 坐标对象格式: {lat: xx.xx, lng: yy.yy}
                r'[\{\s]lat\s*:\s*(-?\d+\.\d+)[,\s]+lng\s*:\s*(-?\d+\.\d+)',
                
                # 点坐标格式: point="xx.xx,yy.yy"
                r'point\s*=\s*["\'"](-?\d+\.\d+),(-?\d+\.\d+)',
                
                # 通用坐标对格式
                r'["\']coordinates["\']\s*:\s*\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\]'
            ]
            
            # 遍历所有模式尝试匹配
            for pattern in patterns:
                match = re.search(pattern, item_str)
                if match:
                    return match.group(1), match.group(2)
            
            # 查找特定属性
            for lat_attr, lng_attr in [
                    ('data-lat', 'data-lng'), 
                    ('data-latitude', 'data-longitude'),
                    ('lat', 'lng'),
                    ('latitude', 'longitude')
                ]:
                lat_elem = item.select_one(f'[{lat_attr}]')
                lng_elem = item.select_one(f'[{lng_attr}]')
                if lat_elem and lng_elem:
                    return lat_elem.get(lat_attr), lng_elem.get(lng_attr)
            
            # 查找data-position属性
            position_elem = item.select_one('[data-position]')
            if position_elem:
                position = position_elem.get('data-position')
                match = re.search(r'(-?\d+\.\d+)[,;](\d+\.\d+)', position)
                if match:
                    return match.group(1), match.group(2)
                    
            # 查找附近元素中是否包含坐标信息
            nearby_script = item.find_next('script')
            if nearby_script and nearby_script.string:
                for pattern in patterns:
                    match = re.search(pattern, nearby_script.string)
                    if match:
                        return match.group(1), match.group(2)
            
        except Exception as e:
            logger.debug(f"提取经纬度信息失败: {e}")
            
        return None, None
    
    def _ensure_detail_url_in_data(self):
        """
        确保所有58同城的数据都包含详情页链接字段
        """
        for item in self.house_data:
            if item['平台'] == '58同城' and '详情页' not in item:
                item['详情页'] = ""  # 添加空的详情页字段
                
        return True
    
    def extract_layout_image(self, item, detail_url=None):
        """提取房源的户型图链接
        
        参数:
            item: BeautifulSoup对象，表示房源项
            detail_url: 详情页URL，如果提供则尝试访问详情页获取户型图
            
        返回:
            str: 户型图链接，无法提取则为空字符串
        """
        if item is None:
            return ""
            
        try:
            # 检查item类型
            if not hasattr(item, 'prettify'):
                return ""
                
            # 尝试在当前页面中查找户型图
            layout_img = None
            
            # 常见的户型图class和id
            layout_selectors = [
                "img[alt*='户型']", "img[alt*='平面']", "img[src*='hu_xing']", "img[src*='huxing']",
                "img[src*='layout']", "img[src*='hu-xing']", ".house-layout img", ".layout-img",
                ".hx-img", ".house-type-img", ".hu-xing", ".huxingtu", ".hu_xing", ".layout-item img"
            ]
            
            # 在当前页面查找
            for selector in layout_selectors:
                layout_imgs = item.select(selector)
                if layout_imgs:
                    layout_img = layout_imgs[0]
                    break
            
            # 如果找到了户型图，返回src属性
            if layout_img and layout_img.has_attr('src'):
                src = layout_img['src']
                # 确保链接是完整的
                if src.startswith('//'):
                    return 'https:' + src
                elif not src.startswith('http'):
                    return 'https://' + src
                return src
                
            # 如果提供了详情页URL，尝试访问详情页获取户型图
            if detail_url and detail_url.strip():
                try:
                    # 访问详情页
                    headers = self.update_headers()
                    response = requests.get(detail_url, headers=headers, timeout=10)
                    
                    # 检查详情页是否需要验证
                    if self.check_verification(response.text):
                        logger.warning(f"获取户型图时详情页需要验证，跳过: {detail_url}")
                        return ""
                    
                    if response.status_code == 200:
                        detail_soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 在详情页查找户型图
                        for selector in layout_selectors:
                            layout_imgs = detail_soup.select(selector)
                            if layout_imgs:
                                layout_img = layout_imgs[0]
                                if layout_img.has_attr('src'):
                                    src = layout_img['src']
                                    # 确保链接是完整的
                                    if src.startswith('//'):
                                        return 'https:' + src
                                    elif not src.startswith('http'):
                                        return 'https://' + src
                                    return src
                except Exception as e:
                    logger.warning(f"访问详情页获取户型图失败: {e}, URL: {detail_url}")
            
        except Exception as e:
            logger.debug(f"提取户型图失败: {e}")
            
        return ""


def main():
    """主函数"""
    print("=" * 50)
    print("多平台房价数据爬虫程序")
    print("=" * 50)
    
    scraper = MultiPlatformHousingScraper()
    
    # 清理过期文件
    scraper.cleanup_old_files()
    
    while True:
        print("\n主菜单:")
        print("1. 爬取房源数据")
        print("2. 分析已有数据")
        print("3. 清空已有数据")
        print("4. 退出程序")
        
        main_choice = input("请输入选项 (1-4): ").strip()
        
        if main_choice == '4':
            print("程序已退出")
            break
        
        elif main_choice == '3':
            confirm = input("确认要清空所有已爬取的数据吗? (y/n): ").strip().lower()
            if confirm == 'y':
                scraper.clear_data()
                print("数据已清空")
            continue
        
        elif main_choice == '2':
            if not scraper.house_data:
                print("没有可分析的数据，请先爬取数据")
                continue
            
            print(f"\n当前数据包含 {len(scraper.house_data)} 条房源记录")
            confirm = input("确认要分析当前数据吗? (y/n): ").strip().lower()
            if confirm == 'y':
                analysis_results = scraper.analyze_data(save_report=True)
                if analysis_results:
                    print("\n数据分析完成，详细结果请查看生成的报告文件")
            continue
        
        elif main_choice != '1':
            print("无效选择，请重新输入")
            continue
        
        # 爬取数据的选项
        print("\n请选择要爬取的平台:")
        print("1. 安居客")
        print("2. 58同城")
        print("3. 贝壳找房")
        print("4. 链家")
        print("5. 所有平台")
        print("0. 返回主菜单")
        
        platform_choice = input("请输入选项 (0-5): ").strip()
        
        if platform_choice == '0':
            continue
        
        if platform_choice not in ['1', '2', '3', '4', '5']:
            print("无效选择，请重新输入")
            continue
        
        # 获取城市信息
        print("\n常见城市代码：郑州=zz, 北京=bj, 上海=sh, 广州=gz, 深圳=sz, 成都=cd, 杭州=hz, 武汉=wh, 西安=xa")
        city_input = input("请输入城市名称或城市代码 (例如: 郑州 或 zz): ").strip()
        
        # 尝试将中文城市名转换为城市代码
        if city_input in CITY_CODES:
            city = CITY_CODES[city_input]
            print(f"已自动将城市名 '{city_input}' 转换为城市代码 '{city}'")
        else:
            city = city_input.lower()  # 如果不是中文城市名，则可能是城市代码，直接使用
        
        if not city:
            print("城市代码不能为空")
            continue
        
        # 获取房源类型（允许多选）
        print("\n请选择房源类型(可多选):")
        print("1. 新房")
        print("2. 二手房")
        print("3. 租房")
        house_type_choices = input("请输入选项，多选请用逗号分隔 (例如: 1,2,3): ").strip()
        
        # 解析用户的房源类型选择
        house_type_list = []
        for choice in house_type_choices.split(','):
            choice = choice.strip()
            if choice in ['1', '2', '3']:
                house_type_list.append(scraper.house_types[choice])
            else:
                print(f"无效选择 '{choice}'，已忽略")
        
        if not house_type_list:
            print("未选择有效的房源类型，请重新输入")
            continue
        
        print(f"已选择房源类型: {', '.join(house_type_list)}")
        
        # 获取筛选条件
        bedroom_num = None
        livingroom_num = None
        build_year = None
        
        filter_option = input("是否按户型筛选? (y/n): ").strip().lower()
        if filter_option == 'y':
            try:
                bedroom_input = input("请输入卧室数量 (直接回车表示不限): ").strip()
                if bedroom_input:
                    bedroom_num = int(bedroom_input)
                
                livingroom_input = input("请输入客厅数量 (直接回车表示不限): ").strip()
                if livingroom_input:
                    livingroom_num = int(livingroom_input)
            except ValueError:
                print("输入格式错误，请输入数字")
                continue
        
        # 获取年份筛选
        year_option = input("是否按建筑年份筛选? (y/n): ").strip().lower()
        if year_option == 'y':
            try:
                year_input = input("请输入建筑年份 (例如: 2015): ").strip()
                if year_input:
                    build_year = int(year_input)
            except ValueError:
                print("输入格式错误，请输入数字")
                continue
        
        # 获取爬取页数
        page_count = 3  # 默认页数
        try:
            page_input = input(f"请输入每个平台爬取的页数 (直接回车默认为{page_count}页): ").strip()
            if page_input:
                page_count = int(page_input)
        except ValueError:
            print(f"输入格式错误，使用默认页数 {page_count}")
        
        # 是否清空之前的数据
        clear_option = input("是否清空之前爬取的数据? (y/n, 默认n): ").strip().lower()
        if clear_option == 'y':
            scraper.clear_data()
        
        # 根据选择爬取数据
        try:
            # 为每一个选定的平台爬取所有选定的房源类型
            if platform_choice == '5':  # 所有平台
                for platform_id, platform_info in scraper.platforms.items():
                    for house_type in house_type_list:
                        print(f"\n正在爬取 {platform_info['name']} 的 {house_type} 数据...")
                        try:
                            platform_info['scraper'](city, house_type, bedroom_num, livingroom_num, build_year, page_count)
                        except Exception as e:
                            print(f"爬取 {platform_info['name']} 的 {house_type} 数据时出错: {e}")
                            skip_option = input(f"是否跳过 {platform_info['name']} 的 {house_type} 数据继续爬取? (y/n): ").strip().lower()
                            if skip_option != 'y':
                                raise  # 如果用户不想跳过，则将异常再次抛出
            else:
                platform_info = scraper.platforms[platform_choice]
                for house_type in house_type_list:
                    print(f"\n正在爬取 {platform_info['name']} 的 {house_type} 数据...")
                    try:
                        platform_info['scraper'](city, house_type, bedroom_num, livingroom_num, build_year, page_count)
                    except Exception as e:
                        print(f"爬取 {platform_info['name']} 的 {house_type} 数据时出错: {e}")
                        skip_option = input(f"是否跳过 {platform_info['name']} 的 {house_type} 数据继续爬取? (y/n): ").strip().lower()
                        if skip_option != 'y':
                            raise  # 如果用户不想跳过，则将异常再次抛出
            
            # 保存数据
            if scraper.house_data:
                save_option = input("\n是否保存数据到Excel? (y/n): ").strip().lower()
                if save_option == 'y':
                    filename = scraper.save_to_excel()
                    print(f"数据已保存到: {filename}")
                
                # 询问是否分析数据
                analyze_option = input("\n是否分析爬取的数据? (y/n): ").strip().lower()
                if analyze_option == 'y':
                    analysis_results = scraper.analyze_data(save_report=True)
                    if analysis_results:
                        print("\n数据分析完成，详细结果请查看生成的报告文件")
            
            # 询问是否继续
            continue_option = input("\n是否返回主菜单? (y/n): ").strip().lower()
            if continue_option != 'y':
                print("程序已退出")
                break
        
        except Exception as e:
            print(f"程序执行过程中出错: {e}")
            retry_option = input("是否跳过错误继续执行程序? (y/n): ").strip().lower()
            if retry_option != 'y':
                break  # 如果用户不想继续，则退出循环
    
    # 最后确认是否保存数据
    if scraper.house_data:
        save_option = input("\n程序退出前，是否将所有数据保存到Excel? (y/n): ").strip().lower()
        if save_option == 'y':
            scraper.save_to_excel()

    # 如果使用了自动验证处理器，确保关闭浏览器
    if scraper.auto_verification_handler:
        scraper.auto_verification_handler.close_browser()


def parse_args():
    """解析命令行参数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='多平台房价数据爬虫程序')
    
    # 通用参数
    parser.add_argument('--debug', action='store_true', help='开启调试模式')
    parser.add_argument('--output', type=str, help='输出文件名')
    parser.add_argument('--clear', action='store_true', help='清空之前爬取的数据')
    
    # 爬取参数
    parser.add_argument('--platform', type=str, choices=['anjuke', '58', 'beike', 'lianjia', 'all'], 
                        help='要爬取的平台(anjuke=安居客, 58=58同城, beike=贝壳找房, lianjia=链家, all=所有平台)')
    parser.add_argument('--city', type=str, help='城市名称或城市代码，例如: 郑州 或 zz')
    parser.add_argument('--type', type=str, help='房源类型，多个类型用逗号分隔 (新房,二手房,租房)')
    parser.add_argument('--pages', type=int, default=3, help='每个平台爬取的页数，默认为3')
    
    # 筛选参数
    parser.add_argument('--bedroom', type=int, help='卧室数量筛选')
    parser.add_argument('--livingroom', type=int, help='客厅数量筛选')
    parser.add_argument('--year', type=int, help='建筑年份筛选')
    
    # 自动化参数
    parser.add_argument('--headless', action='store_true', help='使用无头浏览器模式进行自动验证')
    parser.add_argument('--no-verify', action='store_true', help='禁用自动验证，遇到验证码时直接跳过')
    
    # 数据分析参数
    parser.add_argument('--analyze', action='store_true', help='爬取后自动进行数据分析')
    parser.add_argument('--analyze-only', action='store_true', help='只分析已有数据，不进行爬取')
    
    args = parser.parse_args()
    return args


def run_with_args(args):
    """使用命令行参数运行爬虫"""
    # 设置调试级别
    set_debug_level(args.debug)
    
    scraper = MultiPlatformHousingScraper()
    
    # 清理过期文件
    scraper.cleanup_old_files()
    
    # 如果指定了清空数据
    if args.clear:
        scraper.clear_data()
    
    # 如果只需要分析数据
    if args.analyze_only:
        if not scraper.house_data:
            logger.warning("没有数据可供分析，请先爬取数据或加载已有数据")
            return
        
        logger.info("只分析已有数据，不进行爬取")
        analysis_results = scraper.analyze_data(save_report=True)
        if analysis_results:
            logger.info("数据分析完成")
        return
    
    # 如果没有指定平台和城市，使用交互模式
    if not (args.platform and args.city and args.type):
        logger.info("未指定完整的爬取参数，启动交互模式")
        main()
        return
    
    # 设置平台
    platform_map = {
        'anjuke': '1', 
        '58': '2', 
        'beike': '3', 
        'lianjia': '4', 
        'all': '5'
    }
    platform_choice = platform_map.get(args.platform)
    if not platform_choice:
        logger.error(f"无效的平台选择: {args.platform}")
        return
    
    # 设置城市
    city = args.city.lower()
    if args.city in CITY_CODES:
        city = CITY_CODES[args.city]
        logger.info(f"已自动将城市名 '{args.city}' 转换为城市代码 '{city}'")
    
    # 设置房源类型
    type_map = {
        '新房': '1',
        '二手房': '2',
        '租房': '3'
    }
    
    house_type_list = []
    for house_type in args.type.split(','):
        house_type = house_type.strip()
        if house_type in type_map:
            choice = type_map[house_type]
            house_type_list.append(scraper.house_types[choice])
        else:
            logger.warning(f"无效的房源类型选择: {house_type}，已忽略")
    
    if not house_type_list:
        logger.error("未选择有效的房源类型")
        return
    
    logger.info(f"爬取平台: {args.platform}")
    logger.info(f"爬取城市: {city}")
    logger.info(f"爬取房源类型: {', '.join(house_type_list)}")
    logger.info(f"爬取页数: {args.pages}")
    
    if args.bedroom:
        logger.info(f"卧室数量筛选: {args.bedroom}")
    if args.livingroom:
        logger.info(f"客厅数量筛选: {args.livingroom}")
    if args.year:
        logger.info(f"建筑年份筛选: {args.year}")
    
    # 开始爬取数据
    try:
        # 为每一个选定的平台爬取所有选定的房源类型
        if platform_choice == '5':  # 所有平台
            for platform_id, platform_info in scraper.platforms.items():
                for house_type in house_type_list:
                    logger.info(f"正在爬取 {platform_info['name']} 的 {house_type} 数据...")
                    try:
                        platform_info['scraper'](city, house_type, args.bedroom, args.livingroom, args.year, args.pages)
                    except Exception as e:
                        logger.error(f"爬取 {platform_info['name']} 的 {house_type} 数据时出错: {e}")
                        if not args.no_verify:
                            break
        else:
            platform_info = scraper.platforms[platform_choice]
            for house_type in house_type_list:
                logger.info(f"正在爬取 {platform_info['name']} 的 {house_type} 数据...")
                try:
                    platform_info['scraper'](city, house_type, args.bedroom, args.livingroom, args.year, args.pages)
                except Exception as e:
                    logger.error(f"爬取 {platform_info['name']} 的 {house_type} 数据时出错: {e}")
                    if not args.no_verify:
                        break
        
        # 保存数据
        if scraper.house_data:
            filename = args.output if args.output else None
            scraper.save_to_excel(filename)
            logger.info("数据爬取完成并已保存")
            
            # 如果指定了分析数据
            if args.analyze:
                logger.info("开始分析爬取的数据...")
                analysis_results = scraper.analyze_data(save_report=True)
                if analysis_results:
                    logger.info("数据分析完成")
        else:
            logger.warning("未爬取到任何数据")
    
    except Exception as e:
        logger.error(f"程序执行过程中出错: {e}")
    
    finally:
        # 如果使用了自动验证处理器，确保关闭浏览器
        if scraper.auto_verification_handler:
            scraper.auto_verification_handler.close_browser()


if __name__ == "__main__":
    import sys
    
    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        # 命令行模式
        args = parse_args()
        run_with_args(args)
    else:
        # 交互模式
        main() 