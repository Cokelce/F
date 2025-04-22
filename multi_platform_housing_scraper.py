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
        '新房': 'https://{city}.58.com/loupan/p{page}/',
        '二手房': 'https://{city}.58.com/ershoufang/p{page}/',
        '租房': 'https://{city}.58.com/zufang/p{page}/'
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
        
        # 创建调试目录
        self.debug_dir = 'debug_pages'
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
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
    
    def check_verification(self, response_text):
        """检查页面是否需要验证
        
        参数:
            response_text: 页面响应文本
            
        返回:
            bool: 是否需要验证
        """
        # 基本验证词汇
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
    
    def handle_verification(self, url):
        """处理需要验证的情况，打开浏览器让用户验证或尝试自动验证"""
        max_attempts = 3
        
        # 如果启用了自动验证，尝试自动处理
        if self.auto_verification_handler:
            for attempt in range(max_attempts):
                logger.info(f"检测到网站需要人机验证，尝试自动验证 (尝试 {attempt+1}/{max_attempts})...")
                
                verification_success = self.auto_verification_handler.handle_verification(url)
                
                if verification_success:
                    logger.info("自动验证成功")
                    
                    # 使用验证成功后的cookies更新请求头
                    cookies_dict = self.auto_verification_handler.get_cookies_dict()
                    if cookies_dict:
                        cookies_str = '; '.join([f"{k}={v}" for k, v in cookies_dict.items()])
                        self.headers.update({'Cookie': cookies_str})
                        logger.info(f"已更新Cookie: {cookies_str[:50]}...")
                    
                    # 给验证一些生效的时间
                    time.sleep(3)
                    return True
                else:
                    logger.warning(f"自动验证尝试 {attempt+1} 失败")
                    time.sleep(2)  # 等待一下再尝试
        
        # 如果自动验证失败或未启用，回退到手动验证或跳过
        logger.info(f"检测到网站需要人机验证，将打开浏览器供您手动验证或选择跳过")
        print(f"\n[!] 请选择操作:")
        print(f"  1. 在浏览器中完成验证后回到控制台继续")
        print(f"  2. 跳过当前页面的验证，继续爬取下一页/下一平台")
        choice = input("请输入选项 (1/2): ").strip()
        
        if choice == '2':
            print("已选择跳过验证，继续爬取下一页/下一平台...")
            return False
        
        # 打开浏览器
        try:
            webbrowser.open(url)
            
            # 等待用户验证
            input("\n按回车键继续爬取 (完成验证后)...")
            print("继续爬取过程...")
            
            # 给一些延迟以确保验证会话有效
            time.sleep(3)
            
            return True
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}")
            print("\n[!] 无法自动打开浏览器，请手动访问以下链接并完成验证:")
            print(f"    {url}")
            input("\n按回车键继续爬取 (完成验证后)...")
            time.sleep(3)
            return True
    
    def detect_house_item_selector(self, soup, site='anjuke', house_type='新房'):
        """
        自动检测房源列表项的选择器
        
        参数:
            soup: BeautifulSoup对象
            site: 网站名称
            house_type: 房源类型
            
        返回:
            选择器字符串
        """
        # 安居客新房可能的选择器
        anjuke_new_house_selectors = [
            '.item-mod', '.key-list .item', '.anjuke-result-box .anjuke-result-item',
            '.property-item', '.loupan-item', '.building-item', '.house-item', 
            '.card', '.result-item', '[id*="loupan"] .item', '.new-house-item',
            '.items-list .item', '.list-content > div', '.list > li', '.item', 
            '[data-list-index]', '.list-cell', '.list-item'
        ]
        
        # 安居客二手房可能的选择器
        anjuke_used_house_selectors = [
            '.list-item', '.houselist-item', '.house-cell', '.houseCard', 
            '.house-item', '.property-item', '.sale-item', '.list-content > div',
            '.list > li', '.house-details', '[data-list-index]', 'div[data-component="item"]',
            '.list-cell', '.items-list .item', '.item'
        ]
        
        # 58同城新房可能的选择器
        tc58_new_house_selectors = [
            '.key-list .item', '.house-list-item', '.build-list-item',
            '.list > li', '.loupan-list > li', '.newhouse-item', '.list-cell', 
            '.list-item', '[class*="list"] > [class*="item"]'
        ]
        
        # 58同城二手房可能的选择器
        tc58_used_house_selectors = [
            '.house-cell', '.house-cell-list > li', '.house-item', 
            '.ershou-item', '.list > li', '.house-list-item', '.list-cell',
            '.property-item', '.item'
        ]
        
        # 贝壳找房新房可能的选择器
        beike_new_house_selectors = [
            '.resblock-list-wrapper > li', '.resblock-list-container .resblock-list',
            '.resblock-item', '.loupan-item', '.new-house-item', '.house-item',
            '.key-list > .item', '.item'
        ]
        
        # 贝壳找房二手房可能的选择器
        beike_used_house_selectors = [
            '.sellListContent > li', '.VIEWLIST', '.house-item',
            '.item-card', '.ershoufang-item', '.house-cell', '.key-list > .item',
            '.item'
        ]
        
        # 链家新房可能的选择器
        lianjia_new_house_selectors = [
            '.resblock-list-container .resblock-list', '.resblock-list-module',
            '.newhouse-list .house-item', '.house-cell', '.loupan-item',
            '.key-list > .item', '.item'
        ]
        
        # 链家二手房可能的选择器
        lianjia_used_house_selectors = [
            '.sellListContent > li', '.main-house-list .item', '.house-item',
            '.list-item', '.ershoufang-item', '.key-list > .item', '.item'
        ]
        
        # 根据网站和房源类型选择可能的选择器列表
        selectors = []
        if site == 'anjuke':
            if house_type == '新房':
                selectors = anjuke_new_house_selectors
            else:
                selectors = anjuke_used_house_selectors
        elif site == '58':
            if house_type == '新房':
                selectors = tc58_new_house_selectors
            else:
                selectors = tc58_used_house_selectors
        elif site == 'beike':
            if house_type == '新房':
                selectors = beike_new_house_selectors
            else:
                selectors = beike_used_house_selectors
        elif site == 'lianjia':
            if house_type == '新房':
                selectors = lianjia_new_house_selectors
            else:
                selectors = lianjia_used_house_selectors
        
        # 测试每个选择器，返回匹配项数量最多的选择器
        max_items = 0
        best_selector = None
        
        for selector in selectors:
            items = soup.select(selector)
            if len(items) > max_items:
                max_items = len(items)
                best_selector = selector
                
                # 如果找到的项目数量超过5个，认为这是有效的选择器
                if max_items >= 5:
                    logger.info(f"使用选择器 '{selector}' 找到 {max_items} 个房源项")
                    return selector
        
        # 如果没有找到满意的选择器，返回匹配项最多的那个
        if best_selector and max_items > 0:
            logger.info(f"使用选择器 '{best_selector}' 找到 {max_items} 个房源项")
            return best_selector
        
        # 尝试更通用的选择器，如果上面的都没有找到结果
        general_selectors = [
            '.list-content > div', '.list > li', '.items-list > div', 
            '[class*="list"] > [class*="item"]', 'div[data-index]', 'div[data-list-index]', 
            'div[data-id]', '.content > div', '.content > li'
        ]
        
        for selector in general_selectors:
            items = soup.select(selector)
            if len(items) > max_items:
                max_items = len(items)
                best_selector = selector
                
                if max_items >= 3:  # 降低标准，只要找到3个以上即可
                    logger.info(f"使用通用选择器 '{selector}' 找到 {max_items} 个房源项")
                    return selector
        
        # 如果general_selectors中有找到结果但不多于3个，也返回最好的那个
        if best_selector and max_items > 0:
            logger.info(f"使用通用选择器 '{best_selector}' 找到 {max_items} 个房源项")
            return best_selector
            
        # 如果实在找不到任何有效选择器，返回最通用的选择器
        logger.warning("无法找到合适的选择器，使用最通用选择器")
        return 'div, li, .item, .cell'
        
    def save_debug_page(self, response_text, site, house_type, page):
        """保存页面用于调试"""
        debug_file = os.path.join(self.debug_dir, f"{site}_{house_type}_p{page}.html")
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response_text)
            logger.info(f"已保存调试页面: {debug_file}")
        except Exception as e:
            logger.error(f"保存调试页面失败: {e}")
    
    def scrape_anjuke(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, page_count=3):
        """
        爬取安居客房源数据
        
        参数:
            city: 城市名称
            house_type: 房源类型 (新房/二手房/租房)
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            build_year: 建筑年份
            page_count: 爬取页数
        """
        logger.info(f"开始爬取安居客{city}{house_type}数据")
        if bedroom_num or livingroom_num:
            logger.info(f"筛选条件: {bedroom_num}室{livingroom_num}厅")
        if build_year:
            logger.info(f"建筑年份: {build_year}年")
            
        # 构建URL - 使用城市代码
        city_code = CITY_CODES.get(city, city)  # 获取城市代码，如果没有则使用原始输入
        
        # 获取URL模板
        url_template = URL_TEMPLATES['安居客'][house_type]
        
        total_items = 0
        verification_handled = False
        max_retries = 3  # 每页最大重试次数
        
        for page in range(1, page_count + 1):
            url = url_template.format(city=city_code, page=page)
            headers = self.update_headers()
            
            retry_count = 0
            while retry_count < max_retries:
                try:
                    logger.info(f"正在爬取第{page}页: {url}")
                    response = requests.get(url, headers=headers, timeout=10)
                    
                    # 检查是否需要验证
                    if self.check_verification(response.text):
                        logger.warning("检测到安居客需要人机验证")
                        
                        if not verification_handled:
                            verification_handled = self.handle_verification(url)
                            # 如果用户选择跳过验证，继续下一页
                            if not verification_handled:
                                logger.warning("用户选择跳过验证，继续下一页")
                                break
                            # 重新请求当前页
                            response = requests.get(url, headers=headers, timeout=10)
                        else:
                            logger.warning("仍然需要验证，可能验证未成功")
                            # 保存页面用于分析
                            self.save_debug_page(response.text, "anjuke", house_type, page)
                            retry_count += 1
                            time.sleep(self.get_random_delay() * 2)  # 增加等待时间
                            continue
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 检查页面是否有内容
                        if len(soup.text) < 1000:  # 页面内容过少，可能是反爬页面
                            logger.warning(f"页面内容过少，可能是反爬页面")
                            
                            if not verification_handled:
                                verification_handled = self.handle_verification(url)
                                # 重新请求当前页
                                response = requests.get(url, headers=headers, timeout=10)
                                soup = BeautifulSoup(response.text, 'html.parser')
                            else:
                                logger.warning("仍然无法获取完整页面，重试")
                                self.save_debug_page(response.text, "anjuke", house_type, page)
                                retry_count += 1
                                time.sleep(self.get_random_delay() * 2)
                                continue
                        
                        # 自动检测房源项选择器
                        item_selector = self.detect_house_item_selector(soup, 'anjuke', house_type)
                        
                        house_items = soup.select(item_selector)
                        
                        if not house_items:
                            logger.warning(f"未找到房源数据，尝试其他选择器")
                            self.save_debug_page(response.text, "anjuke", house_type, page)
                            retry_count += 1
                            continue
                        
                        logger.info(f"成功找到 {len(house_items)} 个房源项")
                                
                        for item in house_items:
                            try:
                                # 获取房源名称 - 使用多个选择器
                                name = None
                                for name_selector in ['.items-name', '.loupan-name', '.title', 'h3', '.name', '.building-name', '[class*="name"]', 'a', '.info', '.info-title', '.house-title']:
                                    name_elem = item.select_one(name_selector)
                                    if name_elem:
                                        name = name_elem.text.strip()
                                        break
                                
                                # 如果仍未找到名称，尝试从链接文本中提取
                                if name is None:
                                    links = item.select('a')
                                    for link in links:
                                        if link.text and len(link.text.strip()) > 5:  # 长度超过5的可能是标题
                                            name = link.text.strip()
                                            break
                                
                                if name is None:
                                    name = "未知"
                                
                                # 获取房源价格 - 使用多个选择器
                                price_text = "未知"
                                for price_selector in ['.price', '.money', '.total-price', '.average', '.unit-price', '[class*="price"]', '.value', '.price-det', '.num']:
                                    price_elem = item.select_one(price_selector)
                                    if price_elem:
                                        price_text = price_elem.text.strip()
                                        break
                                
                                # 确保价格中只包含数字和单位
                                if price_text != "未知":
                                    # 清理常见价格文本格式
                                    price_text = re.sub(r'\s+', '', price_text)  # 移除空白字符
                                    
                                    # 尝试使用正则提取数字部分和单位
                                    price_match = re.search(r'([\d\.]+)([万元/平元/㎡]*)', price_text)
                                    if price_match:
                                        price_value = price_match.group(1)
                                        price_unit = price_match.group(2) if price_match.group(2) else "元/平"
                                        price_text = f"{price_value}{price_unit}"
                                
                                # 获取房源位置 - 使用多个选择器
                                location = "未知"
                                for loc_selector in ['.address', '.loc', '.location', '.position', '[class*="address"]', '[class*="location"]', '.address-text', '.region', '.area-text']:
                                    loc_elem = item.select_one(loc_selector)
                                    if loc_elem:
                                        location = loc_elem.text.strip()
                                        break
                                
                                # 如果位置信息为空但有区域信息，使用区域信息
                                if location == "未知":
                                    for region_selector in ['.region', '.area', '.district', '[class*="region"]', '[class*="district"]']:
                                        region_elem = item.select_one(region_selector)
                                        if region_elem:
                                            location = region_elem.text.strip()
                                            break
                                
                                # 如果还是未知，从整个元素文本中尝试提取位置信息
                                if location == "未知":
                                    # 常见城市区域名称模式
                                    location_pattern = r'([东西南北中]部|[东西南北]\d+|[a-zA-Z0-9]+区|.{2,4}路|[a-zA-Z0-9]+街道|.{2,4}小区)'
                                    location_match = re.search(location_pattern, item.text)
                                    if location_match:
                                        location = location_match.group(0)
                                
                                # 获取房屋户型 - 使用多个选择器
                                house_type_text = "未知"
                                for type_selector in ['.house-type', '.huxing', '.type', '.rooms', '[class*="type"]', '[class*="huxing"]', '.layout', '.room', '.house-txt']:
                                    type_elem = item.select_one(type_selector)
                                    if type_elem:
                                        house_type_text = type_elem.text.strip()
                                        break
                                
                                # 如果户型信息不包含"室"，可能不是户型信息
                                if house_type_text != "未知" and "室" not in house_type_text:
                                    # 在房源元素的完整文本中搜索户型信息
                                    house_type_match = re.search(r'(\d+)\s*室\s*(\d+)\s*厅', item.text)
                                    if house_type_match:
                                        rooms, livingrooms = house_type_match.group(1), house_type_match.group(2)
                                        house_type_text = f"{rooms}室{livingrooms}厅"
                                    else:
                                        house_type_text = "未知"
                                
                                # 如果户型仍然未知，尝试更广泛的匹配
                                if house_type_text == "未知":
                                    # 搜索任何可能的户型信息
                                    house_pattern = r'(\d+)[室].*?(\d+)[厅厘]'
                                    house_match = re.search(house_pattern, item.text)
                                    if house_match:
                                        house_type_text = f"{house_match.group(1)}室{house_match.group(2)}厅"
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    # 在整个房源项元素的文本中查找户型信息
                                    room_match = re.search(r'(\d+)\s*室\s*(\d+)\s*厅', item.text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue  # 如果不符合筛选条件，跳过当前房源
                                        house_type_text = f"{rooms}室{livingrooms}厅"
                                    else:
                                        # 没找到户型信息，但有筛选条件，则跳过
                                        if bedroom_num or livingroom_num:
                                            continue
                                
                                # 获取建筑面积 - 使用多个选择器
                                area_text = "未知"
                                for area_selector in ['.area', '.square', '.size', '[class*="area"]', '[class*="square"]', '.house-area', '.area-num']:
                                    area_elem = item.select_one(area_selector)
                                    if area_elem:
                                        area_text = area_elem.text.strip()
                                        break
                                
                                # 从文本中提取数字作为面积
                                area = "未知"
                                # 先尝试从area_text中提取
                                if area_text != "未知":
                                    area_match = re.search(r'(\d+\.?\d*)\s*[平㎡]', area_text)
                                    if area_match:
                                        area = area_match.group(1)
                                
                                # 如果从area_text中没提取到，尝试从整个元素文本中提取
                                if area == "未知":
                                    area_match = re.search(r'(\d+\.?\d*)\s*[平㎡平米平方米]', item.text)
                                    if area_match:
                                        area = area_match.group(1)
                                
                                # 获取建筑年份（如果有的话）
                                build_year_found = "未知"
                                # 先通过选择器尝试查找
                                for year_selector in ['.year', '.time', '[class*="year"]', '[class*="build"]', '.tag']:
                                    year_elem = item.select_one(year_selector)
                                    if year_elem:
                                        year_text = year_elem.text.strip()
                                        year_match = re.search(r'(\d{4})\s*年', year_text)
                                        if year_match:
                                            build_year_found = year_match.group(1)
                                            break
                                
                                # 如果选择器未找到，尝试从整个元素文本中提取
                                if build_year_found == "未知":
                                    year_match = re.search(r'(\d{4})\s*年[建筑建成]?', item.text)
                                    if year_match:
                                        build_year_found = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件
                                if build_year and build_year_found != "未知":
                                    # 转换为整数进行比较
                                    try:
                                        if int(build_year_found) != int(build_year):
                                            continue
                                    except ValueError:
                                        pass
                                
                                # 构建数据项
                                house_data = {
                                    '名称': name,
                                    '价格': price_text,
                                    '位置': location,
                                    '户型': house_type_text,
                                    '面积(平方米)': area,
                                    '建筑年份': build_year_found,
                                    '平台': '安居客',
                                    '类型': house_type,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                logger.info(f"已爬取: {name} - {price_text} - {house_type_text}")
                                total_items += 1
                                
                            except Exception as e:
                                logger.error(f"处理房源项时出错: {e}")
                        
                        # 爬取成功，跳出重试循环
                        break
                    
                    else:
                        logger.warning(f"请求失败，状态码: {response.status_code}")
                        retry_count += 1
                    
                except Exception as e:
                    logger.error(f"爬取第{page}页时出错: {e}")
                    retry_count += 1
                
                # 如果需要重试，等待更长时间
                if retry_count < max_retries and retry_count > 0:
                    wait_time = self.get_random_delay() * (retry_count + 1)
                    logger.info(f"等待 {wait_time:.2f} 秒后重试...")
                    time.sleep(wait_time)
            
            # 正常延迟到下一页
            time.sleep(self.get_random_delay())
        
        logger.info(f"安居客爬取完成，共获取{total_items}条数据")
        return self.house_data
    
    def scrape_58(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, page_count=3):
        """
        爬取58同城房源数据
        
        参数:
            city: 城市名称
            house_type: 房源类型 (新房/二手房/租房)
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            build_year: 建筑年份
            page_count: 爬取页数
        """
        print(f"开始爬取58同城{city}{house_type}数据")
        if bedroom_num or livingroom_num:
            print(f"筛选条件: {bedroom_num}室{livingroom_num}厅")
        if build_year:
            print(f"建筑年份: {build_year}年")
        
        # 构建URL - 使用城市代码而不是直接使用中文名
        city_abbr = city  # 城市代码，例如郑州为zz
        if house_type == '新房':
            base_url = f"https://{city_abbr}.58.com/loupan/all/p{{}}"
        elif house_type == '二手房':
            base_url = f"https://{city_abbr}.58.com/ershoufang/p{{}}"
        else:  # 租房
            base_url = f"https://{city_abbr}.58.com/zufang/p{{}}"
        
        total_items = 0
        verification_handled = False
        
        for page in range(1, page_count + 1):
            url = base_url.format(page)
            headers = self.update_headers()
            
            try:
                print(f"正在爬取第{page}页: {url}")
                response = requests.get(url, headers=headers, timeout=10)
                
                # 检查是否需要验证
                if self.check_verification(response.text):
                    if not verification_handled:
                        verification_handled = self.handle_verification(url)
                        # 如果用户选择跳过验证，继续下一页
                        if not verification_handled:
                            print("用户选择跳过验证，继续下一页")
                            break
                        # 重新请求当前页
                        response = requests.get(url, headers=headers, timeout=10)
                    else:
                        print("仍然需要验证，可能验证未成功，跳过当前页")
                        continue
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 根据房源类型选择不同的选择器
                    if house_type == '新房':
                        house_items = soup.select('.key-list .item')
                        if not house_items:
                            print("未找到房源数据，尝试其他选择器")
                            house_items = soup.select('.property')  # 尝试新的选择器
                            if not house_items:
                                house_items = soup.select('.item')  # 再次尝试更通用的选择器
                            if not house_items:
                                print("所有选择器均未找到数据，可能需要更新")
                                continue
                        
                        print(f"成功找到 {len(house_items)} 个房源项")
                        
                        for item in house_items:
                            try:
                                # 获取房源名称
                                name = item.select_one('.lp-name').text.strip() if item.select_one('.lp-name') else "未知"
                                
                                # 获取房源价格
                                price_text = item.select_one('.price').text.strip() if item.select_one('.price') else "未知"
                                
                                # 获取房源地址
                                location = item.select_one('.address').text.strip() if item.select_one('.address') else "未知"
                                
                                # 获取房屋类型
                                house_type_text = ""
                                for tag in item.select('.tag-panel span'):
                                    text = tag.text.strip()
                                    if "室" in text and "厅" in text:
                                        house_type_text = text
                                        break
                                
                                # 获取建筑年份
                                year = "未知"
                                for tag in item.select('.tag-panel span'):
                                    year_match = re.search(r'(\d{4})年', tag.text)
                                    if year_match:
                                        year = year_match.group(1)
                                        break
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    if int(year) != int(build_year):
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = ""
                                for tag in item.select('.tag-panel span'):
                                    area_match = re.search(r'(\d+\.?\d*)平米', tag.text)
                                    if area_match:
                                        area_text = area_match.group(0)
                                        break
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '58同城',
                                    '名称': name,
                                    '价格': price_text,
                                    '位置': location,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {name} - {price_text} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    elif house_type == '二手房':
                        # 尝试多个可能的选择器
                        house_items = soup.select('.property')
                        if not house_items:
                            print("未找到房源数据，尝试其他选择器")
                            house_items = soup.select('.listItem')
                            if not house_items:
                                house_items = soup.select('li.house-cell')
                                if not house_items:
                                    house_items = soup.select('.house-item')
                                    if not house_items:
                                        print("所有选择器均未找到数据，可能需要更新")
                                        continue
                        
                        print(f"成功找到 {len(house_items)} 个房源项")
                        
                        for item in house_items:
                            try:
                                # 尝试不同的选择器组合来获取数据
                                # 获取房源标题
                                title = None
                                title_selectors = [
                                    '.title a', '.title', 'h3', '.house-title', '.property-content-title h3'
                                ]
                                for selector in title_selectors:
                                    title_elem = item.select_one(selector)
                                    if title_elem:
                                        title = title_elem.text.strip()
                                        break
                                
                                if not title:
                                    title = "未知"
                                
                                # 获取房源价格
                                price = None
                                price_selectors = [
                                    '.price', '.money', '.price-det', '.total-price', '.property-price', '.price_total'
                                ]
                                for selector in price_selectors:
                                    price_elem = item.select_one(selector)
                                    if price_elem:
                                        price = price_elem.text.strip()
                                        break
                                
                                if not price:
                                    price = "未知"
                                
                                # 获取房源地址
                                address = None
                                address_selectors = [
                                    '.address', '.list-cell-address', '.positionInfo', '.property-content-info'
                                ]
                                for selector in address_selectors:
                                    address_elem = item.select_one(selector)
                                    if address_elem:
                                        address = address_elem.text.strip()
                                        break
                                
                                if not address:
                                    address = "未知"
                                
                                # 获取房屋类型
                                house_type_text = ""
                                type_selectors = [
                                    '.houseInfo', '.room', '.property-content-info .property-content-info-text'
                                ]
                                
                                for selector in type_selectors:
                                    type_elems = item.select(selector)
                                    for elem in type_elems:
                                        text = elem.text.strip()
                                        if "室" in text and "厅" in text:
                                            house_type_text = text
                                            break
                                    if house_type_text:
                                        break
                                
                                # 如果还未找到户型信息，尝试从整个item文本中提取
                                if not house_type_text:
                                    item_text = item.text
                                    room_match = re.search(r'(\d+)室(\d+)厅', item_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = "未知"
                                area_match = re.search(r'(\d+\.?\d*)平米', item.text)
                                if area_match:
                                    area_text = area_match.group(0)
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '58同城',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    else:  # 租房
                        house_items = soup.select('.list-cell')
                        if not house_items:
                            print("未找到房源数据，尝试其他选择器")
                            house_items = soup.select('.property')
                            if not house_items:
                                house_items = soup.select('.card')
                                if not house_items:
                                    print("所有选择器均未找到数据，可能需要更新")
                                    continue
                                
                        print(f"成功找到 {len(house_items)} 个房源项")
                        
                        for item in house_items:
                            try:
                                # 获取房源标题
                                title = item.select_one('.list-cell-title a').text.strip() if item.select_one('.list-cell-title a') else "未知"
                                
                                # 获取房源价格
                                price_elem = item.select_one('.money')
                                price = price_elem.text.strip() + "元/月" if price_elem else "未知"
                                
                                # 获取房源地址
                                address = item.select_one('.list-cell-address a span').text.strip() if item.select_one('.list-cell-address a span') else "未知"
                                
                                # 获取房屋类型
                                house_type_text = ""
                                for tag in item.select('.list-cell-attribute li'):
                                    if "室" in tag.text and "厅" in tag.text:
                                        house_type_text = tag.text.strip()
                                        break
                                
                                # 获取建筑年份
                                year = "未知"
                                building_info = item.select_one('.list-cell-desc').text if item.select_one('.list-cell-desc') else ""
                                year_match = re.search(r'(\d{4})年', building_info)
                                if year_match:
                                    year = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    if int(year) != int(build_year):
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = ""
                                for tag in item.select('.list-cell-attribute li'):
                                    area_match = re.search(r'(\d+\.?\d*)平米', tag.text)
                                    if area_match:
                                        area_text = area_match.group(0)
                                        break
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '58同城',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                
                # 添加随机延迟，模拟人类行为
                time.sleep(self.get_random_delay())
                
            except Exception as e:
                print(f"爬取第{page}页时出错: {e}")
        
        print(f"成功从58同城爬取{total_items}条{house_type}数据")
        return total_items
    
    def scrape_beike(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, page_count=3):
        """
        爬取贝壳找房房源数据
        
        参数:
            city: 城市名称
            house_type: 房源类型 (新房/二手房/租房)
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            build_year: 建筑年份
            page_count: 爬取页数
        """
        print(f"开始爬取贝壳找房{city}{house_type}数据")
        if bedroom_num or livingroom_num:
            print(f"筛选条件: {bedroom_num}室{livingroom_num}厅")
        if build_year:
            print(f"建筑年份: {build_year}年")
        
        # 构建URL - 使用城市代码而不是直接使用中文名
        city_abbr = city  # 城市代码，例如郑州为zz
        if house_type == '新房':
            base_url = f"https://{city_abbr}.fang.ke.com/loupan/pg{{}}"
        elif house_type == '二手房':
            base_url = f"https://{city_abbr}.ke.com/ershoufang/pg{{}}"
        else:  # 租房
            base_url = f"https://{city_abbr}.zu.ke.com/zufang/pg{{}}"
        
        total_items = 0
        verification_handled = False
        
        for page in range(1, page_count + 1):
            url = base_url.format(page)
            headers = self.update_headers()
            
            try:
                print(f"正在爬取第{page}页: {url}")
                response = requests.get(url, headers=headers, timeout=10)
                
                # 检查是否需要验证
                if self.check_verification(response.text):
                    if not verification_handled:
                        verification_handled = self.handle_verification(url)
                        # 如果用户选择跳过验证，继续下一页
                        if not verification_handled:
                            print("用户选择跳过验证，继续下一页")
                            break
                        # 重新请求当前页
                        response = requests.get(url, headers=headers, timeout=10)
                    else:
                        print("仍然需要验证，可能验证未成功，跳过当前页")
                        continue
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 根据房源类型选择不同的选择器
                    if house_type == '新房':
                        house_items = soup.select('.resblock-list-wrapper .resblock-list')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源名称
                                name = item.select_one('.resblock-name a').text.strip() if item.select_one('.resblock-name a') else "未知"
                                
                                # 获取房源价格
                                price_elem = item.select_one('.number')
                                price_unit = item.select_one('.desc')
                                price = price_elem.text.strip() + (price_unit.text.strip() if price_unit else "") if price_elem else "未知"
                                
                                # 获取房源地址
                                location = item.select_one('.resblock-location').text.strip() if item.select_one('.resblock-location') else "未知"
                                
                                # 获取房屋类型
                                house_type_elem = item.select_one('.resblock-type')
                                house_type_text = house_type_elem.text.strip() if house_type_elem else "未知"
                                
                                # 获取建筑年份
                                year = "未知"
                                for tag in item.select('.resblock-tag span'):
                                    year_match = re.search(r'(\d{4})年', tag.text)
                                    if year_match:
                                        year = year_match.group(1)
                                        break
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    if int(year) != int(build_year):
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_spans = item.select('.resblock-room span')
                                    for span in room_spans:
                                        room_match = re.search(r'(\d+)室(\d+)厅', span.text)
                                        if room_match:
                                            rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                            if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                                continue
                                            house_type_text = span.text.strip()
                                            break
                                
                                # 获取面积
                                area_elem = item.select_one('.resblock-area')
                                area_text = area_elem.text.strip() if area_elem else "未知"
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '贝壳找房',
                                    '名称': name,
                                    '价格': price,
                                    '位置': location,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {name} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    elif house_type == '二手房':
                        house_items = soup.select('.sellListContent li.clear')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源标题
                                title = item.select_one('.title a').text.strip() if item.select_one('.title a') else "未知"
                                
                                # 获取房源价格
                                total_price = item.select_one('.totalPrice span')
                                unit_price = item.select_one('.unitPrice span')
                                price = (total_price.text.strip() + "万" if total_price else "") + (" (" + unit_price.text.strip() + ")" if unit_price else "")
                                
                                # 获取房源地址
                                address = item.select_one('.positionInfo').text.strip() if item.select_one('.positionInfo') else "未知"
                                
                                # 获取房屋信息
                                house_info = item.select_one('.houseInfo').text.strip() if item.select_one('.houseInfo') else ""
                                
                                # 提取户型
                                house_type_text = "未知"
                                room_match = re.search(r'(\d+)室(\d+)厅', house_info)
                                if room_match:
                                    house_type_text = room_match.group(0)
                                
                                # 获取建筑年份
                                year = "未知"
                                year_match = re.search(r'(\d{4})年建', house_info)
                                if year_match:
                                    year = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    try:
                                        if int(year) != int(build_year):
                                            continue
                                    except ValueError:
                                        # 如果年份转换失败，跳过当前房源
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = "未知"
                                area_match = re.search(r'(\d+\.?\d*)平米', house_info)
                                if area_match:
                                    area_text = area_match.group(0)
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '贝壳找房',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    else:  # 租房
                        house_items = soup.select('.content__list .content__list--item')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源标题
                                title = item.select_one('.content__list--item--title twoline').text.strip() if item.select_one('.content__list--item--title twoline') else "未知"
                                
                                # 获取房源价格
                                price_elem = item.select_one('.content__list--item-price')
                                price = price_elem.text.strip() + "元/月" if price_elem else "未知"
                                
                                # 获取房源地址
                                address = item.select_one('.content__list--item--des').text.strip() if item.select_one('.content__list--item--des') else "未知"
                                
                                # 获取房屋类型
                                house_type_text = "未知"
                                room_match = re.search(r'(\d+)室(\d+)厅', item.text)
                                if room_match:
                                    house_type_text = room_match.group(0)
                                
                                # 获取建筑年份
                                year = "未知"
                                year_match = re.search(r'(\d{4})年', item.text)
                                if year_match:
                                    year = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    try:
                                        if int(year) != int(build_year):
                                            continue
                                    except ValueError:
                                        # 如果年份转换失败，跳过当前房源
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = "未知"
                                area_match = re.search(r'(\d+\.?\d*)平米', item.text)
                                if area_match:
                                    area_text = area_match.group(0)
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '贝壳找房',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                
                # 添加随机延迟，模拟人类行为
                time.sleep(self.get_random_delay())
                
            except Exception as e:
                print(f"爬取第{page}页时出错: {e}")
        
        print(f"成功从贝壳找房爬取{total_items}条{house_type}数据")
        return total_items
    
    def scrape_lianjia(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, page_count=3):
        """
        爬取链家房源数据
        
        参数:
            city: 城市名称
            house_type: 房源类型 (新房/二手房/租房)
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            build_year: 建筑年份
            page_count: 爬取页数
        """
        print(f"开始爬取链家{city}{house_type}数据")
        if bedroom_num or livingroom_num:
            print(f"筛选条件: {bedroom_num}室{livingroom_num}厅")
        if build_year:
            print(f"建筑年份: {build_year}年")
        
        # 构建URL - 使用城市代码而不是直接使用中文名
        # 这里使用城市简写，不要直接使用中文
        city_abbr = city  # 城市代码，例如郑州为zz
        if house_type == '新房':
            base_url = f"https://{city_abbr}.fang.lianjia.com/loupan/pg{{}}"
        elif house_type == '二手房':
            base_url = f"https://{city_abbr}.lianjia.com/ershoufang/pg{{}}"
        else:  # 租房
            base_url = f"https://{city_abbr}.lianjia.com/zufang/pg{{}}"
        
        total_items = 0
        verification_handled = False
        
        for page in range(1, page_count + 1):
            url = base_url.format(page)
            headers = self.update_headers()
            
            try:
                print(f"正在爬取第{page}页: {url}")
                response = requests.get(url, headers=headers, timeout=10)
                
                # 检查是否需要验证
                if self.check_verification(response.text):
                    if not verification_handled:
                        verification_handled = self.handle_verification(url)
                        # 如果用户选择跳过验证，继续下一页
                        if not verification_handled:
                            print("用户选择跳过验证，继续下一页")
                            break
                        # 重新请求当前页
                        response = requests.get(url, headers=headers, timeout=10)
                    else:
                        print("仍然需要验证，可能验证未成功，跳过当前页")
                        continue
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 根据房源类型选择不同的选择器
                    if house_type == '新房':
                        house_items = soup.select('.resblock-list-wrapper .resblock-list')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源名称
                                name = item.select_one('.resblock-name a').text.strip() if item.select_one('.resblock-name a') else "未知"
                                
                                # 获取房源价格
                                price_elem = item.select_one('.number')
                                price_unit = item.select_one('.desc')
                                price = price_elem.text.strip() + (price_unit.text.strip() if price_unit else "") if price_elem else "未知"
                                
                                # 获取房源地址
                                location = item.select_one('.resblock-location').text.strip() if item.select_one('.resblock-location') else "未知"
                                
                                # 获取房屋类型
                                house_type_elem = item.select_one('.resblock-type')
                                house_type_text = house_type_elem.text.strip() if house_type_elem else "未知"
                                
                                # 获取建筑年份
                                year = "未知"
                                for tag in item.select('.resblock-tag span'):
                                    year_match = re.search(r'(\d{4})年', tag.text)
                                    if year_match:
                                        year = year_match.group(1)
                                        break
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    if int(year) != int(build_year):
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_spans = item.select('.resblock-room span')
                                    for span in room_spans:
                                        room_match = re.search(r'(\d+)室(\d+)厅', span.text)
                                        if room_match:
                                            rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                            if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                                continue
                                            house_type_text = span.text.strip()
                                            break
                                
                                # 获取面积
                                area_elem = item.select_one('.resblock-area')
                                area_text = area_elem.text.strip() if area_elem else "未知"
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '链家',
                                    '名称': name,
                                    '价格': price,
                                    '位置': location,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {name} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    elif house_type == '二手房':
                        house_items = soup.select('.sellListContent li.clear')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源标题
                                title = item.select_one('.title a').text.strip() if item.select_one('.title a') else "未知"
                                
                                # 获取房源价格
                                total_price = item.select_one('.totalPrice span')
                                unit_price = item.select_one('.unitPrice span')
                                price = (total_price.text.strip() + "万" if total_price else "") + (" (" + unit_price.text.strip() + ")" if unit_price else "")
                                
                                # 获取房源地址
                                address = item.select_one('.positionInfo').text.strip() if item.select_one('.positionInfo') else "未知"
                                
                                # 获取房屋信息
                                house_info = item.select_one('.houseInfo').text.strip() if item.select_one('.houseInfo') else ""
                                
                                # 提取户型
                                house_type_text = "未知"
                                room_match = re.search(r'(\d+)室(\d+)厅', house_info)
                                if room_match:
                                    house_type_text = room_match.group(0)
                                
                                # 获取建筑年份
                                year = "未知"
                                year_match = re.search(r'(\d{4})年建', house_info)
                                if year_match:
                                    year = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    try:
                                        if int(year) != int(build_year):
                                            continue
                                    except ValueError:
                                        # 如果年份转换失败，跳过当前房源
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = "未知"
                                area_match = re.search(r'(\d+\.?\d*)平米', house_info)
                                if area_match:
                                    area_text = area_match.group(0)
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '链家',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                    
                    else:  # 租房
                        house_items = soup.select('.content__list .content__list--item')
                        if not house_items:
                            print("未找到房源数据，可能需要更新选择器")
                            continue
                            
                        for item in house_items:
                            try:
                                # 获取房源标题
                                title = item.select_one('.content__list--item--title twoline').text.strip() if item.select_one('.content__list--item--title twoline') else "未知"
                                
                                # 获取房源价格
                                price_elem = item.select_one('.content__list--item-price')
                                price = price_elem.text.strip() + "元/月" if price_elem else "未知"
                                
                                # 获取房源地址
                                address = item.select_one('.content__list--item--des').text.strip() if item.select_one('.content__list--item--des') else "未知"
                                
                                # 获取房屋类型
                                house_type_text = "未知"
                                room_match = re.search(r'(\d+)室(\d+)厅', item.text)
                                if room_match:
                                    house_type_text = room_match.group(0)
                                
                                # 获取建筑年份
                                year = "未知"
                                year_match = re.search(r'(\d{4})年', item.text)
                                if year_match:
                                    year = year_match.group(1)
                                
                                # 如果指定了建筑年份筛选条件，检查是否符合
                                if build_year and year != "未知":
                                    try:
                                        if int(year) != int(build_year):
                                            continue
                                    except ValueError:
                                        # 如果年份转换失败，跳过当前房源
                                        continue
                                
                                # 如果需要筛选几室几厅
                                if bedroom_num or livingroom_num:
                                    room_match = re.search(r'(\d+)室(\d+)厅', house_type_text)
                                    if room_match:
                                        rooms, livingrooms = int(room_match.group(1)), int(room_match.group(2))
                                        if (bedroom_num and rooms != bedroom_num) or (livingroom_num and livingrooms != livingroom_num):
                                            continue
                                
                                # 获取面积
                                area_text = "未知"
                                area_match = re.search(r'(\d+\.?\d*)平米', item.text)
                                if area_match:
                                    area_text = area_match.group(0)
                                
                                # 构建数据项
                                house_data = {
                                    '平台': '链家',
                                    '名称': title,
                                    '价格': price,
                                    '位置': address,
                                    '户型': house_type_text,
                                    '面积': area_text,
                                    '建筑年份': year,
                                    '房源类型': house_type,
                                    '城市': city,
                                    '爬取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                }
                                
                                self.house_data.append(house_data)
                                total_items += 1
                                print(f"已爬取: {title} - {price} - {house_type_text}")
                                
                            except Exception as e:
                                print(f"处理房源项时出错: {e}")
                
                else:
                    print(f"请求失败，状态码: {response.status_code}")
                
                # 添加随机延迟，模拟人类行为
                time.sleep(self.get_random_delay())
                
            except Exception as e:
                print(f"爬取第{page}页时出错: {e}")
        
        print(f"成功从链家爬取{total_items}条{house_type}数据")
        return total_items
    
    def save_to_excel(self, filename=None):
        """将爬取的数据保存到Excel文件中"""
        if not self.house_data:
            print("没有数据可保存")
            return None
        
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{self.data_dir}/多平台房价数据_{timestamp}.xlsx"
        
        # 按平台和房源类型分类
        platforms = set(item['平台'] for item in self.house_data)
        house_types = set(item.get('类型', item.get('房源类型', '未知')) for item in self.house_data)
        
        # 创建Excel写入器
        with pd.ExcelWriter(filename) as writer:
            # 总数据表 - 增加平台标识列
            df_all = pd.DataFrame(self.house_data)
            
            # 确保'平台'和'类型'(或'房源类型')列是第一列和第二列
            if '平台' in df_all.columns:
                cols = ['平台'] + [col for col in df_all.columns if col != '平台']
                df_all = df_all[cols]
            
            # 统一房源类型列名
            if '类型' in df_all.columns and '房源类型' not in df_all.columns:
                df_all.rename(columns={'类型': '房源类型'}, inplace=True)
            elif '房源类型' in df_all.columns and '类型' not in df_all.columns:
                df_all.rename(columns={'房源类型': '类型'}, inplace=True)
            
            # 把类型列移到第二位
            if '类型' in df_all.columns:
                type_col = '类型'
            elif '房源类型' in df_all.columns:
                type_col = '房源类型'
            else:
                type_col = None
            
            if type_col:
                cols = [col for col in df_all.columns if col != type_col]
                idx = min(1, len(cols))
                cols.insert(idx, type_col)
                df_all = df_all[cols]
            
            # 保存全部数据
            df_all.to_excel(writer, sheet_name='全部数据', index=False)
            
            # 按平台分表 - 标题添加平台名称
            for platform in platforms:
                platform_data = [item for item in self.house_data if item['平台'] == platform]
                if platform_data:
                    df_platform = pd.DataFrame(platform_data)
                    
                    # 添加平台标识到每个表格的标题行
                    sheet_name = f'{platform}'
                    df_platform.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # 按房源类型分表 - 标题添加房源类型
            for house_type in house_types:
                # 考虑两种可能的键名
                type_data = [item for item in self.house_data 
                            if item.get('类型', item.get('房源类型', '未知')) == house_type]
                if type_data:
                    df_type = pd.DataFrame(type_data)
                    
                    # 添加房源类型标识到表格
                    sheet_name = f'{house_type}'
                    df_type.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # 按平台+房源类型分表 - 最清晰的分类方式
            for platform in platforms:
                for house_type in house_types:
                    # 考虑两种可能的键名
                    filtered_data = [item for item in self.house_data 
                                    if item['平台'] == platform and 
                                    (item.get('类型', item.get('房源类型', '未知')) == house_type)]
                    
                    if filtered_data:
                        df_filtered = pd.DataFrame(filtered_data)
                        
                        # 创建清晰的工作表名称
                        sheet_name = f'{platform}_{house_type}'
                        
                        # 如果名称过长，进行截断
                        if len(sheet_name) > 31:  # Excel工作表名称最长31个字符
                            sheet_name = sheet_name[:31]
                        
                        # 将平台名和房源类型添加到表格标题中
                        df_filtered.to_excel(writer, sheet_name=sheet_name, index=False)
        
        print(f"数据已保存到: {filename}")
        print(f"包含以下工作表:")
        print(f"1. 全部数据 - 包含所有平台的所有房源数据")
        for platform in platforms:
            print(f"2. {platform} - 仅包含{platform}的房源数据")
        for house_type in house_types:
            print(f"3. {house_type} - 仅包含{house_type}类型的房源数据")
        for platform in platforms:
            for house_type in house_types:
                print(f"4. {platform}_{house_type} - 仅包含{platform}的{house_type}类型房源数据")
        
        return filename
    
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
            self.debug_dir,  # 调试页面
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


def main():
    """主函数"""
    print("=" * 50)
    print("多平台房价数据爬虫程序")
    print("=" * 50)
    
    scraper = MultiPlatformHousingScraper()
    
    # 清理过期文件
    scraper.cleanup_old_files()
    
    while True:
        print("\n请选择要爬取的平台:")
        print("1. 安居客")
        print("2. 58同城")
        print("3. 贝壳找房")
        print("4. 链家")
        print("5. 所有平台")
        print("0. 退出程序")
        
        platform_choice = input("请输入选项 (0-5): ").strip()
        
        if platform_choice == '0':
            print("程序已退出")
            break
        
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
                    scraper.save_to_excel()
                
            # 询问是否继续
            continue_option = input("\n是否继续爬取其他数据? (y/n): ").strip().lower()
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


if __name__ == "__main__":
    main() 