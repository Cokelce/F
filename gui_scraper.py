#!/usr/bin/env python
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import traceback
from datetime import datetime
from multi_platform_housing_scraper import MultiPlatformHousingScraper, CITY_CODES, set_debug_level
import time
import random

class HousingScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("房源数据爬取工具")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        self.scraper = MultiPlatformHousingScraper()
        self.setup_ui()
        
    def setup_ui(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题
        title_label = ttk.Label(main_frame, text="多平台房源数据爬取工具", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # 创建设置框架
        settings_frame = ttk.LabelFrame(main_frame, text="爬取设置", padding="10")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行: 平台选择和城市
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=5)
        
        # 平台选择（支持多选）
        ttk.Label(row1, text="平台:").pack(side=tk.LEFT, padx=5)
        platform_frame = ttk.Frame(row1)
        platform_frame.pack(side=tk.LEFT, padx=5)
        
        self.platform_vars = {}
        platforms = ["58同城", "安居客", "贝壳找房", "链家"]
        for platform in platforms:
            var = tk.BooleanVar(value=platform == "安居客")
            cb = ttk.Checkbutton(platform_frame, text=platform, variable=var)
            cb.pack(side=tk.LEFT, padx=5)
            self.platform_vars[platform] = var
        
        ttk.Label(row1, text="城市:").pack(side=tk.LEFT, padx=10)
        self.city_var = tk.StringVar(value="北京")
        
        # 获取城市列表
        cities = sorted(list(CITY_CODES.keys()))
        city_combo = ttk.Combobox(row1, textvariable=self.city_var, width=10)
        city_combo['values'] = cities
        city_combo.pack(side=tk.LEFT, padx=5)
        
        # 第二行: 房源类型和筛选条件
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=5)
        
        ttk.Label(row2, text="房源类型:").pack(side=tk.LEFT, padx=5)
        self.house_type_var = tk.StringVar(value="二手房")
        house_type_combo = ttk.Combobox(row2, textvariable=self.house_type_var, width=10)
        house_type_combo['values'] = ["新房", "二手房", "租房"]
        house_type_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="卧室数:").pack(side=tk.LEFT, padx=5)
        self.bedroom_var = tk.StringVar()
        bedroom_combo = ttk.Combobox(row2, textvariable=self.bedroom_var, width=5)
        bedroom_combo['values'] = ["", "1", "2", "3", "4", "5"]
        bedroom_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="客厅数:").pack(side=tk.LEFT, padx=5)
        self.livingroom_var = tk.StringVar()
        livingroom_combo = ttk.Combobox(row2, textvariable=self.livingroom_var, width=5)
        livingroom_combo['values'] = ["", "1", "2", "3"]
        livingroom_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row2, text="建筑年份:").pack(side=tk.LEFT, padx=5)
        self.year_var = tk.StringVar()
        year_entry = ttk.Entry(row2, textvariable=self.year_var, width=6)
        year_entry.pack(side=tk.LEFT, padx=5)
        
        # 第三行: 页数和高级选项
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill=tk.X, pady=5)
        
        ttk.Label(row3, text="爬取页数:").pack(side=tk.LEFT, padx=5)
        self.pages_var = tk.StringVar(value="3")
        pages_entry = ttk.Entry(row3, textvariable=self.pages_var, width=5)
        pages_entry.pack(side=tk.LEFT, padx=5)
        
        # 调试模式开关
        self.debug_var = tk.BooleanVar(value=False)
        debug_check = ttk.Checkbutton(row3, text="调试模式", variable=self.debug_var)
        debug_check.pack(side=tk.LEFT, padx=20)
        
        # 批量模式
        self.batch_var = tk.BooleanVar(value=False)
        batch_check = ttk.Checkbutton(row3, text="批量爬取", variable=self.batch_var, 
                                      command=self.toggle_batch_mode)
        batch_check.pack(side=tk.LEFT, padx=20)
        
        # 跳过验证选项
        self.skip_verification_var = tk.BooleanVar(value=True)
        skip_verification_check = ttk.Checkbutton(row3, text="跳过验证", variable=self.skip_verification_var)
        skip_verification_check.pack(side=tk.LEFT, padx=20)
        
        # 高级选项
        advanced_button = ttk.Button(row3, text="高级选项", command=self.show_advanced_options)
        advanced_button.pack(side=tk.RIGHT, padx=10)
        
        # 批量城市选择（初始隐藏）
        self.batch_frame = ttk.LabelFrame(settings_frame, text="批量城市选择", padding="10")
        
        # 创建城市选择列表框和滚动条
        batch_cities_frame = ttk.Frame(self.batch_frame)
        batch_cities_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.cities_listbox = tk.Listbox(batch_cities_frame, selectmode=tk.MULTIPLE, height=6)
        self.cities_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        for city in cities:
            self.cities_listbox.insert(tk.END, city)
        
        cities_scrollbar = ttk.Scrollbar(batch_cities_frame, command=self.cities_listbox.yview)
        cities_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.cities_listbox.config(yscrollcommand=cities_scrollbar.set)
        
        # 批量城市选择按钮
        batch_buttons_frame = ttk.Frame(self.batch_frame)
        batch_buttons_frame.pack(fill=tk.X, pady=5)
        
        select_all_button = ttk.Button(batch_buttons_frame, text="全选", 
                                      command=lambda: self.cities_listbox.selection_set(0, tk.END))
        select_all_button.pack(side=tk.LEFT, padx=5)
        
        clear_all_button = ttk.Button(batch_buttons_frame, text="清除", 
                                     command=lambda: self.cities_listbox.selection_clear(0, tk.END))
        clear_all_button.pack(side=tk.LEFT, padx=5)
        
        # 按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="开始爬取", command=self.start_scraping)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止爬取", command=self.stop_scraping, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.export_button = ttk.Button(button_frame, text="导出数据", command=self.export_data)
        self.export_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(button_frame, text="清除数据", command=self.clear_data)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="爬取日志", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, width=80, height=15)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 初始化变量
        self.scraping_thread = None
        self.stop_event = threading.Event()
        
    def show_advanced_options(self):
        """显示高级选项窗口"""
        advanced_window = tk.Toplevel(self.root)
        advanced_window.title("高级选项")
        advanced_window.geometry("400x300")
        advanced_window.transient(self.root)  # 设置为主窗口的子窗口
        
        frame = ttk.Frame(advanced_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 用户代理设置
        ttk.Label(frame, text="自定义用户代理:").pack(anchor=tk.W, pady=5)
        user_agent_var = tk.StringVar(value=self.scraper.headers.get('User-Agent', ''))
        user_agent_entry = ttk.Entry(frame, textvariable=user_agent_var, width=50)
        user_agent_entry.pack(fill=tk.X, pady=5)
        
        # 清理选项
        ttk.Label(frame, text="清理选项:").pack(anchor=tk.W, pady=5)
        cleanup_frame = ttk.Frame(frame)
        cleanup_frame.pack(fill=tk.X, pady=5)
        
        cleanup_var = tk.BooleanVar(value=True)
        cleanup_check = ttk.Checkbutton(cleanup_frame, text="自动清理超过以下天数的临时文件:", variable=cleanup_var)
        cleanup_check.pack(side=tk.LEFT)
        
        days_var = tk.StringVar(value="7")
        days_entry = ttk.Entry(cleanup_frame, textvariable=days_var, width=5)
        days_entry.pack(side=tk.LEFT, padx=5)
        
        # 保存按钮
        def save_settings():
            if user_agent_var.get():
                self.scraper.headers['User-Agent'] = user_agent_var.get()
                self.scraper.update_headers()
            
            if cleanup_var.get():
                try:
                    days = int(days_var.get())
                    self.scraper.cleanup_old_files(max_age_days=days)
                    self.log("已清理超过 {} 天的临时文件".format(days))
                except ValueError:
                    messagebox.showerror("错误", "请输入有效的天数")
            
            advanced_window.destroy()
        
        save_button = ttk.Button(frame, text="保存设置", command=save_settings)
        save_button.pack(pady=10)
    
    def log(self, message):
        """添加日志消息到日志窗口"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)  # 滚动到最后
        self.root.update_idletasks()  # 确保UI更新
    
    def toggle_batch_mode(self):
        """切换批量模式"""
        if self.batch_var.get():
            # 简单直接地将批量城市选择框添加到设置框架
            settings_frame = None
            # 遍历查找设置框架
            for child in self.root.winfo_children():
                if isinstance(child, ttk.Frame):
                    for subchild in child.winfo_children():
                        if isinstance(subchild, ttk.LabelFrame) and hasattr(subchild, 'cget') and subchild.cget('text') == "爬取设置":
                            settings_frame = subchild
                            break
                    if settings_frame:
                        break
                        
            if settings_frame:
                # 添加到设置框架
                self.batch_frame.pack(fill=tk.X, pady=5, padx=10)
                self.log("已开启批量爬取模式，您可以在下方选择多个城市")
            else:
                self.log("错误: 无法找到设置框架，无法显示批量城市选择")
        else:
            self.batch_frame.pack_forget()
            self.log("已关闭批量爬取模式")
            
    def get_selected_cities(self):
        """获取选中的城市列表"""
        if not self.batch_var.get():
            return [self.city_var.get()]
        
        # 批量模式下，获取多个选中的城市
        selected_indices = self.cities_listbox.curselection()
        if not selected_indices:
            return [self.city_var.get()]  # 如果没选择，用下拉框选中的城市
        return [self.cities_listbox.get(i) for i in selected_indices]
    
    def start_scraping(self):
        """开始爬取数据"""
        try:
            # 获取基本参数
            platforms = self.get_selected_platforms()
            cities = self.get_selected_cities()
            house_type = self.house_type_var.get()
            
            if not platforms:
                messagebox.showinfo("提示", "请至少选择一个平台")
                return
            
            if not cities:
                messagebox.showinfo("提示", "请至少选择一个城市")
                return
            
            bedroom_num = None
            if self.bedroom_var.get():
                bedroom_num = int(self.bedroom_var.get())
                
            livingroom_num = None
            if self.livingroom_var.get():
                livingroom_num = int(self.livingroom_var.get())
                
            building_year = None
            if self.year_var.get():
                building_year = int(self.year_var.get())
                
            pages = 3
            if self.pages_var.get():
                pages = int(self.pages_var.get())
            
            # 设置调试模式
            debug = self.debug_var.get()
            set_debug_level(debug)
            
            # 禁用开始按钮，启用停止按钮
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_var.set("正在爬取数据...")
            
            # 重置停止事件
            self.stop_event = threading.Event()
            
            # 创建并启动爬取线程
            if self.batch_var.get() and (len(platforms) > 1 or len(cities) > 1):
                # 批量爬取
                self.log(f"开始批量爬取 - 平台: {platforms}, 城市: {cities}")
                self.scraping_thread = threading.Thread(
                    target=self.run_batch_scraping,
                    args=(platforms, cities, house_type, bedroom_num, livingroom_num, building_year, pages)
                )
            else:
                # 单城市多平台爬取
                city = cities[0]
                self.log(f"开始多平台连续爬取 - 平台: {platforms}, 城市: {city}")
                self.scraping_thread = threading.Thread(
                    target=self.run_multi_platform_scraping,
                    args=(platforms, city, house_type, bedroom_num, livingroom_num, building_year, pages)
                )
                
            self.scraping_thread.daemon = True  # 设置为守护线程
            self.scraping_thread.start()
            
            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self.monitor_scraping)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            
        except Exception as e:
            error_msg = f"启动爬取失败: {str(e)}"
            messagebox.showerror("错误", error_msg)
            self.log(f"错误: {error_msg}")
            self.log(f"详细信息: {traceback.format_exc()}")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("就绪")
    
    def get_selected_platforms(self):
        """获取选中的平台列表"""
        return [platform for platform, var in self.platform_vars.items() if var.get()]
    
    def run_batch_scraping(self, platforms, cities, house_type, bedroom_num, livingroom_num, building_year, pages):
        """执行批量爬取操作"""
        count = 0
        total_cities = len(cities)
        total_platforms = len(platforms)
        
        self.log(f"开始批量爬取 - {total_platforms}个平台 x {total_cities}个城市")
        self.log(f"选择的平台: {', '.join(platforms)}")  # 添加明确的平台列表日志
        self.log(f"筛选条件 - 卧室: {bedroom_num or '不限'}, 客厅: {livingroom_num or '不限'}, 建筑年份: {building_year or '不限'}")
        self.log(f"页数: {pages}")
        
        # 清空现有数据，为批量爬取做准备
        self.scraper.house_data = []
        
        # 检查是否启用跳过验证
        original_handle_verification = None
        if self.skip_verification_var.get():
            self.log("已启用跳过验证功能")
            # 临时保存原始的验证处理方法
            original_handle_verification = self.scraper.handle_verification
            
            # 修改验证处理方法为自动跳过
            def skip_verification_handler(platform=None, url=None):
                self.log(f"检测到{platform or '未知平台'}验证页面，已启用跳过验证，继续爬取下一页/平台")
                # 保存一下验证页面以便日后分析
                if url and platform == "58":
                    try:
                        import requests
                        import os
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'}
                        response = requests.get(url, headers=headers)
                        os.makedirs('debug_pages', exist_ok=True)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        with open(f'debug_pages/58_verification_{timestamp}.html', 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        self.log(f"已保存验证页面至debug_pages/58_verification_{timestamp}.html")
                    except:
                        pass
                return False
            
            # 替换验证处理方法
            self.scraper.handle_verification = skip_verification_handler
        
        try:
            # 记录爬取开始前的数据量
            initial_data_count = len(self.scraper.house_data)
            
            # 遍历每个城市
            for i, city in enumerate(cities):
                if self.stop_event.is_set():
                    self.log("批量爬取已手动停止")
                    break
                
                self.status_var.set(f"爬取中 - 城市 {i+1}/{total_cities}")
                self.log(f"开始爬取城市: {city} ({i+1}/{total_cities})")
                city_data_before = len(self.scraper.house_data)
                
                # 遍历每个平台 - 关键修改部分
                for j, platform in enumerate(platforms):
                    if self.stop_event.is_set():
                        break
                    
                    self.log(f"准备爬取平台: {platform} ({j+1}/{total_platforms})")
                    initial_platform_count = len(self.scraper.house_data)
                    
                    # 分别处理每个平台
                    if platform == "58同城":
                        # 58同城处理逻辑
                        city_abbr = CITY_CODES.get(city)
                        if not city_abbr:
                            self.log(f"错误: 未找到城市'{city}'的代码")
                            continue  # 继续下一个平台
                        
                        # 房源类型映射
                        house_type_map = {"新房": "new", "二手房": "second", "租房": "rent"}
                        scrape_type = house_type_map.get(house_type, "second")
                        
                        # 58同城爬取
                        self.log(f"开始爬取58同城 - 城市代码: {city_abbr}, 类型: {scrape_type}")
                        
                        # 尝试爬取
                        max_retries = 2
                        for retry in range(max_retries):
                            self.log(f"58同城爬取尝试 {retry+1}/{max_retries}")
                            if retry > 0:
                                delay = random.uniform(5, 10)
                                self.log(f"重试前延迟 {delay:.1f} 秒")
                                time.sleep(delay)
                            
                            try:
                                result = self.scraper.scrape_58(city_abbr, scrape_type, bedroom_num, livingroom_num, building_year, pages)
                                if result:
                                    break
                            except Exception as e:
                                self.log(f"58同城爬取出错: {str(e)}")
                                if retry == max_retries - 1:
                                    self.log("58同城爬取失败，继续下一平台")
                    
                    elif platform == "安居客":
                        # 安居客处理逻辑
                        self.log(f"开始爬取安居客 - 城市: {city}, 类型: {house_type}")
                        try:
                            result = self.scraper.scrape_anjuke(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            self.log(f"安居客爬取{'成功' if result else '失败'}")
                        except Exception as e:
                            self.log(f"安居客爬取出错: {str(e)}")
                    
                    elif platform == "贝壳找房":
                        # 贝壳找房处理逻辑
                        self.log(f"开始爬取贝壳找房 - 城市: {city}, 类型: {house_type}")
                        try:
                            result = self.scraper.scrape_beike(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            self.log(f"贝壳找房爬取{'成功' if result else '失败'}")
                        except Exception as e:
                            self.log(f"贝壳找房爬取出错: {str(e)}")
                    
                    elif platform == "链家":
                        # 链家处理逻辑
                        self.log(f"开始爬取链家 - 城市: {city}, 类型: {house_type}")
                        try:
                            result = self.scraper.scrape_lianjia(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            self.log(f"链家爬取{'成功' if result else '失败'}")
                        except Exception as e:
                            self.log(f"链家爬取出错: {str(e)}")
                    
                    # 计算每个平台的爬取结果
                    platform_items = len(self.scraper.house_data) - initial_platform_count
                    self.log(f"{platform}爬取完成，获取{platform_items}条数据")
                
                # 计算每个城市的爬取结果
                city_items = len(self.scraper.house_data) - city_data_before
                self.log(f"城市 {city} 爬取完成，共获取 {city_items} 条数据")
            
            # 计算总爬取结果
            total_items = len(self.scraper.house_data) - initial_data_count
            self.log(f"批量爬取完成，共获取 {total_items} 条房源数据")
            
            # 一次性保存所有数据
            if self.scraper.house_data:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = self.scraper.save_to_excel(f"house_data_{timestamp}.xlsx")
                self.log(f"数据已保存到 {filename}")
        
        finally:
            # 恢复原始验证处理方法
            if original_handle_verification:
                self.scraper.handle_verification = original_handle_verification
    
    def run_multi_platform_scraping(self, platforms, city, house_type, bedroom_num, livingroom_num, building_year, pages):
        """执行多平台连续爬取操作（单城市多平台）"""
        try:
            self.log(f"开始多平台连续爬取 - 平台: {platforms}, 城市: {city}")
            self.log(f"筛选条件 - 卧室: {bedroom_num or '不限'}, 客厅: {livingroom_num or '不限'}, 建筑年份: {building_year or '不限'}")
            self.log(f"页数: {pages}")
            
            # 记录爬取开始前的数据量
            initial_data_count = len(self.scraper.house_data)
            
            # 检查是否启用跳过验证
            original_handle_verification = None
            if self.skip_verification_var.get():
                self.log("已启用跳过验证功能")
                # 临时保存原始的验证处理方法
                original_handle_verification = self.scraper.handle_verification
                
                # 修改验证处理方法为自动跳过
                def skip_verification_handler(platform=None, url=None):
                    self.log(f"检测到{platform or '未知平台'}验证页面，已启用跳过验证，继续爬取下一页/平台")
                    # 保存一下验证页面以便日后分析
                    if url and platform == "58":
                        try:
                            import requests
                            import os
                            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'}
                            response = requests.get(url, headers=headers)
                            os.makedirs('debug_pages', exist_ok=True)
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            with open(f'debug_pages/58_verification_{timestamp}.html', 'w', encoding='utf-8') as f:
                                f.write(response.text)
                            self.log(f"已保存验证页面至debug_pages/58_verification_{timestamp}.html")
                        except:
                            pass
                    return False
                
                # 替换验证处理方法
                self.scraper.handle_verification = skip_verification_handler
            
            try:
                # 连续爬取每个平台
                for i, platform in enumerate(platforms):
                    if self.stop_event.is_set():
                        self.log("爬取已手动停止")
                        break
                        
                    self.status_var.set(f"爬取中 - 平台 {i+1}/{len(platforms)}")
                    self.log(f"开始爬取平台: {platform} ({i+1}/{len(platforms)})")
                    platform_data_before = len(self.scraper.house_data)
                    
                    # 处理不同的爬取平台
                    if platform == "58同城":
                        city_abbr = CITY_CODES.get(city)
                        if not city_abbr:
                            self.log(f"错误: 未找到城市'{city}'的代码")
                            continue
                        self.log(f"58同城城市代码: {city_abbr}")
                        
                        # 根据房源类型映射
                        house_type_map = {"新房": "new", "二手房": "second", "租房": "rent"}
                        scrape_type = house_type_map.get(house_type, "second")
                        self.log(f"58同城爬取类型: {scrape_type}")
                        
                        # 58同城特别容易需要验证，尝试有限次重试
                        max_retries = 2  # 降低最大重试次数
                        initial_platform_count = len(self.scraper.house_data)
                        for retry in range(max_retries):
                            self.log(f"58同城爬取尝试 {retry+1}/{max_retries}...")
                            
                            # 随机延迟降低被检测概率
                            if retry > 0:
                                delay = random.uniform(5, 10)
                                self.log(f"重试前随机延迟 {delay:.1f} 秒...")
                                time.sleep(delay)
                            
                            try:
                                result = self.scraper.scrape_58(city_abbr, scrape_type, bedroom_num, livingroom_num, building_year, pages)
                                
                                # 只要爬取过程正常完成，无论是否获取到数据，都视为成功
                                if result:
                                    new_data_count = len(self.scraper.house_data) - initial_platform_count
                                    if new_data_count > 0:
                                        self.log(f"{platform}爬取成功，获取{new_data_count}条数据")
                                    else:
                                        self.log(f"{platform}爬取过程完成，但未获取到任何数据，可能是没有符合条件的房源或被反爬机制拦截")
                                    break
                                
                                # 爬取失败且未到最大重试次数
                                if retry < max_retries - 1:
                                    self.log(f"{platform}爬取未成功，将进行重试...")
                                else:
                                    self.log(f"{platform}多次爬取未成功，跳过此平台")
                            except Exception as e:
                                self.log(f"{platform}爬取出错: {str(e)}")
                                if retry == max_retries - 1:
                                    self.log(f"{platform}爬取失败，继续下一平台")
                        
                        platform_items = len(self.scraper.house_data) - initial_platform_count
                        self.log(f"{platform}爬取结束，获取{platform_items}条数据")
                        
                    elif platform == "安居客":
                        self.log(f"开始爬取安居客 - 城市: {city}, 类型: {house_type}")
                        try:
                            initial_platform_count = len(self.scraper.house_data)
                            result = self.scraper.scrape_anjuke(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            platform_items = len(self.scraper.house_data) - initial_platform_count
                            self.log(f"{platform}爬取{'成功' if result else '失败'}，获取{platform_items}条数据")
                        except Exception as e:
                            self.log(f"{platform}爬取出错: {str(e)}")
                        
                    elif platform == "贝壳找房":
                        self.log(f"开始爬取贝壳找房 - 城市: {city}, 类型: {house_type}")
                        try:
                            initial_platform_count = len(self.scraper.house_data)
                            result = self.scraper.scrape_beike(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            platform_items = len(self.scraper.house_data) - initial_platform_count
                            self.log(f"{platform}爬取{'成功' if result else '失败'}，获取{platform_items}条数据")
                        except Exception as e:
                            self.log(f"{platform}爬取出错: {str(e)}")
                        
                    elif platform == "链家":
                        self.log(f"开始爬取链家 - 城市: {city}, 类型: {house_type}")
                        try:
                            initial_platform_count = len(self.scraper.house_data)
                            result = self.scraper.scrape_lianjia(city, house_type, bedroom_num, livingroom_num, building_year, pages)
                            platform_items = len(self.scraper.house_data) - initial_platform_count
                            self.log(f"{platform}爬取{'成功' if result else '失败'}，获取{platform_items}条数据")
                        except Exception as e:
                            self.log(f"{platform}爬取出错: {str(e)}")
                        
                    else:
                        self.log(f"错误: 不支持的平台 '{platform}'")
                        continue
                    
                    # 计算每个平台的爬取结果
                    platform_items = len(self.scraper.house_data) - platform_data_before
                    self.log(f"平台 {platform} 爬取完成，共获取 {platform_items} 条数据")
                
                # 检查是否被停止
                if self.stop_event.is_set():
                    self.log("爬取已手动停止")
                    return
                
                # 计算总爬取结果
                total_items = len(self.scraper.house_data) - initial_data_count
                self.log(f"多平台爬取完成，共获取 {total_items} 条房源数据")
                
                # 自动保存结果
                if self.scraper.house_data:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = self.scraper.save_to_excel(f"house_data_{timestamp}.xlsx")
                    self.log(f"数据已保存到 {filename}")
            finally:
                # 如果启用了跳过验证，恢复原始的验证处理方法
                if original_handle_verification:
                    self.scraper.handle_verification = original_handle_verification
        
        except Exception as e:
            error_msg = f"爬取过程中出错: {str(e)}"
            self.log(error_msg)
            self.log(f"详细错误信息: {traceback.format_exc()}")
            
            # 在主线程显示错误消息
            self.root.after(0, lambda: messagebox.showerror("爬取错误", error_msg))
    
    def monitor_scraping(self):
        """监控爬取线程，并在完成后更新UI"""
        self.scraping_thread.join()  # 等待爬取线程完成
        
        # 在主线程中更新UI
        self.root.after(0, self.update_ui_after_scraping)
    
    def update_ui_after_scraping(self):
        """爬取结束后更新UI状态"""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.NORMAL)
        self.clear_button.config(state=tk.NORMAL)
        self.root.update()
        
        # 显示当前数据条数
        if hasattr(self, 'scraper') and self.scraper:
            data_count = len(self.scraper.house_data)
            self.status_var.set(f"就绪 - 当前有 {data_count} 条数据")
            
            # 如果爬取完成后有数据，提示用户可以导出
            if data_count > 0:
                self.log(f"爬取完成，获取到 {data_count} 条数据")
                if not hasattr(self, 'exported') or not self.exported:
                    self.log("您可以使用'导出数据'按钮保存结果")
        else:
            self.status_var.set("就绪")
    
    def stop_scraping(self):
        """停止爬取数据"""
        if self.scraping_thread and self.scraping_thread.is_alive():
            self.log("正在停止爬取...")
            self.stop_event.set()  # 设置停止事件
            self.status_var.set("正在停止...")
            self.stop_button.config(state=tk.DISABLED)
    
    def export_data(self):
        """导出数据到Excel"""
        if not self.scraper.house_data:
            messagebox.showinfo("提示", "没有数据可导出")
            return
            
        try:
            # 打开文件选择对话框
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel文件", "*.xlsx")],
                title="保存数据"
            )
            
            if file_path:
                filename = self.scraper.save_to_excel(file_path)
                if filename:
                    self.log(f"数据已导出到: {filename}")
                    messagebox.showinfo("导出成功", f"数据已成功导出到:\n{filename}")
                else:
                    self.log("导出数据失败")
                    messagebox.showerror("导出失败", "导出数据时出错")
        except Exception as e:
            self.log(f"导出数据时出错: {str(e)}")
            messagebox.showerror("错误", f"导出数据时出错: {str(e)}")
    
    def clear_data(self):
        """清除已爬取的数据"""
        if not self.scraper.house_data:
            messagebox.showinfo("提示", "没有数据需要清除")
            return
            
        if messagebox.askyesno("确认", "确定要清除所有已爬取的数据吗?"):
            count = len(self.scraper.house_data)
            self.scraper.clear_data()
            self.log(f"已清除 {count} 条数据")
            self.status_var.set("就绪")

def main():
    root = tk.Tk()
    app = HousingScraperGUI(root)
    root.mainloop()

# 启动主程序
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"程序出错: {e}")
        traceback.print_exc() 