#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import time
import random
import logging
import requests
import pandas as pd
import functools
from datetime import datetime
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# 检查是否可以导入自动验证模块
try:
    from auto_verification import AutoVerificationHandler
    AUTO_VERIFICATION_AVAILABLE = True
except ImportError:
    AUTO_VERIFICATION_AVAILABLE = False

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("housing_scraper.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("house_scraper")

# 城市代码映射
CITY_CODES = {
    "北京": "bj", "上海": "sh", "广州": "gz", "深圳": "sz", "成都": "cd",
    "杭州": "hz", "重庆": "cq", "武汉": "wh", "苏州": "su", "西安": "xa",
    "天津": "tj", "南京": "nj", "郑州": "zz", "长沙": "cs", "沈阳": "sy",
    "青岛": "qd", "宁波": "nb", "东莞": "dg", "无锡": "wx", "昆明": "km"
}

def set_debug_level(debug=False):
    """设置日志级别
    
    Args:
        debug: 是否开启调试模式
    """
    if debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("已开启调试模式")
    else:
        logger.setLevel(logging.INFO)
        logger.info("已关闭调试模式")

# 异常类
class ScraperException(Exception):
    """爬虫相关异常的基类"""
    pass

class VerificationException(ScraperException):
    """验证码相关异常"""
    pass

class ParsingException(ScraperException):
    """解析数据时的异常"""
    pass

class NetworkException(ScraperException):
    """网络请求相关异常"""
    pass

# 装饰器用于统一的异常处理和日志记录
def safe_scraper(func):
    """装饰器: 为爬取函数提供异常处理和日志记录
    
    Args:
        func: 需要装饰的爬取函数
        
    Returns:
        包装后的函数
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        function_name = func.__name__
        logger.info(f"开始执行 {function_name}")
        
        try:
            result = func(self, *args, **kwargs)
            logger.info(f"{function_name} 执行完成")
            return result
        except VerificationException as e:
            logger.error(f"{function_name} 验证错误: {str(e)}")
            raise
        except ParsingException as e:
            logger.error(f"{function_name} 解析错误: {str(e)}")
            raise
        except NetworkException as e:
            logger.error(f"{function_name} 网络错误: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"{function_name} 未知错误: {str(e)}")
            raise
            
    return wrapper

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
                    "滑动验证", "请完成验证", "安全检测", "captcha.58.com",
                    "请输入验证码", "ws:", "请完成下列验证"
                ]
                
                for keyword in tc58_verification_keywords:
                    if keyword in response_text:
                        logger.info(f"检测到58同城验证关键词: {keyword}")
                        return True
                
                # 检查58同城特有的验证页面特征
                if "antirobot" in response_text or "security-verification" in response_text:
                    logger.warning("58同城页面包含验证元素")
                    return True
                
                # 检查页面长度，验证页面通常很短
                if len(response_text) < 10000 and "58.com" in response_text:
                    # 检查页面标题
                    title_match = re.search(r'<title>(.*?)</title>', response_text)
                    if title_match:
                        title = title_match.group(1)
                        if "验证" in title or "请输入验证码" in title:
                            logger.warning(f"58同城页面标题包含验证提示: {title}")
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

    @safe_scraper
    def scrape_anjuke(self, city, house_type, bedroom_num, livingroom_num, build_year, page_count, enable_layout_image=False):
        """爬取安居客房源数据
        
        参数:
            city: 城市名称，如'北京'
            house_type: 房源类型，如'new'(新房),'second'(二手房),'rent'(租房)
            bedroom_num: 卧室数量筛选，None表示不限
            livingroom_num: 客厅数量筛选，None表示不限
            build_year: 建筑年份筛选，None表示不限
            page_count: 爬取页数
            enable_layout_image: 是否获取户型图，默认False
            
        返回:
            bool: 是否爬取成功
        """
        print(f"开始爬取安居客-{house_type}，城市: {city}")
        logger.info(f"开始爬取安居客-{house_type}，城市: {city}")
        
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
        
        # 安居客URL模板
        url_templates = {
            '新房': 'https://{city}.fang.anjuke.com/loupan/all/p{page}/',
            '二手房': 'https://{city}.anjuke.com/sale/p{page}/',
            '租房': 'https://{city}.anjuke.com/rental/p{page}/'
        }
        
        # 获取城市对应的拼音代码
        city_abbr = None
        for name, code in CITY_CODES.items():
            if city in name or name in city:
                city_abbr = code
                break
                                
        if not city_abbr:
            # 如果没有找到城市代码，尝试直接使用城市名称作为拼音代码
            city_abbr = city
            logger.warning(f"未找到城市'{city}'的代码，将直接使用城市名称")
        
        # 当前类型的URL模板
        if house_type not in url_templates:
            logger.error(f"不支持的房源类型: {house_type}")
            return False
            
        url_template = url_templates[house_type]
        
        total_items = 0
        
        # 记录验证次数，避免无限循环
        verification_attempts = 0
        max_verification_attempts = 3
        
        try:
            # 爬取指定页数
            for page in range(1, page_count + 1):
                # 检查是否达到最大验证尝试次数
                if verification_attempts >= max_verification_attempts:
                    logger.warning(f"达到最大验证尝试次数 ({max_verification_attempts})，停止爬取")
                    return True  # 返回真以避免GUI中的重试循环
                
                # 构建当前页URL
                page_url = url_template.format(city=city_abbr, page=page)
                logger.info(f"爬取页面: {page}/{page_count}, URL: {page_url}")
                
                # 添加随机延迟(1-3秒)，模拟人类行为
                delay = self.get_random_delay()
                logger.debug(f"请求前随机延迟 {delay:.2f} 秒")
                time.sleep(delay)
                
                # 使用随机User-Agent
                headers = self.update_headers()
                
                try:
                    response = requests.get(page_url, headers=headers, timeout=15)
                except Exception as e:
                    logger.error(f"请求页面失败: {e}")
                    continue
                
                # 检查是否需要验证
                if self.check_verification(response.text, "anjuke", page_url):
                    logger.warning("检测到安居客需要验证")
                    verification_attempts += 1
                    logger.info(f"验证尝试次数: {verification_attempts}/{max_verification_attempts}")
                    
                    if verification_attempts >= max_verification_attempts:
                        logger.warning("达到最大验证尝试次数，停止当前爬取")
                        return True  # 提前返回避免无限循环
                    
                    verify_success = self.handle_verification("anjuke", page_url)
                    if not verify_success:
                        logger.warning("验证失败或用户选择跳过，继续下一页")
                        continue
                    
                    # 验证成功后增加略长延迟，并重新请求页面
                    time.sleep(2)
                    try:
                        headers = self.update_headers()
                        response = requests.get(page_url, headers=headers, timeout=15)
                    except Exception as e:
                        logger.error(f"验证后重新请求页面失败: {e}")
                        continue
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 根据房源类型选择不同的选择器
                if house_type == '新房':
                    # 新房选择器
                    items = soup.select('.item-mod') or soup.select('.key-list .item') or soup.select('.key-list li')
                    logger.info(f"找到 {len(items)} 个新房项目")
                    
                elif house_type == '二手房':
                    # 二手房选择器
                    items = (
                        soup.select('.property-item') or 
                        soup.select('.house-list .item') or 
                        soup.select('.houselist-mod-wrap .list-item') or
                        soup.select('.house-details') or
                        soup.select('.sale-item') or
                        soup.select('.list-content > div')
                    )
                    logger.info(f"找到 {len(items)} 个二手房项目")
                    
                else:  # 租房
                    # 租房选择器
                    items = (
                        soup.select('.zu-itemmod') or 
                        soup.select('.zu-item') or 
                        soup.select('.list-content .item') or
                        soup.select('.rent-list-item')
                    )
                    logger.info(f"找到 {len(items)} 个租房项目")
                
                # 如果找不到房源项，可能是被反爬
                if len(items) == 0:
                    logger.warning(f"未找到任何房源项，可能是被反爬或验证页面")
                    verification_attempts += 1
                    continue  # 跳过当前页，尝试下一页
                
                # 处理每个房源项
                for item in items:
                    try:
                        # 提取房源名称
                        name_elem = item.select_one('h3') or item.select_one('.house-title') or item.select_one('.items-name')
                        house_name = name_elem.get_text(strip=True) if name_elem else "未知房源"
                        
                        # 提取价格
                        price_elem = item.select_one('.price') or item.select_one('.price-det') or item.select_one('.favor-pos')
                        price = price_elem.get_text(strip=True) if price_elem else "价格未知"
                        
                        # 提取地址/位置
                        address_elem = (
                            item.select_one('.address') or 
                            item.select_one('.details-item-p') or 
                            item.select_one('.comm-address') or
                            item.select_one('.list-map')
                        )
                        address = address_elem.get_text(strip=True) if address_elem else "位置未知"
                        
                        # 提取房源类型
                        type_elem = item.select_one('.huxing') or item.select_one('.item-value.huxing') or item.select_one('.details-item span')
                        house_type_text = type_elem.get_text(strip=True) if type_elem else ""
                        
                        # 提取面积
                        area_elem = item.select_one('.infos .area') or item.select_one('.item-value.area')
                        area_text = area_elem.get_text(strip=True) if area_elem else ""
                        
                        # 提取建筑年份
                        year = None
                        if house_type in ['新房', '二手房']:
                            # 新房和二手房可能有年份信息
                            info_elems = item.select('.details-item') or item.select('.housing-info li')
                            for info in info_elems:
                                info_text = info.get_text(strip=True)
                                if '年' in info_text and ('建' in info_text or '造' in info_text):
                                    year_match = re.search(r'(\d{4})', info_text)
                                    if year_match:
                                        year = year_match.group(1)
                                        break
                        
                        # 检查是否符合房间数筛选条件
                        if bedroom_num is not None or livingroom_num is not None:
                            pattern = r'(\d+)室(\d+)厅'
                            match = re.search(pattern, house_type_text)
                            
                            if match:
                                rooms = int(match.group(1))
                                living = int(match.group(2))
                                
                                if bedroom_num is not None and rooms != bedroom_num:
                                    logger.debug(f"房源 '{house_name}' 卧室数不符合要求，跳过")
                                    continue
                                
                                if livingroom_num is not None and living != livingroom_num:
                                    logger.debug(f"房源 '{house_name}' 客厅数不符合要求，跳过")
                                    continue
                        
                        # 检查是否符合建筑年份筛选条件
                        if build_year is not None and year:
                            try:
                                if int(year) != build_year:
                                    logger.debug(f"房源 '{house_name}' 建筑年份不符合要求，跳过")
                                    continue
                            except ValueError:
                                logger.debug(f"房源 '{house_name}' 建筑年份解析失败: {year}")
                        
                        # 尝试提取详情页链接
                        detail_url = None
                        link_elem = item.select_one('a[href]')
                        if link_elem:
                            detail_url = link_elem.get('href')
                            # 确保链接是完整的URL
                            if detail_url and not detail_url.startswith('http'):
                                if detail_url.startswith('/'):
                                    base_url = f"https://{city_abbr}.anjuke.com"
                                    detail_url = base_url + detail_url
                                else:
                                    detail_url = f"https://{city_abbr}.anjuke.com/{detail_url}"
                        
                        # 尝试获取坐标信息
                        lat, lng = None, None
                        if house_type == '二手房':
                            try:
                                # 安居客二手房页面可能有隐藏的坐标信息
                                map_elem = item.select_one('[data-latitude]')
                                if map_elem:
                                    lat = map_elem.get('data-latitude')
                                    lng = map_elem.get('data-longitude')
                            except Exception:
                                pass
                        
                        # 尝试获取户型图
                        layout_image = None
                        if enable_layout_image and detail_url and house_type in ['新房', '二手房']:
                            try:
                                layout_image = self.extract_layout_image(detail_url, house_type)
                            except Exception as e:
                                logger.error(f"提取户型图失败: {e}")
                        
                        # 构建数据项
                        house_item = {
                            'platform': '安居客',
                            'city': city,
                            'house_name': house_name,
                            'price': price,
                            'address': address,
                            'house_type': house_type_text,
                            'area': area_text,
                            'year': year,
                            'type': house_type,
                            'latitude': lat,
                            'longitude': lng,
                            'detail_url': detail_url,
                            'layout_image': layout_image
                        }
                        
                        # 添加到数据集
                        self.house_data.append(house_item)
                        total_items += 1
                        
                    except Exception as e:
                        logger.error(f"处理房源项时出错: {str(e)}")
                
                logger.info(f"已爬取安居客-{house_type} 第 {page} 页, 累计 {total_items} 条数据")
            
            logger.info(f"安居客-{house_type} 爬取完成，共获取 {total_items} 条数据")
            print(f"安居客-{house_type} 爬取完成，共获取 {total_items} 条数据")
            return True
            
        except Exception as e:
            logger.error(f"安居客-{house_type} 爬取过程出错: {str(e)}")
            print(f"安居客-{house_type} 爬取过程出错: {str(e)}")
            return False 

    def extract_layout_image(self, detail_url, house_type):
        """提取户型图URL
        
        Args:
            detail_url: 详情页URL
            house_type: 房源类型
            
        Returns:
            str: 户型图URL或None
        """
        try:
            logger.debug(f"尝试提取户型图: {detail_url}")
            
            # 随机延迟(0.5-1.5秒)，避免太频繁请求
            time.sleep(random.uniform(0.5, 1.5))
            
            headers = self.update_headers()
            response = requests.get(detail_url, headers=headers, timeout=15)
            
            if self.check_verification(response.text, url=detail_url):
                logger.warning(f"提取户型图时遇到验证，跳过")
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 根据房源类型选择不同的选择器
            if "anjuke" in detail_url:
                if house_type == '新房':
                    # 新房户型图
                    imgs = soup.select('.hx-list img') or soup.select('.ho-list img') or soup.select('.huxing-box img')
                    if imgs:
                        return imgs[0].get('src')
                elif house_type == '二手房':
                    # 二手房户型图
                    imgs = soup.select('.huxing-pic img') or soup.select('.house-type img') or soup.select('.quanjing-box img')
                    if imgs:
                        return imgs[0].get('src')
                    
            elif "58.com" in detail_url:
                if house_type == '新房':
                    imgs = soup.select('.hx-list img') or soup.select('.hu-list img')
                    if imgs:
                        return imgs[0].get('src')
                elif house_type == '二手房':
                    imgs = soup.select('.picList img') or soup.select('.house-pic-list img') or soup.select('.house-type-pic img')
                    for img in imgs:
                        alt = img.get('alt', '')
                        if '户型图' in alt or '平面图' in alt:
                            return img.get('src')
                    # 如果没有明确标为户型图的图片，尝试找第一张
                    if imgs:
                        return imgs[0].get('src')
            
            elif "ke.com" in detail_url or "lianjia.com" in detail_url:
                # 贝壳/链家户型图
                imgs = soup.select('.content-img img') or soup.select('.layout img') or soup.select('.thumbnail img')
                if imgs:
                    for img in imgs:
                        alt = img.get('alt', '')
                        if '户型图' in alt:
                            return img.get('src')
                    # 如果没有明确标为户型图的图片，尝试找第一张
                    return imgs[0].get('src')
            
            logger.debug(f"未找到户型图")
            return None
            
        except Exception as e:
            logger.error(f"提取户型图出错: {e}")
            return None
            
    @safe_scraper
    def scrape_beike(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, pages=3, enable_layout_image=False):
        """爬取贝壳找房数据
        
        参数:
            city: 城市名称，如'北京'
            house_type: 房源类型，如'新房','二手房','租房'
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            build_year: 建筑年份
            pages: 爬取页数
            enable_layout_image: 是否获取户型图
            
        返回:
            bool: 是否爬取成功
        """
        print(f"开始爬取贝壳找房-{house_type}，城市: {city}")
        logger.info(f"开始爬取贝壳找房-{house_type}，城市: {city}")
        
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
        
        # URL模板
        url_templates = {
            '新房': 'https://{city}.fang.ke.com/loupan/pg{page}/',
            '二手房': 'https://{city}.ke.com/ershoufang/pg{page}/',
            '租房': 'https://{city}.zu.ke.com/zufang/pg{page}/'
        }
        
        # 将城市转换为拼音代码
        city_abbr = self._get_city_pinyin(city)
        if not city_abbr:
            logger.error(f"未找到城市'{city}'的拼音代码")
            return False
        
        # 根据房源类型选择URL模板
        if house_type not in url_templates:
            logger.error(f"不支持的房源类型: {house_type}")
            return False
            
        url_template = url_templates[house_type]
        
        # 爬取多页
        total_items = 0
        try:
            for page in range(1, pages + 1):
                page_url = url_template.format(city=city_abbr, page=page)
                logger.info(f"爬取页面: {page_url}")
                
                # 添加随机延迟
                time.sleep(self.get_random_delay())
                
                # 发送请求
                headers = self.update_headers()
                try:
                    response = requests.get(page_url, headers=headers, timeout=15)
                except Exception as e:
                    logger.error(f"请求页面失败: {e}")
                    continue
                
                # 检查是否需要验证
                if self.check_verification(response.text, "beike", page_url):
                    logger.warning("检测到贝壳找房需要验证")
                    verify_success = self.handle_verification("beike", page_url)
                    if not verify_success:
                        logger.warning("验证失败，跳过当前页面")
                        continue
                    
                    # 验证成功后重新请求
                    headers = self.update_headers()
                    response = requests.get(page_url, headers=headers, timeout=15)
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 根据房源类型选择不同的选择器查找房源项
                if house_type == '新房':
                    items = soup.select('.resblock-list .resblock-item')
                elif house_type == '二手房':
                    items = soup.select('.sellListContent .clear')
                else:  # 租房
                    items = soup.select('.content__list .content__list--item')
                
                logger.info(f"找到 {len(items)} 个房源项")
                
                # 处理每个房源项
                for item in items:
                    try:
                        # 根据房源类型提取信息
                        house_name = "未知房源"
                        price = "价格未知"
                        address = "位置未知"
                        house_type_text = ""
                        area_text = ""
                        year = None
                        detail_url = None
                        
                        if house_type == '新房':
                            # 新房信息提取
                            name_elem = item.select_one('.resblock-name')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.number')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                unit_elem = item.select_one('.desc')
                                if unit_elem:
                                    price = f"{price} {unit_elem.get_text(strip=True)}"
                                    
                            address_elem = item.select_one('.resblock-location')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                            area_elem = item.select_one('.resblock-area')
                            if area_elem:
                                area_text = area_elem.get_text(strip=True)
                                
                            # 新房可能没有明确的建筑年份
                            
                            # 获取详情页链接
                            link_elem = item.select_one('.resblock-name a')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.fang.ke.com{detail_url}"
                            
                        elif house_type == '二手房':
                            # 二手房信息提取
                            name_elem = item.select_one('.title')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.totalPrice')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                
                            address_elem = item.select_one('.positionInfo')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                            house_type_elem = item.select_one('.houseInfo')
                            if house_type_elem:
                                house_type_text = house_type_elem.get_text(strip=True)
                                
                                # 从户型信息中提取面积
                                area_match = re.search(r'(\d+(?:\.\d+)?)平米', house_type_text)
                                if area_match:
                                    area_text = f"{area_match.group(1)}平米"
                                
                                # 从户型信息中尝试提取年份
                                year_match = re.search(r'(\d{4})年', house_type_text)
                                if year_match:
                                    year = year_match.group(1)
                                
                            # 获取详情页链接
                            link_elem = item.select_one('.title a')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.ke.com{detail_url}"
                            
                        else:  # 租房
                            # 租房信息提取
                            name_elem = item.select_one('.content__list--item--title')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.content__list--item-price')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                
                            address_elem = item.select_one('.content__list--item--des')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                                # 从地址信息中提取户型和面积
                                info_text = address
                                room_match = re.search(r'(\d+)室(\d+)厅', info_text)
                                if room_match:
                                    house_type_text = f"{room_match.group(1)}室{room_match.group(2)}厅"
                                
                                area_match = re.search(r'(\d+(?:\.\d+)?)平米', info_text)
                                if area_match:
                                    area_text = f"{area_match.group(1)}平米"
                                
                            # 获取详情页链接
                            link_elem = item.select_one('.content__list--item--title a')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.zu.ke.com{detail_url}"
                        
                        # 检查是否符合过滤条件
                        if bedroom_num is not None or livingroom_num is not None:
                            room_pattern = r'(\d+)室(\d+)厅'
                            room_match = re.search(room_pattern, house_type_text)
                            
                            if room_match:
                                rooms = int(room_match.group(1))
                                living = int(room_match.group(2))
                                
                                if bedroom_num is not None and rooms != bedroom_num:
                                    continue
                                
                                if livingroom_num is not None and living != livingroom_num:
                                    continue
                        
                        # 检查年份
                        if build_year is not None and year:
                            try:
                                if int(year) != build_year:
                                    continue
                            except ValueError:
                                pass
                        
                        # 尝试获取户型图
                        layout_image = None
                        if enable_layout_image and detail_url:
                            try:
                                layout_image = self.extract_layout_image(detail_url, house_type)
                            except Exception as e:
                                logger.error(f"提取户型图失败: {e}")
                        
                        # 尝试获取坐标
                        lat, lng = None, None
                        
                        # 构建数据项
                        house_item = {
                            'platform': '贝壳找房',
                            'city': city,
                            'house_name': house_name,
                            'price': price,
                            'address': address,
                            'house_type': house_type_text,
                            'area': area_text,
                            'year': year,
                            'type': house_type,
                            'latitude': lat,
                            'longitude': lng,
                            'detail_url': detail_url,
                            'layout_image': layout_image
                        }
                        
                        self.house_data.append(house_item)
                        total_items += 1
                        
                    except Exception as e:
                        logger.error(f"处理房源项时出错: {str(e)}")
                
                logger.info(f"已爬取贝壳找房-{house_type} 第 {page} 页, 累计 {total_items} 条数据")
            
            logger.info(f"贝壳找房-{house_type} 爬取完成，共获取 {total_items} 条数据")
            print(f"贝壳找房-{house_type} 爬取完成，共获取 {total_items} 条数据")
            return True
            
        except Exception as e:
            logger.error(f"贝壳找房-{house_type} 爬取过程出错: {str(e)}")
            print(f"贝壳找房-{house_type} 爬取过程出错: {str(e)}")
            return False
    
    @safe_scraper
    def scrape_lianjia(self, city, house_type, bedroom_num=None, livingroom_num=None, build_year=None, pages=3, enable_layout_image=False):
        """爬取链家房源数据
        
        参数与scrape_beike相同，这里转发到贝壳找房爬虫
        """
        logger.info(f"链家爬取请求转发到贝壳找房爬虫")
        return self.scrape_beike(city, house_type, bedroom_num, livingroom_num, build_year, pages, enable_layout_image)
    
    @safe_scraper
    def scrape_58(self, city_abbr, house_type='second', bedroom_num=None, livingroom_num=None, building_year=None, pages=3, enable_layout_image=False):
        """爬取58同城房源数据
        
        参数:
            city_abbr: 城市代码，如'bj'表示北京
            house_type: 房源类型，'new'(新房),'second'(二手房),'rent'(租房)
            bedroom_num: 卧室数量
            livingroom_num: 客厅数量
            building_year: 建筑年份
            pages: 爬取页数
            enable_layout_image: 是否获取户型图
        
        返回:
            bool: 是否爬取成功
        """
        print(f"开始爬取58同城-{house_type}，城市代码: {city_abbr}")
        logger.info(f"开始爬取58同城-{house_type}，城市代码: {city_abbr}")
        
        # 检查筛选条件
        filter_conditions = []
        if bedroom_num is not None:
            filter_conditions.append(f"卧室数: {bedroom_num}")
        if livingroom_num is not None:
            filter_conditions.append(f"客厅数: {livingroom_num}")
        if building_year is not None:
            filter_conditions.append(f"建筑年份: {building_year}")
            
        if filter_conditions:
            logger.info(f"筛选条件: {', '.join(filter_conditions)}")
        
        # URL模板
        url_templates = {
            'new': f'https://{city_abbr}.58.com/loupan/all/p{{page}}/',
            'second': f'https://{city_abbr}.58.com/ershoufang/p{{page}}/',
            'rent': f'https://{city_abbr}.58.com/zufang/p{{page}}/'
        }
        
        # 验证城市代码
        if not city_abbr:
            logger.error("未提供有效的城市代码")
            return False
        
        # 验证房源类型
        if house_type not in url_templates:
            logger.error(f"不支持的房源类型: {house_type}")
            return False
        
        url_template = url_templates[house_type]
        
        # 爬取多页
        total_items = 0
        try:
            for page in range(1, pages + 1):
                page_url = url_template.format(page=page)
                logger.info(f"爬取页面: {page_url}")
                
                # 添加随机延迟
                time.sleep(self.get_random_delay())
                
                # 发送请求
                headers = self.update_headers()
                try:
                    response = requests.get(page_url, headers=headers, timeout=15)
                except Exception as e:
                    logger.error(f"请求页面失败: {e}")
                    continue
                
                # 检查是否需要验证
                if self.check_verification(response.text, "58", page_url):
                    logger.warning("检测到58同城需要验证")
                    verify_success = self.handle_verification("58", page_url)
                    if not verify_success:
                        logger.warning("验证失败，跳过当前页面")
                        continue
                    
                    # 验证成功后重新请求
                    headers = self.update_headers()
                    response = requests.get(page_url, headers=headers, timeout=15)
                
                # 解析HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 根据房源类型选择不同的选择器
                if house_type == 'new':
                    # 新房选择器
                    items = soup.select('.key-list .item') or soup.select('.newhouse-fang-list li.item')
                elif house_type == 'second':
                    # 二手房选择器
                    items = soup.select('.house-list-wrap li') or soup.select('.house-list li')
                else:  # 租房
                    # 租房选择器
                    items = soup.select('.listUl li') or soup.select('.list li')
                
                logger.info(f"找到 {len(items)} 个房源项")
                
                # (... 省略处理每个房源的详细代码 ...)
                for item in items:
                    try:
                        # 提取房源信息
                        house_name = "未知房源"
                        price = "价格未知"
                        address = "位置未知"
                        house_type_text = ""
                        area_text = ""
                        year = None
                        detail_url = None
                        
                        # 根据房源类型选择不同的提取方式
                        if house_type == 'new':
                            # 新房信息提取
                            name_elem = item.select_one('.title') or item.select_one('.lp-name')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.price') or item.select_one('.favor-pos')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                
                            address_elem = item.select_one('.address') or item.select_one('.area-street')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                            link_elem = item.select_one('a[href]')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.58.com{detail_url}"
                            
                        elif house_type == 'second':
                            # 二手房信息提取
                            name_elem = item.select_one('.title') or item.select_one('h3')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.price') or item.select_one('.sum')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                
                            address_elem = item.select_one('.address') or item.select_one('.addr')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                            # 提取户型信息
                            info_elems = item.select('.info p') or item.select('.baseinfo span')
                            for elem in info_elems:
                                text = elem.get_text(strip=True)
                                if '室' in text and '厅' in text:
                                    house_type_text = text
                                elif '平米' in text or '㎡' in text:
                                    area_text = text
                                elif '年建' in text or '建成' in text:
                                    year_match = re.search(r'(\d{4})', text)
                                    if year_match:
                                        year = year_match.group(1)
                            
                            # 提取详情页链接
                            link_elem = item.select_one('a[href]')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.58.com{detail_url}"
                        
                        else:  # 租房
                            # 租房信息提取
                            name_elem = item.select_one('.title') or item.select_one('h3')
                            if name_elem:
                                house_name = name_elem.get_text(strip=True)
                                
                            price_elem = item.select_one('.money') or item.select_one('.price')
                            if price_elem:
                                price = price_elem.get_text(strip=True)
                                
                            address_elem = item.select_one('.address') or item.select_one('.add')
                            if address_elem:
                                address = address_elem.get_text(strip=True)
                                
                            # 提取户型和面积
                            info_elems = item.select('.info p') or item.select('.item-info li')
                            for elem in info_elems:
                                text = elem.get_text(strip=True)
                                if '室' in text and '厅' in text:
                                    house_type_text = text
                                elif '平米' in text or '㎡' in text:
                                    area_text = text
                            
                            # 提取详情页链接
                            link_elem = item.select_one('a[href]')
                            if link_elem:
                                detail_url = link_elem.get('href')
                                if detail_url and not detail_url.startswith('http'):
                                    detail_url = f"https://{city_abbr}.58.com{detail_url}"
                        
                        # 检查是否符合过滤条件
                        if bedroom_num is not None or livingroom_num is not None:
                            room_pattern = r'(\d+)室(\d+)厅'
                            room_match = re.search(room_pattern, house_type_text)
                            
                            if room_match:
                                rooms = int(room_match.group(1))
                                living = int(room_match.group(2))
                                
                                if bedroom_num is not None and rooms != bedroom_num:
                                    continue
                                
                                if livingroom_num is not None and living != livingroom_num:
                                    continue
                        
                        # 检查年份
                        if building_year is not None and year:
                            try:
                                if int(year) != building_year:
                                    continue
                            except ValueError:
                                pass
                        
                        # 尝试获取户型图
                        layout_image = None
                        if enable_layout_image and detail_url:
                            try:
                                layout_image = self.extract_layout_image(detail_url, house_type)
                            except Exception as e:
                                logger.error(f"提取户型图失败: {e}")
                        
                        # 构建数据项
                        house_item = {
                            'platform': '58同城',
                            'city': city_abbr,
                            'house_name': house_name,
                            'price': price,
                            'address': address,
                            'house_type': house_type_text,
                            'area': area_text,
                            'year': year,
                            'type': house_type,
                            'detail_url': detail_url,
                            'layout_image': layout_image
                        }
                        
                        self.house_data.append(house_item)
                        total_items += 1
                        
                    except Exception as e:
                        logger.error(f"处理房源项时出错: {str(e)}")
                
                logger.info(f"已爬取58同城-{house_type} 第 {page} 页, 累计 {total_items} 条数据")
            
            logger.info(f"58同城-{house_type} 爬取完成，共获取 {total_items} 条数据")
            print(f"58同城-{house_type} 爬取完成，共获取 {total_items} 条数据")
            return True
            
        except Exception as e:
            logger.error(f"58同城-{house_type} 爬取过程出错: {str(e)}")
            print(f"58同城-{house_type} 爬取过程出错: {str(e)}")
            return False
            
    def _get_city_pinyin(self, city):
        """获取城市拼音代码"""
        for name, code in CITY_CODES.items():
            if city in name or name in city:
                return code
        return None 

    def save_to_excel(self, filename=None):
        """将爬取的房源数据保存为Excel文件
        
        参数:
            filename: 保存的文件名，如果为None则使用默认文件名
            
        返回:
            str: 保存的文件路径
        """
        if not self.house_data:
            logger.warning("没有数据可保存")
            return None
            
        if filename is None:
            # 使用当前时间作为默认文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"house_data_{timestamp}.xlsx"
        
        # 确保文件有.xlsx后缀
        if not filename.endswith('.xlsx'):
            filename = filename + '.xlsx'
            
        # 如果提供的不是绝对路径，则保存到output_dir目录下
        if not os.path.isabs(filename):
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)
            filename = os.path.join(self.output_dir, filename)
            
        logger.info(f"正在保存数据到: {filename}")
        
        try:
            # 将数据转换为DataFrame
            df = pd.DataFrame(self.house_data)
            
            # 定义列的顺序和中文列名映射
            columns_mapping = {
                'platform': '平台',
                'city': '城市',
                'house_name': '房源名称',
                'price': '价格',
                'address': '地址',
                'house_type': '户型',
                'area': '面积',
                'year': '建筑年份',
                'type': '房源类型',
                'latitude': '纬度',
                'longitude': '经度',
                'detail_url': '详情链接',
                'layout_image': '户型图链接'
            }
            
            # 重新排序和重命名列
            columns = [col for col in columns_mapping.keys() if col in df.columns]
            df = df[columns]
            df = df.rename(columns=columns_mapping)
            
            # 保存为Excel
            df.to_excel(filename, index=False, engine='openpyxl')
            logger.info(f"数据已保存到: {filename}")
            
            return filename
        except Exception as e:
            logger.error(f"保存Excel文件出错: {e}")
            return None
            
    def clear_data(self):
        """清空爬取的数据"""
        self.house_data = []
        logger.info("已清空爬取的数据")

    def handle_verification(self, platform=None, url=None):
        """处理验证码
        
        参数:
            platform: 平台名称
            url: 当前页面URL
        
        返回:
            bool: 是否成功处理验证
        """
        # 如果没有提供URL，使用一个默认值
        if not url:
            url = "https://example.com"  # 使用一个无害的默认URL
            logger.warning("handle_verification被调用但未提供URL")
        
        # 如果启用了自动验证
        if self.auto_verification_handler:
            logger.info(f"使用自动验证处理器处理{platform or '未知平台'}验证")
            try:
                success = self.auto_verification_handler.handle_verification(url, platform)
                if success:
                    logger.info("自动验证成功")
                    return True
                else:
                    logger.warning("自动验证失败")
            except Exception as e:
                logger.error(f"自动验证过程出错: {e}")
        
        # 如果没有自动验证处理器或自动验证失败，提示用户手动验证
        logger.info(f"提示用户手动处理{platform or '未知平台'}验证")
        print(f"\n检测到{platform or '未知平台'}验证页面，URL: {url}")
        print("请在浏览器中手动完成验证后，回到这里按回车键继续...")
        choice = input("如果要跳过此验证并继续下一页/平台，请输入'skip'，否则按回车继续: ")
        
        if choice.lower() == 'skip':
            logger.info("用户选择跳过验证")
            return False
        
        logger.info("用户已完成验证")
        return True 