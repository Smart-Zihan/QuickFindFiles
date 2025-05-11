import os
import tkinter as tk
from tkinter import ttk, scrolledtext
from concurrent.futures import ThreadPoolExecutor
import threading
import sys  # 新增控制台输出支持
import datetime  # 新增：导入datetime模块
import shutil  # 新增：导入shutil模块获取终端尺寸
from colorama import init, AnsiToWin32  # 新增colorama导入

# 初始化colorama（必须在所有输出前调用）
init(autoreset=True)
stream = AnsiToWin32(sys.stdout).stream  # 兼容Windows的ANSI流

def get_all_drives():
    """获取Windows系统中所有可用的逻辑驱动器（修复：移除Unix专用的statvfs判断）"""
    drives = []
    for drive in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive_path = f"{drive}:\\"
        if os.path.exists(drive_path):  # 仅检查驱动器是否存在（Windows兼容）
            drives.append(drive_path)
    return drives if drives else [os.getcwd()]  # 无有效驱动器时回退到当前目录

# 移除 colorama 相关导入和初始化代码（原 import colorama 和 init/stream 行）

def on_search():
    keyword = entry_keyword.get().strip()  # 保留原始输入的关键字
    input_dir = entry_dir.get().strip()
    root_dirs = [input_dir] if input_dir else get_all_drives()
    
    text_result.delete(1.0, tk.END)
    text_result.insert(tk.END, "搜索已启动...\n")

    result_queue = []
    is_searching = True

    # 新增：创建独立进度条窗口
    progress_window = tk.Toplevel(window)
    progress_window.title("搜索进度")
    progress_window.geometry("400x80")
    progress_window.resizable(False, False)

    # 进度条组件
    progress_bar = ttk.Progressbar(progress_window, orient=tk.HORIZONTAL, length=350, mode='determinate')
    progress_bar.pack(pady=10)

    # 进度标签（显示百分比和总数）
    progress_label = ttk.Label(progress_window, text="0% (0/0)")
    progress_label.pack()

    # 预扫描统计总条目数（文件+目录）
    def count_entries(dir_path):
        """递归统计目录下的文件和子目录总数（跳过无权限目录）"""
        count = 0
        dir_stack = [dir_path]
        while dir_stack:
            current_dir = dir_stack.pop()
            try:
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        count += 1  # 每个条目（文件/目录）计数+1
                        if entry.is_dir(follow_symlinks=False):
                            dir_stack.append(entry.path)
            except (PermissionError, OSError):
                continue  # 跳过无权限目录，不计入总数
        return count

    total_estimated = sum(count_entries(dir) for dir in root_dirs)
    processed_count = 0  # 已处理条目计数器

    # 新增：GUI进度更新函数（线程安全）
    def update_progress():
        nonlocal processed_count
        processed_count += 1
        
        if total_estimated > 0:
            progress_percent = min(int(processed_count / total_estimated * 100), 100)
            progress_bar['value'] = progress_percent
            progress_label.config(text=f"{progress_percent}% ({processed_count}/{total_estimated})")
        else:
            progress_label.config(text="无有效条目")

    # 定义控制台日志输出函数（仅保留必要日志）
    def log_to_console(message):
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
        sys.stdout.write(f"{timestamp} {message}\n")
        sys.stdout.flush()

    # 后台执行搜索任务
    def background_search():
        nonlocal is_searching
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(
                    search_worker, 
                    dir, 
                    keyword, 
                    result_queue, 
                    log_to_console, 
                    update_progress  # 传递GUI进度更新回调
                ) for dir in root_dirs
            ]
            for future in futures:
                future.result()
        is_searching = False
        window.after(0, lambda: finish_search(result_queue, progress_window))  # 传递进度窗口参数

    # 搜索完成后关闭进度窗口（修改此处）
    def finish_search(result_queue, progress_window):
        progress_window.destroy()  # 关闭进度窗口
        unique_results = list(dict.fromkeys(result_queue))
        unique_results.sort()
        
        # 分类目录和文件
        folders = [path for path in unique_results if os.path.isdir(path)]
        files = [path for path in unique_results if os.path.isfile(path)]
        
        text_result.delete(1.0, tk.END)
        if unique_results:
            # 构造格式化输出（新增总数显示）
            output = f"已完成查找（包含{keyword}的目录/文件名 | 共{len(unique_results)}个）：\n"
            output += "     - 文件夹（目录）：\n"
            output += "\n".join(f"         - {folder}" for folder in folders) if folders else "         - 无"
            output += "\n     - 文件：\n"
            output += "\n".join(f"         - {file}" for file in files) if files else "         - 无"
            text_result.insert(tk.END, output)
        else:
            text_result.insert(tk.END, "未找到匹配的文件/目录")
        sys.stdout.write("\n搜索完成！结果已显示在界面中\n")
        sys.stdout.flush()

    # 保持 search_worker 函数不变（通过 window.after 触发进度更新）
    def search_worker(root_dir, keyword, result_queue, log_callback, update_progress):
        """迭代式目录遍历（非递归），减少函数调用开销"""
        dir_stack = [root_dir]
        while dir_stack:
            current_dir = dir_stack.pop()
            try:
                with os.scandir(current_dir) as entries:
                    for entry in entries:
                        try:
                            log_callback(f"正在处理：{entry.path}")
                            window.after(0, update_progress)  # 触发GUI进度更新（线程安全）
                            
                            if entry.is_dir(follow_symlinks=False):
                                if keyword.lower() in entry.name.lower():
                                    result_queue.append(entry.path)
                                dir_stack.append(entry.path)
                            elif entry.is_file():
                                if keyword.lower() in entry.name.lower():
                                    result_queue.append(entry.path)
                        except (PermissionError, OSError):
                            log_callback(f"跳过无权限项：{entry.path}")
                            continue
            except (PermissionError, OSError, FileNotFoundError) as e:
                log_callback(f"无法访问目录 {current_dir}，错误：{str(e)}")
                continue  # 跳过当前目录，继续处理下一个目录

    threading.Thread(target=background_search, daemon=True).start()

def finish_search(result_queue):
    """搜索完成后的界面更新"""
    unique_results = list(dict.fromkeys(result_queue))
    unique_results.sort()
    
    text_result.delete(1.0, tk.END)
    if unique_results:
        text_result.insert(tk.END, f"找到 {len(unique_results)} 个匹配项：\n")
        for item in unique_results:
            text_result.insert(tk.END, f"{item}\n")
    else:
        text_result.insert(tk.END, "未找到匹配的文件/目录")
    sys.stdout.write("\n搜索完成！结果已显示在界面中\n")
    sys.stdout.flush()

# 创建主窗口（移除进度条相关代码）
window = tk.Tk()
window.title("文件快速查找工具")
window.geometry("800x600")

frame_input = ttk.Frame(window, padding=10)
frame_input.pack(fill=tk.X)

# 目录输入
ttk.Label(frame_input, text="搜索目录（留空为当前驱动器）:").grid(row=0, column=0, padx=5, pady=5)
entry_dir = ttk.Entry(frame_input, width=60)
entry_dir.grid(row=0, column=1, padx=5, pady=5)

# 关键字输入
ttk.Label(frame_input, text="搜索关键字:").grid(row=1, column=0, padx=5, pady=5)
entry_keyword = ttk.Entry(frame_input, width=60)
entry_keyword.grid(row=1, column=1, padx=5, pady=5)

# 搜索按钮
btn_search = ttk.Button(frame_input, text="开始搜索", command=on_search)
btn_search.grid(row=0, column=2, rowspan=2, padx=10, pady=5, sticky="ns")

# 移除原进度条框架和组件代码

frame_result = ttk.Frame(window, padding=10)
frame_result.pack(fill=tk.BOTH, expand=True)

ttk.Label(frame_result, text="搜索结果（可复制）:").pack(anchor="w", padx=5, pady=5)
text_result = scrolledtext.ScrolledText(frame_result, wrap=tk.WORD, width=100, height=20)
text_result.pack(fill=tk.BOTH, expand=True)

window.mainloop()