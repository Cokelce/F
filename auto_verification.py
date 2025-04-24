#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import random
import os
import cv2
import numpy as np
import base64
import re
import json
import logging
from PIL import Image
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("verification.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("verification")

class AutoVerificationHandler:
    """自动处理网站验证码的类"""
    
    def __init__(self, headless=False, debug=True, max_retries=1):
        """初始化自动验证处理器
        
        参数:
            headless: 是否使用无头模式（无浏览器界面）
            debug: 是否启用调试模式
            max_retries: 验证失败后的最大重试次数
        """
        self.debug = debug
        self.cookies = {}
        self.max_retries = max_retries
        
        # 创建验证截图保存目录
        self.debug_dir = 'verification_debug'
        if debug and not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)
        
        # 设置Chrome选项
        self.chrome_options = Options()
        if headless:
            self.chrome_options.add_argument('--headless')
        
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        self.chrome_options.add_argument('--start-maximized')
        
        # 设置更接近真人的用户代理
        self.chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # 初始化WebDriver
        self.driver = None
    
    def start_browser(self):
        """启动浏览器"""
        if self.driver is None:
            try:
                self.driver = webdriver.Chrome(options=self.chrome_options)
                
                # 注入JS来隐藏自动化特征
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                
                # 设置窗口大小
                self.driver.set_window_size(1366, 768)
                
                if self.debug:
                    logger.info("浏览器已启动")
            except Exception as e:
                logger.error(f"启动浏览器失败: {e}")
                raise
    
    def close_browser(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None
                if self.debug:
                    logger.info("浏览器已关闭")
            except Exception as e:
                logger.error(f"关闭浏览器出错: {e}")
    
    def handle_verification(self, url, platform=None):
        """
        处理页面验证
        
        参数:
            url (str): 需要验证的页面URL
            platform (str, optional): 平台名称，如果不提供则从URL推断
        
        返回:
            bool: 验证是否成功
            dict: 验证成功后的cookies
        """
        if platform is None:
            if "anjuke" in url:
                platform = "anjuke"
            elif "58" in url or "5i5j" in url:
                platform = "58"
            elif "ke.com" in url:
                platform = "beike"
            elif "lianjia" in url:
                platform = "lianjia"
            else:
                platform = "general"
            
        logger.info(f"开始处理 {platform} 平台的验证，URL: {url}")
        
        success = False
        retries = 0
        
        while not success and retries < self.max_retries:
            try:
                self.start_browser()
                if not self.driver:
                    logger.error("浏览器启动失败，无法进行自动验证")
                    return False
                
                logger.info(f"访问URL: {url}")
                self.driver.get(url)
                time.sleep(2)  # 等待页面加载
                
                # 根据平台调用不同的处理方法
                if platform == "anjuke":
                    success = self.handle_anjuke_verification()
                elif platform == "58":
                    success = self.handle_58_verification()
                elif platform == "beike":
                    success = self.handle_beike_verification()
                elif platform == "lianjia":
                    success = self.handle_lianjia_verification()
                else:
                    success = self.handle_general_verification()
                
                if success:
                    logger.info(f"{platform}平台验证成功")
                    
                    # 等待一段时间确保cookie被设置
                    time.sleep(5)
                    
                    # 检查验证页面是否已消失
                    current_url = self.driver.current_url
                    page_source = self.driver.page_source
                    
                    # 验证是否完成的关键特征
                    verification_markers = ["验证码", "人机验证", "滑动验证", "拖动滑块", "captcha", "verify"]
                    
                    # 检查当前页面是否仍有验证特征
                    has_verification = False
                    for marker in verification_markers:
                        if marker in page_source:
                            has_verification = True
                            logger.warning(f"页面仍包含验证特征: {marker}")
                            break
                    
                    if has_verification:
                        logger.warning("虽然验证步骤完成，但页面仍有验证特征，可能需要重新尝试")
                        
                        # 对于链家/贝壳，尝试额外的方法
                        if platform in ["lianjia", "beike"] and "验证码" in page_source:
                            logger.info("尝试额外的链家/贝壳验证方法...")
                            
                            # 尝试点击可能的刷新按钮
                            try:
                                refresh_buttons = self.driver.find_elements(By.CSS_SELECTOR, 
                                    "[class*='refresh'],[class*='reload'],[title*='刷新'],[alt*='刷新']")
                                if refresh_buttons:
                                    logger.info("点击刷新按钮")
                                    refresh_buttons[0].click()
                                    time.sleep(2)
                                    
                                # 重新尝试滑块验证
                                sliders = self.driver.find_elements(By.CSS_SELECTOR, 
                                    "[class*='slider'],[class*='slide']")
                                if sliders:
                                    logger.info("找到滑块，尝试再次滑动")
                                    slide_element = sliders[0]
                                    slider_width = slide_element.size['width']
                                    
                                    actions = ActionChains(self.driver)
                                    actions.move_to_element(slide_element)
                                    actions.click_and_hold()
                                    
                                    # 随机滑动
                                    slide_distance = random.randint(int(slider_width * 0.6), int(slider_width * 0.9))
                                    
                                    actions.move_by_offset(slide_distance, random.randint(-5, 5))
                                    actions.release()
                                    actions.perform()
                                    
                                    time.sleep(3)
                                
                                # 再次检查
                                has_verification = False
                                for marker in verification_markers:
                                    if marker in self.driver.page_source:
                                        has_verification = True
                                        break
                                
                                if not has_verification:
                                    logger.info("额外验证方法成功")
                                    success = True
                            except Exception as e:
                                logger.error(f"额外验证方法失败: {e}")
                    
                    # 获取所有cookies
                    cookies = self.get_cookies_dict()
                    logger.info(f"获取到 {len(cookies)} 个cookies")
                    
                    # 如果验证成功，返回true
                    if success:
                        # 额外等待，确保所有cookies都已设置
                        time.sleep(2)
                        return True
                    
                # 如果自动验证失败，提示用户手动验证
                if not success:
                    logger.warning(f"{platform}平台自动验证失败，尝试人工验证")
                    # 提示用户进行人工验证
                    print(f"\n请在打开的浏览器中完成 {platform} 平台的验证")
                    print("完成后请在此处按下回车键继续...")
                    input()
                    
                    # 等待一段时间确保手动验证后的cookie被设置
                    time.sleep(3)
                    
                    # 检查人工验证是否成功
                    cookies = self.get_cookies_dict()
                    logger.info(f"手动验证后获取到的cookies: {len(cookies)}个")
                    return True
            except Exception as e:
                logger.error(f"验证处理过程中出错: {e}")
                retries += 1
                if retries < self.max_retries:
                    logger.info(f"将进行第{retries+1}次重试")
                else:
                    logger.error(f"已达到最大重试次数{self.max_retries}，验证失败")
            finally:
                if not success and retries >= self.max_retries:
                    self.close_browser()
        
        return False

    def try_trigger_verification(self):
        # Implementation of try_trigger_verification method
        pass

    def solve_verification(self):
        # Implementation of solve_verification method
        return False

    def handle_58_verification(self):
        # Implementation of handle_58_verification method
        return False

    def handle_anjuke_verification(self):
        """
        处理安居客网站的验证
        
        返回:
            bool: 验证是否成功
        """
        logger.info("尝试安居客特定验证处理方法")
        
        # 等待页面加载完成
        time.sleep(3)
        
        # 首先尝试点击页面，激活可能的验证控件
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            ActionChains(self.driver).move_to_element(body).click().perform()
            logger.info("已点击页面主体，激活可能的验证控件")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"点击页面主体失败: {e}")
        
        # 查找可能的滑块验证元素
        slider_selectors = [
            ".verify-slider", 
            ".captcha-slider", 
            ".verify-slider-handle", 
            ".nc_scale",
            ".slider",
            "[class*='slider']", 
            "[class*='verify']", 
            "[class*='captcha']"
        ]
        
        for selector in slider_selectors:
            try:
                slider = self.driver.find_element(By.CSS_SELECTOR, selector)
                logger.info(f"找到安居客滑块元素: {selector}")
                
                # 获取滑块的位置和大小
                slider_location = slider.location
                slider_size = slider.size
                
                # 计算滑动距离（通常需要滑到右侧）
                start_x = slider_location['x'] + 5
                start_y = slider_location['y'] + slider_size['height'] // 2
                end_x = start_x + slider_size['width'] * 0.9  # 滑动到大约90%位置
                
                # 创建人性化的滑动动作（缓慢且有停顿）
                actions = ActionChains(self.driver)
                actions.move_to_element(slider).click_and_hold()
                actions.pause(0.2)
                
                # 模拟人工滑动，不是匀速的
                steps = random.randint(5, 8)
                for i in range(steps):
                    # 非线性移动，先慢后快再慢
                    move_ratio = 1 - (1 - i / steps) ** 2  # 加速曲线
                    current_x = start_x + (end_x - start_x) * move_ratio
                    actions.move_by_offset(xoffset=(current_x - start_x), yoffset=0)
                    actions.pause(random.uniform(0.05, 0.1))  # 随机暂停
                
                # 最后松开鼠标
                actions.release()
                actions.perform()
                
                logger.info("已执行安居客滑块验证操作")
                time.sleep(2)  # 等待验证结果
                
                # 检查验证后的页面是否仍包含验证元素
                if not self._is_still_verification_page():
                    logger.info("安居客验证成功")
                    return True
                
                # 如果验证还存在，可能需要再次尝试
                logger.warning("第一次滑块验证未成功，尝试再次验证")
                self._try_simple_slider_verification()
                
                # 再次检查验证结果
                if not self._is_still_verification_page():
                    logger.info("安居客第二次验证成功")
                    return True
                
            except Exception as e:
                logger.warning(f"处理安居客滑块验证失败: {e}")
        
        # 尝试其他可能的验证方式
        return self.solve_verification()
    
    def _is_still_verification_page(self):
        """检查当前页面是否仍然是验证页面
        
        返回:
            bool: 如果页面仍然需要验证，返回True；否则返回False
        """
        try:
            page_source = self.driver.page_source
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # 验证页面的常见特征
            verification_indicators = [
                "验证码", "人机验证", "安全验证", "滑动验证", "拖动滑块", 
                "CAPTCHA", "verify", "verification", "security check",
                "点击进行验证", "拼图", "请完成验证", "完成安全验证",
                "slide to verify", "拖动滑块完成拼图", "智能检测"
            ]
            
            # HTML元素特征
            element_indicators = [
                'id="captcha"', 'class="captcha"', 'id="verify"', 'class="verify"',
                'nc_scale', 'nc-lang-cnt', 'class="slider"', 'id="slider"',
                'class="verification"', 'id="verification"', 'class="validate"',
                'geetest', '.captcha-verify', '.CAPTCHA', '#captcha-verify-image', 
                '.captcha-wrapper', '.gt_slider', '.yidun_slider', '.shumei_captcha'
            ]
            
            # 检查文本特征
            for indicator in verification_indicators:
                if indicator in page_source or indicator in page_text:
                    logger.debug(f"检测到验证特征: {indicator}")
                    return True
            
            # 检查HTML元素特征
            for indicator in element_indicators:
                if indicator in page_source:
                    logger.debug(f"检测到验证元素: {indicator}")
                    return True
            
            # 检查验证相关的DOM元素是否存在
            verification_selectors = [
                ".captcha_verify", ".verify-slider", "[class*='captcha']", 
                "[class*='verify']", "img[src*='captcha']", "img[src*='verify']",
                ".CAPTCHA", ".nc_scale", ".gt_slider_knob", ".yidun_slider"
            ]
            
            for selector in verification_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements and elements[0].is_displayed():
                    logger.debug(f"找到可见的验证元素: {selector}")
                    return True
            
            # 检查当前URL是否包含验证相关关键词
            current_url = self.driver.current_url
            url_indicators = ["verify", "captcha", "security-check", "validate"]
            for indicator in url_indicators:
                if indicator in current_url:
                    logger.debug(f"URL包含验证关键词: {indicator}")
                    return True
            
            # 检查内容长度，如果内容过短可能是验证页面
            if len(page_source) < 3000:
                # 验证页面通常内容较短，但同时应检查是否包含验证相关内容
                short_content_verification = ["验证", "captcha", "verify", "security"]
                for term in short_content_verification:
                    if term in page_source:
                        logger.debug(f"页面内容短且包含验证关键词: {term}")
                        return True
            
            logger.debug("页面不再需要验证")
            return False
        except Exception as e:
            logger.error(f"检查验证页面时出错: {e}")
            # 出错时保守地认为仍需验证
            return True
    
    def _try_simple_slider_verification(self):
        """尝试简单的滑块验证方式"""
        try:
            # 尝试查找页面上任何可能的滑块元素
            sliders = self.driver.find_elements(By.CSS_SELECTOR, 
                "[class*='slider'],[class*='verify'],[class*='captcha'],div[role='slider']")
            
            if not sliders:
                return False
                
            slider = sliders[0]
            # 获取滑块大小和滑动区域大小
            slider_rect = slider.rect
            # 假设滑动区域是滑块父元素的宽度
            parent = slider.find_element(By.XPATH, "..")
            track_width = parent.rect['width']
            
            # 执行简单的滑动动作
            actions = ActionChains(self.driver)
            actions.click_and_hold(slider)
            actions.pause(0.2)
            
            # 简单的三段式滑动
            moves = [
                (track_width * 0.6, 0.1),  # 快速滑动到60%
                (track_width * 0.3, 0.15),  # 慢速滑动到90%
                (track_width * 0.1, 0.05)   # 很慢滑动到100%
            ]
            
            current_x = 0
            for move_x, pause in moves:
                actions.move_by_offset(move_x, 0)
                current_x += move_x
                actions.pause(pause)
            
            actions.release()
            actions.perform()
            
            time.sleep(2)  # 等待验证结果
            return True
            
        except Exception as e:
            logger.error(f"执行简单滑块验证失败: {e}")
            return False

    def handle_beike_verification(self):
        """
        处理贝壳找房网站的验证
        
        返回:
            bool: 验证是否成功
        """
        logger.info("尝试贝壳找房特定验证处理方法")
        
        # 检查是否需要验证
        verification_type = self._identify_verification_type()
        if not verification_type:
            logger.info("贝壳找房页面无需验证或验证类型未识别")
            return True
            
        logger.info(f"贝壳找房识别到验证类型: {verification_type}")
        
        # 贝壳找房特别处理逻辑
        # 例如针对特定的滑块验证或图片选择验证
        
        # 尝试解决验证
        return self.solve_verification(verification_type)

    def handle_general_verification(self):
        """
        处理通用平台的验证
        
        返回:
            bool: 验证是否成功
        """
        logger.info("尝试通用验证处理方法")
        
        # 检查是否需要验证
        verification_type = self._identify_verification_type()
        if not verification_type:
            logger.info("当前页面无需验证或验证类型未识别")
            return True
            
        logger.info(f"识别到验证类型: {verification_type}")
        
        # 尝试解决验证
        return self.solve_verification(verification_type)

    def handle_lianjia_verification(self):
        """
        处理链家网站的验证
        
        返回:
            bool: 验证是否成功
        """
        logger.info("尝试处理链家验证...")
        try:
            # 等待验证元素出现
            time.sleep(3)
            
            # 保存验证前的页面截图用于调试
            if self.debug:
                self.driver.save_screenshot(os.path.join(self.debug_dir, "lianjia_verification_before.png"))
            
            # 识别并处理滑块验证
            slider_selectors = [
                ".captcha_verify_slide", ".verifyslider", ".verify-slider", 
                ".nc_scale", ".geetest_slider_button", ".gt_slider_knob",
                "[class*='slider']", "[class*='captcha']", "[class*='verify']", 
                "input[type='range']", ".nc-lang-cnt"
            ]
            
            # 第一次尝试：寻找滑块
            verification_handled = False
            for selector in slider_selectors:
                try:
                    slider_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if slider_elements:
                        slider = slider_elements[0]
                        logger.info(f"找到链家滑块元素: {selector}")
                        
                        # 获取滑块宽度，计算滑动距离
                        slider_width = slider.size['width']
                        container_element = None
                        
                        # 尝试找到滑动容器
                        container_selectors = [
                            ".captcha_verify_container", ".verify-slider-track", 
                            ".nc-lang-cnt", ".slider-track", ".geetest_slider_track"
                        ]
                        
                        for container_selector in container_selectors:
                            container_elements = self.driver.find_elements(By.CSS_SELECTOR, container_selector)
                            if container_elements:
                                container_element = container_elements[0]
                                break
                        
                        # 如果找到容器，使用容器宽度，否则估计
                        if container_element:
                            container_width = container_element.size['width']
                            slide_distance = int(container_width * 0.8)  # 滑动容器宽度的80%
                        else:
                            # 根据滑块估计滑动距离
                            slide_distance = int(slider_width * 4)  # 估计值
                        
                        # 创建动作链
                        actions = ActionChains(self.driver)
                        actions.move_to_element(slider)
                        actions.click_and_hold()
                        
                        # 使用更自然的滑动轨迹
                        # 分三段执行：快速 -> 减速 -> 微调
                        current_offset = 0
                        
                        # 第一段：快速滑动到60%
                        fast_distance = int(slide_distance * 0.6)
                        actions.move_by_offset(fast_distance, random.randint(-3, 3))
                        current_offset += fast_distance
                        actions.pause(0.1)
                        
                        # 第二段：减速滑动到90%
                        medium_distance = int(slide_distance * 0.3)
                        steps = 3
                        for i in range(steps):
                            move = medium_distance // steps
                            actions.move_by_offset(move, random.randint(-2, 2))
                            actions.pause(0.05)
                        current_offset += medium_distance
                        
                        # 第三段：微调到终点
                        remaining = slide_distance - current_offset
                        actions.move_by_offset(remaining, random.randint(-1, 1))
                        actions.pause(0.1)
                        
                        # 释放滑块
                        actions.release()
                        actions.perform()
                        
                        logger.info(f"执行链家滑块验证，滑动距离: {slide_distance}px")
                        time.sleep(3)  # 等待验证结果
                        
                        # 检查验证是否成功
                        if not self._is_still_verification_page():
                            logger.info("链家滑块验证成功!")
                            return True
                        else:
                            logger.warning("第一次滑块验证未成功，尝试其他策略")
                            
                        verification_handled = True
                        break
                except Exception as e:
                    logger.warning(f"处理链家滑块{selector}失败: {e}")
            
            # 第二次尝试：如果滑块验证未成功，尝试其他滑动距离
            if verification_handled and self._is_still_verification_page():
                logger.info("尝试第二种滑动策略...")
                
                # 再次查找滑块
                for selector in slider_selectors:
                    try:
                        slider_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if slider_elements:
                            slider = slider_elements[0]
                            
                            # 使用不同的滑动距离，这次尝试完全滑动
                            slide_distance = 280  # 尝试一个固定的距离
                            
                            actions = ActionChains(self.driver)
                            actions.move_to_element(slider)
                            actions.click_and_hold()
                            
                            # 缓慢均匀滑动
                            steps = 8
                            for i in range(steps):
                                actions.move_by_offset(slide_distance/steps, 0)
                                actions.pause(0.05)
                            
                            actions.release()
                            actions.perform()
                            
                            logger.info("执行第二次链家滑块验证")
                            time.sleep(3)
                            
                            # 检查验证是否成功
                            if not self._is_still_verification_page():
                                logger.info("第二次链家滑块验证成功!")
                                return True
                            break
                    except Exception as e:
                        logger.warning(f"第二次处理链家滑块{selector}失败: {e}")
            
            # 第三次尝试：查找并处理可能的刷新按钮，然后再次尝试
            if self._is_still_verification_page():
                logger.info("尝试第三种策略：刷新验证码后再滑动...")
                
                # 查找刷新按钮
                refresh_selectors = [
                    ".reload-btn", ".refresh", ".captcha-refresh", 
                    "a[title*='刷新']", "a[title*='换一张']",
                    "[class*='refresh']", "[class*='reload']"
                ]
                
                for selector in refresh_selectors:
                    try:
                        refresh_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if refresh_elements:
                            refresh_button = refresh_elements[0]
                            refresh_button.click()
                            logger.info(f"点击刷新按钮: {selector}")
                            time.sleep(2)
                            break
                    except Exception as e:
                        logger.warning(f"点击刷新按钮{selector}失败: {e}")
                
                # 再次尝试滑块
                for selector in slider_selectors:
                    try:
                        slider_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if slider_elements:
                            slider = slider_elements[0]
                            
                            # 尝试随机距离
                            slide_distance = random.randint(200, 320)
                            
                            actions = ActionChains(self.driver)
                            actions.move_to_element(slider)
                            actions.click_and_hold()
                            
                            # 模拟人类滑动：先快后慢
                            fast_part = int(slide_distance * 0.7)
                            slow_part = slide_distance - fast_part
                            
                            # 快速滑动
                            actions.move_by_offset(fast_part, random.randint(-2, 2))
                            actions.pause(0.1)
                            
                            # 慢速完成
                            small_steps = 5
                            for i in range(small_steps):
                                actions.move_by_offset(slow_part/small_steps, random.randint(-1, 1))
                                actions.pause(0.08)
                            
                            actions.release()
                            actions.perform()
                            
                            logger.info("执行第三次链家滑块验证")
                            time.sleep(3)
                            
                            # 最终检查
                            if not self._is_still_verification_page():
                                logger.info("第三次链家滑块验证成功!")
                                return True
                            else:
                                logger.warning("所有滑块验证策略均未成功")
                                
                            break
                    except Exception as e:
                        logger.warning(f"第三次处理链家滑块{selector}失败: {e}")
            
            # 如果所有滑块策略都失败，尝试点击验证
            if self._is_still_verification_page():
                logger.info("尝试点击验证...")
                
                # 查找可能的点击验证元素
                click_selectors = [
                    ".captcha_verify_img", ".verify-img", "img[src*='captcha']",
                    "img[src*='verify']", "[class*='captcha'] img"
                ]
                
                for selector in click_selectors:
                    try:
                        click_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if click_elements:
                            logger.info(f"找到点击验证元素: {selector}")
                            
                            # 点击验证图片的随机位置
                            click_elem = click_elements[0]
                            img_width = click_elem.size['width']
                            img_height = click_elem.size['height']
                            
                            # 随机点击位置
                            x_offset = random.randint(int(img_width * 0.3), int(img_width * 0.7))
                            y_offset = random.randint(int(img_height * 0.3), int(img_height * 0.7))
                            
                            actions = ActionChains(self.driver)
                            actions.move_to_element_with_offset(click_elem, x_offset, y_offset)
                            actions.click()
                            actions.perform()
                            
                            logger.info(f"点击验证图片坐标: ({x_offset}, {y_offset})")
                            time.sleep(3)
                            
                            # 检查验证是否成功
                            if not self._is_still_verification_page():
                                logger.info("点击验证成功!")
                                return True
                            else:
                                logger.warning("点击验证未成功")
                            break
                    except Exception as e:
                        logger.warning(f"执行点击验证{selector}失败: {e}")
            
            # 保存验证后的页面截图用于调试
            if self.debug:
                self.driver.save_screenshot(os.path.join(self.debug_dir, "lianjia_verification_after.png"))
            
            # 最后检查
            if not self._is_still_verification_page():
                logger.info("链家验证已完成")
                return True
            else:
                logger.warning("所有自动验证方法均未成功，需要手动验证")
                return False
                
        except Exception as e:
            logger.error(f"链家验证处理过程中出错: {e}")
            return False
        
    def get_cookies_dict(self):
        """获取当前浏览器的cookies字典
        
        返回:
            dict: cookies字典
        """
        if self.driver is None:
            return {}
            
        try:
            cookies = self.driver.get_cookies()
            return {cookie['name']: cookie['value'] for cookie in cookies}
        except Exception as e:
            logger.error(f"获取cookies失败: {e}")
            return {} 