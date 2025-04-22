#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
房价数据爬虫项目安装脚本
自动检查和安装所需的依赖，配置必要的环境
"""

import os
import sys
import subprocess
import platform
import time

def print_header(message):
    """打印带有格式的标题"""
    print("\n" + "=" * 60)
    print(f"  {message}")
    print("=" * 60)

def print_step(step_num, message):
    """打印步骤信息"""
    print(f"\n[步骤 {step_num}] {message}")

def print_success(message):
    """打印成功信息"""
    print(f"\n✓ {message}")

def print_error(message):
    """打印错误信息"""
    print(f"\n✗ {message}")

def print_warning(message):
    """打印警告信息"""
    print(f"\n⚠ {message}")

def check_python_version():
    """检查Python版本是否满足要求"""
    print_step(1, "检查Python版本")
    
    major, minor = sys.version_info.major, sys.version_info.minor
    print(f"当前Python版本: {major}.{minor}.{sys.version_info.micro}")
    
    if major < 3 or (major == 3 and minor < 6):
        print_error("需要Python 3.6或更高版本")
        print("请升级Python后重试")
        return False
    
    print_success(f"Python版本满足要求: {sys.version}")
    return True

def install_package(package_name):
    """安装指定的Python包"""
    print(f"正在安装 {package_name}...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
        print(f"{package_name} 安装成功！")
        return True
    except subprocess.CalledProcessError as e:
        print(f"安装 {package_name} 失败: {e}")
        return False

def install_packages(packages):
    """安装多个Python包"""
    success = True
    for package in packages:
        if not install_package(package):
            success = False
    return success

def check_and_install_dependencies():
    """检查并安装所需的依赖"""
    print_step(2, "检查并安装基本依赖")
    
    # 基本依赖列表
    basic_packages = [
        "requests",
        "beautifulsoup4",
        "pandas",
        "openpyxl",
        "fake-useragent",
        "pillow"
    ]
    
    # Selenium相关依赖
    selenium_packages = [
        "selenium",
        "opencv-python"
    ]
    
    print("正在安装基本依赖...")
    basic_success = install_packages(basic_packages)
    
    if basic_success:
        print_success("基本依赖安装完成")
    else:
        print_warning("部分基本依赖安装失败，您可能需要手动安装")
    
    print("\n是否安装自动验证所需的Selenium相关依赖? (y/n): ", end="")
    choice = input().strip().lower()
    
    if choice == 'y':
        print("正在安装Selenium相关依赖...")
        selenium_success = install_packages(selenium_packages)
        
        if selenium_success:
            print_success("Selenium相关依赖安装完成")
        else:
            print_warning("部分Selenium依赖安装失败，您可能需要手动安装")
    else:
        print("跳过Selenium依赖安装，自动验证功能将无法使用")
    
    return basic_success

def check_and_setup_chrome():
    """检查Chrome浏览器和ChromeDriver"""
    print_step(3, "检查Chrome浏览器和ChromeDriver")
    
    chrome_installed = False
    
    if platform.system() == "Windows":
        chrome_paths = [
            os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'Google\\Chrome\\Application\\chrome.exe'),
            os.path.join(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)'), 'Google\\Chrome\\Application\\chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google\\Chrome\\Application\\chrome.exe')
        ]
        
        for path in chrome_paths:
            if os.path.exists(path):
                chrome_installed = True
                print(f"检测到Chrome浏览器: {path}")
                break
    
    elif platform.system() == "Darwin":  # macOS
        if os.path.exists("/Applications/Google Chrome.app"):
            chrome_installed = True
            print("检测到Chrome浏览器: /Applications/Google Chrome.app")
    
    elif platform.system() == "Linux":
        try:
            subprocess.check_output(["which", "google-chrome"])
            chrome_installed = True
            print("检测到Chrome浏览器")
        except subprocess.CalledProcessError:
            pass
    
    if not chrome_installed:
        print_warning("未检测到Chrome浏览器")
        print("使用自动验证功能需要安装Chrome浏览器")
        print("请访问 https://www.google.com/chrome/ 下载并安装Chrome浏览器")
        
        return False
    
    # 检查ChromeDriver
    try:
        # 导入selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        
        try:
            print("正在检查ChromeDriver...")
            driver = webdriver.Chrome(options=options)
            driver.quit()
            print_success("ChromeDriver 已正确配置")
            return True
        except Exception as e:
            print_error(f"ChromeDriver 未正确配置: {e}")
            print("\n要安装ChromeDriver，请按照以下步骤操作：")
            
            if platform.system() == "Windows":
                print("\n在Windows上:")
                print("1. 检查你的Chrome浏览器版本 (在浏览器中访问 chrome://version/)")
                print("2. 访问 https://chromedriver.chromium.org/downloads 下载对应版本的ChromeDriver")
                print("3. 解压并将ChromeDriver.exe复制到Python安装目录或系统PATH路径中")
            
            elif platform.system() == "Darwin":  # macOS
                print("\n在macOS上:")
                print("1. 检查你的Chrome浏览器版本 (在浏览器中访问 chrome://version/)")
                print("2. 访问 https://chromedriver.chromium.org/downloads 下载对应版本的ChromeDriver")
                print("3. 解压后在终端中运行: sudo mv chromedriver /usr/local/bin/")
            
            elif platform.system() == "Linux":
                print("\n在Linux上:")
                print("1. 检查你的Chrome浏览器版本 (在浏览器中访问 chrome://version/)")
                print("2. 访问 https://chromedriver.chromium.org/downloads 下载对应版本的ChromeDriver")
                print("3. 解压后在终端中运行: sudo mv chromedriver /usr/local/bin/")
            
            return False
    
    except ImportError:
        print_error("未安装Selenium，请先安装Selenium库")
        return False

def create_directories():
    """创建必要的目录"""
    print_step(4, "创建必要的目录")
    
    directories = [
        'housing_data',      # 保存爬取的数据
        'verification_debug', # 验证码调试图片
        'debug_pages'        # 调试页面保存
    ]
    
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"已创建目录: {directory}")
        else:
            print(f"目录已存在: {directory}")
    
    print_success("所有必要目录已创建")
    return True

def test_installation():
    """测试安装是否成功"""
    print_step(5, "测试安装")
    
    try:
        print("测试基本依赖...")
        import requests
        import bs4
        import pandas
        import fake_useragent
        print_success("基本依赖测试通过")
        
        # 测试自动验证依赖
        try:
            print("测试自动验证依赖...")
            import selenium
            import cv2
            print_success("自动验证依赖测试通过")
            has_selenium = True
        except ImportError:
            print_warning("自动验证依赖未完全安装，自动验证功能可能无法使用")
            has_selenium = False
        
        return True, has_selenium
    
    except ImportError as e:
        print_error(f"测试失败: {e}")
        return False, False

def main():
    """主函数"""
    print_header("房价数据爬虫项目安装")
    
    # 检查Python版本
    if not check_python_version():
        return False
    
    # 安装依赖
    dependencies_ok = check_and_install_dependencies()
    
    if not dependencies_ok:
        print_warning("依赖安装存在问题，可能影响程序运行")
    
    # 检查Chrome和ChromeDriver (针对自动验证功能)
    chrome_ok = check_and_setup_chrome()
    
    # 创建目录
    directories_ok = create_directories()
    
    # 测试安装
    test_ok, has_selenium = test_installation()
    
    # 总结
    print_header("安装总结")
    
    if dependencies_ok and directories_ok and test_ok:
        print_success("基本安装成功！您可以运行标准爬虫程序")
        
        if has_selenium and chrome_ok:
            print_success("自动验证功能安装成功！您可以使用带自动验证功能的多平台爬虫")
        else:
            print_warning("自动验证功能未完全配置，您可以使用标准爬虫，但可能需要手动处理验证码")
    else:
        print_warning("安装存在问题，请解决上述错误后重试")
    
    print("\n使用说明:")
    print("1. 使用标准爬虫: python zhengzhou_housing_scraper.py")
    print("2. 使用多平台爬虫: python multi_platform_housing_scraper.py")
    print("3. 如需查看所有选项，请运行程序并按提示操作")
    
    return True

if __name__ == "__main__":
    success = main()
    
    if success:
        print("\n安装程序已完成")
    else:
        print("\n安装程序遇到错误，请解决后重试")
    
    print("\n按回车键退出...", end="")
    input() 