#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M3U播放列表管理器
支持交互式选择音乐文件并生成.m3u播放列表
"""

import os
import sys
import termios
import tty
import argparse
import json
from pathlib import Path


class ConfigManager:
    """配置管理器"""
    
    def __init__(self):
        self.config_file = Path("music_config.json")
        self.default_config = {
            "music_dir": "~/Music/音乐",
            "page_size": 20
        }
    
    def load_config(self):
        """加载配置文件"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return {**self.default_config, **config}
            except Exception as e:
                print(f"配置文件读取失败：{e}")
                return self.default_config
        return self.default_config
    
    def save_config(self, config):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"配置文件保存失败：{e}")
            return False
    
    def get_music_dir_interactive(self):
        """交互式获取音乐目录"""
        print("配置音乐目录")
        print("-" * 30)
        print("请选择配置方式：")
        print("1. 输入自定义路径")
        print("2. 使用默认路径")
        print("3. 浏览常见位置")
        
        while True:
            choice = input("请选择 (1-3): ").strip()
            
            if choice == '1':
                path = input("请输入音乐目录的完整路径: ").strip()
                if path and Path(path).exists():
                    return path
                else:
                    print("路径不存在，请重新输入")
                    
            elif choice == '2':
                return self.default_config["music_dir"]
                
            elif choice == '3':
                common_paths = [
                    f"/Users/{os.getenv('USER')}/Music",
                    f"/Users/{os.getenv('USER')}/Desktop/Music",
                    "/Users/Shared/Music",
                    "自定义路径"
                ]
                
                print("\n常见音乐目录：")
                for i, path in enumerate(common_paths, 1):
                    exists = "✓" if path != "自定义路径" and Path(path).exists() else "✗"
                    print(f"{i}. {path} [{exists}]")
                
                try:
                    sub_choice = int(input(f"请选择 (1-{len(common_paths)}): "))
                    if 1 <= sub_choice <= len(common_paths) - 1:
                        selected_path = common_paths[sub_choice - 1]
                        if Path(selected_path).exists():
                            return selected_path
                        else:
                            print("所选路径不存在")
                    elif sub_choice == len(common_paths):
                        path = input("请输入自定义路径: ").strip()
                        if path and Path(path).exists():
                            return path
                        else:
                            print("路径不存在")
                except ValueError:
                    print("请输入有效数字")
            else:
                print("请选择 1-3")


class MusicPlaylistManager:
    """音乐播放列表管理器"""
    
    def __init__(self, music_dir=None, page_size=20):
        # 设置音乐目录
        if music_dir:
            self.music_dir = Path(music_dir)
        else:
            self.music_dir = Path("/Users/song/Music/音乐")  # 默认路径作为后备
            
        self.music_files = []  # 存储所有音乐文件路径
        self.selected_files = set()  # 存储选中的文件索引
        self.current_index = 0  # 当前光标位置
        self.page_size = page_size  # 每页显示的歌曲数量
        self.current_page = 0  # 当前页码
        self.screen_initialized = False  # 屏幕是否已初始化
        self.existing_playlist = set()  # 现有播放列表中的歌曲（用于去重）
        self.append_mode = False  # 是否为追加模式
        self.target_playlist_file = None  # 目标播放列表文件
        self.search_mode = False  # 是否在搜索模式
        self.search_keyword = ""  # 搜索关键词
        self.filtered_files = []  # 搜索结果（存储原始索引）
        
        # 支持的音乐文件格式
        self.music_extensions = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg', '.wma'}
        
    def getch(self):
        """获取单个按键输入（macOS/Linux）"""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # 使用setcbreak而不是cbreak
            ch = sys.stdin.read(1)
            # 处理方向键（ESC序列）
            if ch == '\x1b':  # ESC
                ch += sys.stdin.read(2)
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    
    def clear_screen(self):
        """清屏"""
        print("\033[2J", end="")
        
    def move_cursor(self, row, col=1):
        """移动光标到指定位置"""
        print(f"\033[{row};{col}H", end="")
        
    def hide_cursor(self):
        """隐藏光标"""
        print("\033[?25l", end="")
        
    def show_cursor(self):
        """显示光标"""
        print("\033[?25h", end="")
        
    def clear_line(self):
        """清除当前行"""
        print("\033[K", end="")
        
    def init_screen(self):
        """初始化屏幕"""
        if not self.screen_initialized:
            self.clear_screen()
            self.hide_cursor()
            self.screen_initialized = True
    
    def cleanup_screen(self):
        """清理屏幕设置"""
        self.show_cursor()
        print()  # 换行
    
    def scan_music_files(self):
        """扫描音乐目录，获取所有音乐文件"""
        print("正在扫描音乐文件...")
        self.music_files = []
        
        if not self.music_dir.exists():
            print(f"错误：音乐目录不存在：{self.music_dir}")
            return False
            
        # 递归扫描所有音乐文件
        for file_path in self.music_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.music_extensions:
                # 使用相对路径，避免绝对路径过长
                relative_path = file_path.relative_to(self.music_dir.parent)
                self.music_files.append(str(relative_path))
        
        self.music_files.sort()  # 按文件名排序
        print(f"找到 {len(self.music_files)} 个音乐文件")
        return len(self.music_files) > 0
    
    def load_existing_playlist(self, playlist_file):
        """加载现有的.m3u播放列表"""
        try:
            playlist_path = Path(playlist_file)
            if not playlist_path.exists():
                return False, f"播放列表文件不存在：{playlist_file}"
            
            self.existing_playlist.clear()
            with open(playlist_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    # 标准化路径格式，确保一致性
                    normalized_path = str(Path(line).as_posix())
                    self.existing_playlist.add(normalized_path)
            
            self.target_playlist_file = playlist_file
            self.append_mode = True
            return True, f"成功加载播放列表：{playlist_file}，包含 {len(self.existing_playlist)} 首歌曲"
            
        except Exception as e:
            return False, f"加载播放列表时出错：{e}"
    
    def is_song_in_playlist(self, file_path):
        """检查歌曲是否已在播放列表中"""
        if not self.append_mode:
            return False
        normalized_path = str(Path(file_path).as_posix())
        return normalized_path in self.existing_playlist
    
    def get_available_playlists(self):
        """获取当前目录下的所有.m3u文件"""
        m3u_files = list(Path('.').glob('*.m3u'))
        return [str(f) for f in m3u_files]
    
    def search_music(self, keyword):
        """根据关键词搜索音乐文件"""
        if not keyword.strip():
            self.search_mode = False
            self.search_keyword = ""
            self.filtered_files = []
            self.current_index = 0
            self.current_page = 0
            return
        
        self.search_keyword = keyword.strip().lower()
        self.filtered_files = []
        
        # 搜索匹配的文件
        for i, file_path in enumerate(self.music_files):
            file_name = Path(file_path).name.lower()
            if self.search_keyword in file_name:
                self.filtered_files.append(i)
        
        self.search_mode = True
        self.current_index = 0
        self.current_page = 0
    
    def clear_search(self):
        """清除搜索"""
        self.search_mode = False
        self.search_keyword = ""
        self.filtered_files = []
        self.current_index = 0
        self.current_page = 0
    
    def get_current_display_files(self):
        """获取当前要显示的文件列表（考虑搜索模式）"""
        if self.search_mode:
            return self.filtered_files
        else:
            return list(range(len(self.music_files)))
    
    def get_current_page_items(self):
        """获取当前页的项目"""
        if self.search_mode:
            # 搜索模式：返回搜索结果的当前页
            start_idx = self.current_page * self.page_size
            end_idx = min(start_idx + self.page_size, len(self.filtered_files))
            page_indices = self.filtered_files[start_idx:end_idx]
            page_items = [self.music_files[i] for i in page_indices]
            return page_items, page_indices
        else:
            # 正常模式：返回所有文件的当前页
            start_idx = self.current_page * self.page_size
            end_idx = min(start_idx + self.page_size, len(self.music_files))
            page_items = self.music_files[start_idx:end_idx]
            page_indices = list(range(start_idx, end_idx))
            return page_items, page_indices
    
    def display_page(self):
        """显示当前页面"""
        # 初始化屏幕（只在第一次调用时清屏）
        self.init_screen()
        
        page_items, page_indices = self.get_current_page_items()
        
        # 计算总页数（根据当前模式）
        if self.search_mode:
            total_items = len(self.filtered_files)
        else:
            total_items = len(self.music_files)
        total_pages = (total_items + self.page_size - 1) // self.page_size if total_items > 0 else 1
        
        # 移动到屏幕顶部并显示标题信息
        self.move_cursor(1)
        self.clear_line()
        print("=" * 80)
        
        self.move_cursor(2)
        self.clear_line()
        mode_text = "追加模式" if self.append_mode else "新建模式"
        target_info = f" -> {self.target_playlist_file}" if self.append_mode else ""
        search_info = f" [搜索: {self.search_keyword}]" if self.search_mode else ""
        print(f"M3U播放列表管理器 ({mode_text}) - 第 {self.current_page + 1}/{total_pages} 页{target_info}{search_info}")
        
        self.move_cursor(3)
        self.clear_line()
        existing_count = len(self.existing_playlist) if self.append_mode else 0
        if self.search_mode:
            print(f"搜索到 {len(self.filtered_files)} 首歌曲，已选择 {len(self.selected_files)} 首，播放列表中已有 {existing_count} 首")
        else:
            print(f"总共 {len(self.music_files)} 首歌曲，已选择 {len(self.selected_files)} 首，播放列表中已有 {existing_count} 首")
        
        self.move_cursor(4)
        self.clear_line()
        print("=" * 80)
        
        self.move_cursor(5)
        self.clear_line()
        if self.search_mode:
            print("操作说明：↑↓移动光标 | 空格选择/取消 | ←→翻页 | Esc清除搜索 | S保存 | Q退出")
        else:
            print("操作说明：↑↓移动光标 | 空格选择/取消 | ←→翻页 | /搜索 | A追加到现有 | S保存 | Q退出")
        
        self.move_cursor(6)
        self.clear_line()
        print("=" * 80)
        
        self.move_cursor(7)
        self.clear_line()
        if self.append_mode:
            print("符号说明：▶当前选中 | ✓新选择 | ●已在播放列表中 | ○已在列表且新选择")
        else:
            print("符号说明：▶当前选中 | ✓已选择的歌曲")
        
        self.move_cursor(8)
        self.clear_line()
        print("=" * 80)
        
        # 显示当前页的音乐文件
        for i in range(self.page_size):
            row = 9 + i
            self.move_cursor(row)
            self.clear_line()
            
            if i < len(page_items):
                file_path = page_items[i]
                global_idx = page_indices[i]  # 使用新的索引系统
                
                # 在搜索模式下，current_index是相对于搜索结果的索引
                if self.search_mode:
                    display_idx = self.current_page * self.page_size + i
                    cursor = "▶ " if display_idx == self.current_index else "  "
                else:
                    cursor = "▶ " if global_idx == self.current_index else "  "
                
                # 确定状态符号
                is_selected = global_idx in self.selected_files
                is_in_playlist = self.is_song_in_playlist(file_path)
                
                if self.append_mode:
                    if is_in_playlist and is_selected:
                        checkbox = "○ "  # 已在播放列表中且新选择
                    elif is_in_playlist:
                        checkbox = "● "  # 已在播放列表中
                    elif is_selected:
                        checkbox = "✓ "  # 新选择
                    else:
                        checkbox = "  "
                else:
                    checkbox = "✓ " if is_selected else "  "
                
                # 获取文件名（不包含路径）
                file_name = Path(file_path).name
                
                # 如果文件名过长，截断显示
                if len(file_name) > 68:
                    file_name = file_name[:65] + "..."
                
                print(f"{cursor}{checkbox}{file_name}")
        
        # 显示页面导航信息
        footer_row = 9 + self.page_size
        self.move_cursor(footer_row)
        self.clear_line()
        print("=" * 80)
        
        self.move_cursor(footer_row + 1)
        self.clear_line()
        if total_pages > 1:
            print(f"使用 ←→ / PgUp/PgDn / Enter 翻页 (当前第 {self.current_page + 1}/{total_pages} 页)")
        
        # 刷新输出
        sys.stdout.flush()
    
    def handle_input(self):
        """处理用户输入"""
        while True:
            self.display_page()
            
            key = self.getch()
            
            if key == 'q' or key == 'Q':
                # 退出不保存
                self.cleanup_screen()
                print("退出程序，未保存任何更改。")
                return False
                
            elif key == 's' or key == 'S':
                # 保存播放列表
                return self.save_playlist()
                
            elif key == 'a' or key == 'A':
                # 追加到现有播放列表
                if not self.search_mode:  # 只在非搜索模式下允许
                    self.select_existing_playlist()
                    
            elif key == '/':
                # 开始搜索
                self.search_input()
                
            elif len(key) == 1 and ord(key) == 27:  # ESC键（单独的ESC） - 清除搜索
                if self.search_mode:
                    self.clear_search()
                
            elif key == ' ':
                # 选择/取消选择当前歌曲
                if self.search_mode:
                    # 搜索模式下，需要获取真实的文件索引
                    if self.current_index < len(self.filtered_files):
                        real_idx = self.filtered_files[self.current_index]
                        if real_idx in self.selected_files:
                            self.selected_files.remove(real_idx)
                        else:
                            self.selected_files.add(real_idx)
                else:
                    # 正常模式
                    if self.current_index in self.selected_files:
                        self.selected_files.remove(self.current_index)
                    else:
                        self.selected_files.add(self.current_index)
                    
            elif key == '\x1b[A':  # 上方向键
                if self.current_index > 0:
                    self.current_index -= 1
                    # 如果光标移到了上一页，自动翻页
                    if self.current_index < self.current_page * self.page_size:
                        self.current_page = max(0, self.current_page - 1)
                        
            elif key == '\x1b[B':  # 下方向键
                # 根据当前模式确定最大索引
                if self.search_mode:
                    max_index = len(self.filtered_files) - 1
                else:
                    max_index = len(self.music_files) - 1
                    
                if self.current_index < max_index:
                    self.current_index += 1
                    # 如果光标移到了下一页，自动翻页
                    if self.current_index >= (self.current_page + 1) * self.page_size:
                        if self.search_mode:
                            total_pages = (len(self.filtered_files) + self.page_size - 1) // self.page_size
                        else:
                            total_pages = (len(self.music_files) + self.page_size - 1) // self.page_size
                        self.current_page = min(total_pages - 1, self.current_page + 1)
                        
            elif key == '\r' or key == '\n':  # Enter键翻页
                if self.search_mode:
                    total_pages = (len(self.filtered_files) + self.page_size - 1) // self.page_size
                else:
                    total_pages = (len(self.music_files) + self.page_size - 1) // self.page_size
                self.current_page = (self.current_page + 1) % total_pages
                # 调整光标位置到当前页
                self.current_index = self.current_page * self.page_size
                
            elif key == '\x1b[5~':  # Page Up
                if self.current_page > 0:
                    self.current_page -= 1
                    self.current_index = self.current_page * self.page_size
                    
            elif key == '\x1b[6~':  # Page Down
                if self.search_mode:
                    total_pages = (len(self.filtered_files) + self.page_size - 1) // self.page_size
                else:
                    total_pages = (len(self.music_files) + self.page_size - 1) // self.page_size
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                    self.current_index = self.current_page * self.page_size
                    
            elif key == '\x1b[D':  # 左方向键 - 上一页
                if self.current_page > 0:
                    self.current_page -= 1
                    self.current_index = self.current_page * self.page_size
                    
            elif key == '\x1b[C':  # 右方向键 - 下一页
                if self.search_mode:
                    total_pages = (len(self.filtered_files) + self.page_size - 1) // self.page_size
                else:
                    total_pages = (len(self.music_files) + self.page_size - 1) // self.page_size
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                    self.current_index = self.current_page * self.page_size
    
    def select_existing_playlist(self):
        """选择要追加到的现有播放列表"""
        # 清理屏幕显示，切换到正常模式
        self.cleanup_screen()
        
        # 获取所有可用的.m3u文件
        available_playlists = self.get_available_playlists()
        
        if not available_playlists:
            print("当前目录下没有找到.m3u播放列表文件。")
            input("按任意键继续...")
            # 重新初始化屏幕
            self.screen_initialized = False
            return
        
        print("可用的播放列表文件：")
        print("-" * 40)
        for i, playlist in enumerate(available_playlists, 1):
            print(f"{i}. {playlist}")
        print("-" * 40)
        
        while True:
            try:
                choice = input(f"请选择播放列表 (1-{len(available_playlists)}) 或 0 取消: ").strip()
                
                if choice == '0':
                    break
                    
                choice_num = int(choice)
                if 1 <= choice_num <= len(available_playlists):
                    selected_playlist = available_playlists[choice_num - 1]
                    success, message = self.load_existing_playlist(selected_playlist)
                    
                    print(message)
                    if success:
                        print("现在您可以选择要添加的新歌曲。")
                        print("已存在的歌曲将显示为 ● 符号。")
                    input("按任意键继续...")
                    break
                else:
                    print(f"请输入 1-{len(available_playlists)} 之间的数字")
                    
            except ValueError:
                print("请输入有效的数字")
        
        # 重新初始化屏幕
        self.screen_initialized = False
    
    def search_input(self):
        """搜索输入界面"""
        # 清理屏幕显示，切换到正常模式
        self.cleanup_screen()
        
        print("搜索歌曲")
        print("-" * 20)
        keyword = input("请输入搜索关键词（支持歌曲名搜索）: ").strip()
        
        if keyword:
            self.search_music(keyword)
            search_count = len(self.filtered_files)
            if search_count > 0:
                print(f"找到 {search_count} 首匹配的歌曲")
            else:
                print("没有找到匹配的歌曲")
                self.clear_search()
        else:
            print("搜索关键词为空，取消搜索")
        
        input("按任意键继续...")
        # 重新初始化屏幕
        self.screen_initialized = False
    
    def save_playlist(self):
        """保存选中的音乐到.m3u文件"""
        # 清理屏幕显示，切换到正常模式
        self.cleanup_screen()
        
        if not self.selected_files:
            print("没有选择任何歌曲，无法生成播放列表。")
            input("按任意键继续...")
            return False
        
        if self.append_mode:
            # 追加模式：过滤掉已存在的歌曲
            new_songs = []
            duplicate_count = 0
            
            selected_indices = sorted(self.selected_files)
            for idx in selected_indices:
                file_path = self.music_files[idx]
                if not self.is_song_in_playlist(file_path):
                    new_songs.append(file_path)
                else:
                    duplicate_count += 1
            
            if not new_songs:
                print("所选择的歌曲都已经在播放列表中，没有新歌曲要添加。")
                input("按任意键继续...")
                return False
            
            print(f"准备添加 {len(new_songs)} 首新歌曲到 {self.target_playlist_file}")
            if duplicate_count > 0:
                print(f"跳过 {duplicate_count} 首重复的歌曲")
            
            confirm = input("确认追加？(y/N): ").strip().lower()
            if confirm != 'y':
                print("取消追加操作。")
                input("按任意键继续...")
                return False
            
            try:
                # 追加新歌曲到现有文件
                with open(self.target_playlist_file, 'a', encoding='utf-8') as f:
                    for file_path in new_songs:
                        clean_path = file_path.replace('&nbsp;', ' ').replace('&amp;', '&')
                        f.write(f"{clean_path}\n")
                
                print(f"成功添加 {len(new_songs)} 首歌曲到 {self.target_playlist_file}")
            
            except Exception as e:
                print(f"追加歌曲时出错: {e}")
                input("按任意键继续...")
                return False
        
        else:
            # 新建模式：创建新的播放列表文件
            print(f"已选择 {len(self.selected_files)} 首歌曲")
            playlist_name = input("请输入播放列表名称（不需要.m3u后缀）: ").strip()
            
            if not playlist_name:
                playlist_name = "playlist"
            
            # 确保文件名不包含非法字符
            playlist_name = "".join(c for c in playlist_name if c.isalnum() or c in (' ', '-', '_')).strip()
            playlist_file = f"{playlist_name}.m3u"
            
            try:
                with open(playlist_file, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n")  # M3U文件头
                    
                    # 按原顺序写入选中的歌曲
                    selected_indices = sorted(self.selected_files)
                    for idx in selected_indices:
                        file_path = self.music_files[idx]
                        # 写入文件路径，使用相对路径
                        # 避免&nbsp等HTML实体
                        clean_path = file_path.replace('&nbsp;', ' ').replace('&amp;', '&')
                        f.write(f"{clean_path}\n")
                
                print(f"播放列表已保存到: {playlist_file}")
                print(f"包含 {len(selected_indices)} 首歌曲")
                
            except Exception as e:
                print(f"保存播放列表时出错: {e}")
                input("按任意键继续...")
                return False
        
        input("按任意键退出...")
        return True
    
    def run(self):
        """运行主程序"""
        print("M3U播放列表管理器")
        print("=" * 40)
        
        # 扫描音乐文件
        if not self.scan_music_files():
            print("没有找到音乐文件，程序退出。")
            return
        
        # 开始交互
        try:
            self.handle_input()
        finally:
            # 确保程序结束时清理屏幕
            if self.screen_initialized:
                self.cleanup_screen()


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="M3U播放列表管理器 - 交互式音乐播放列表创建工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python3 music.py                           # 使用默认配置
  python3 music.py -d /path/to/music         # 指定音乐目录
  python3 music.py --config                  # 交互式配置音乐目录
  python3 music.py -d ~/Music --page-size 30 # 自定义目录和页面大小
        """
    )
    
    parser.add_argument(
        '-d', '--dir', '--music-dir',
        dest='music_dir',
        help='指定音乐目录路径'
    )
    
    parser.add_argument(
        '--page-size',
        type=int,
        default=20,
        help='每页显示的歌曲数量 (默认: 20)'
    )
    
    parser.add_argument(
        '--config',
        action='store_true',
        help='交互式配置音乐目录'
    )
    
    parser.add_argument(
        '--reset-config',
        action='store_true',
        help='重置配置文件为默认值'
    )
    
    return parser.parse_args()


def get_music_directory(args):
    """获取音乐目录路径"""
    config_manager = ConfigManager()
    
    # 如果用户要求重置配置
    if args.reset_config:
        config_manager.save_config(config_manager.default_config)
        print("配置已重置为默认值")
        return config_manager.default_config["music_dir"]
    
    # 如果指定了命令行参数
    if args.music_dir:
        music_dir = Path(args.music_dir).expanduser().resolve()
        if music_dir.exists():
            # 保存到配置文件
            config = config_manager.load_config()
            config["music_dir"] = str(music_dir)
            config["page_size"] = args.page_size
            config_manager.save_config(config)
            return str(music_dir)
        else:
            print(f"错误：指定的音乐目录不存在：{music_dir}")
            sys.exit(1)
    
    # 如果要求交互式配置
    if args.config:
        music_dir = config_manager.get_music_dir_interactive()
        if music_dir:
            config = config_manager.load_config()
            config["music_dir"] = music_dir
            config["page_size"] = args.page_size
            config_manager.save_config(config)
            print(f"配置已保存：{music_dir}")
            return music_dir
    
    # 加载现有配置
    config = config_manager.load_config()
    music_dir = Path(config["music_dir"]).expanduser().resolve()
    
    # 检查配置的目录是否存在
    if not music_dir.exists():
        print(f"配置的音乐目录不存在：{music_dir}")
        print("请选择以下操作：")
        print("1. 重新配置音乐目录")
        print("2. 使用命令行参数指定目录")
        print("3. 退出程序")
        
        choice = input("请选择 (1-3): ").strip()
        if choice == '1':
            new_dir = config_manager.get_music_dir_interactive()
            if new_dir:
                config["music_dir"] = new_dir
                config_manager.save_config(config)
                return new_dir
            else:
                sys.exit(1)
        elif choice == '2':
            print("请使用: python3 music.py -d /path/to/your/music")
            sys.exit(1)
        else:
            sys.exit(1)
    
    return str(music_dir)


def main():
    """主函数"""
    print("M3U播放列表管理器 v1.0")
    print("=" * 40)
    
    # 解析命令行参数
    args = parse_arguments()
    
    # 获取音乐目录
    try:
        music_dir = get_music_directory(args)
    except KeyboardInterrupt:
        print("\n用户取消操作")
        sys.exit(0)
    
    # 创建管理器实例并运行
    manager = None
    try:
        manager = MusicPlaylistManager(music_dir=music_dir, page_size=args.page_size)
        manager.run()
    except KeyboardInterrupt:
        if manager and manager.screen_initialized:
            manager.cleanup_screen()
        print("\n程序被用户中断。")
    except Exception as e:
        if manager and manager.screen_initialized:
            manager.cleanup_screen()
        print(f"程序运行出错: {e}")


if __name__ == "__main__":
    main()
