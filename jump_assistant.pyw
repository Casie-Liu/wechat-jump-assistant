"""Windows visual Jump assistant. Run locally; no network or client injection."""
import ctypes
from ctypes import wintypes as W
import json
import math
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageGrab, ImageTk, ImageDraw
    from vision import detect, duration_ms, press_start, landing_center_x, DetectionError, ALGORITHM
    from score_reader import read_score
    from precise_input import PreciseInput
except ImportError as error:
    tk.Tk().withdraw()
    messagebox.showerror('缺少依赖', f'{error}\n请先运行：python -m pip install -r requirements.txt')
    raise SystemExit(1)

BASE = Path(__file__).resolve().parent
user32 = ctypes.WinDLL('user32', use_last_error=True)
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    user32.SetProcessDPIAware()
user32.GetForegroundWindow.restype = W.HWND
user32.GetAncestor.argtypes = [W.HWND, W.UINT]
user32.GetAncestor.restype = W.HWND
user32.IsWindow.argtypes = [W.HWND]
user32.IsWindow.restype = W.BOOL
user32.IsWindowVisible.argtypes = [W.HWND]
user32.GetWindowTextLengthW.argtypes = [W.HWND]
user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.IsIconic.argtypes = [W.HWND]
user32.WindowFromPoint.argtypes = [W.POINT]
user32.WindowFromPoint.restype = W.HWND
dwmapi = ctypes.WinDLL('dwmapi')
dwmapi.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, ctypes.c_void_p, W.DWORD]


class MouseInput(ctypes.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('mouseData', W.DWORD),
                ('dwFlags', W.DWORD), ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [('wVk', W.WORD), ('wScan', W.WORD), ('dwFlags', W.DWORD),
                ('time', W.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [('uMsg', W.DWORD), ('wParamL', W.WORD), ('wParamH', W.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [('mi', MouseInput), ('ki', KeyboardInput), ('hi', HardwareInput)]


class Input(ctypes.Structure):
    _anonymous_ = ('u',)
    _fields_ = [('type', W.DWORD), ('u', InputUnion)]


user32.SendInput.argtypes = [W.UINT, ctypes.POINTER(Input), ctypes.c_int]
user32.SendInput.restype = W.UINT


def mouse_event(flags):
    event = Input(type=0, mi=MouseInput(dwFlags=flags))
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise RuntimeError('Windows 未接受鼠标输入，请正常权限运行微信与本程序')


def game_windows():
    found = []
    callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    @callback_type
    def visit(hwnd, _):
        size = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(size+1)
        user32.GetWindowTextW(hwnd, buf, size+1)
        if user32.IsWindowVisible(hwnd) and buf.value.strip() == '跳一跳':
            found.append((int(hwnd), buf.value))
        return True

    user32.EnumWindows(visit, 0)
    return found


def window_rect(hwnd):
    rect = W.RECT()
    if not user32.IsWindow(hwnd) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError('游戏窗口已关闭，请重新绑定')
    if user32.IsIconic(hwnd):
        raise RuntimeError('游戏窗口已最小化')
    visible = W.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(visible), ctypes.sizeof(visible)) == 0:
        rect = visible
    if rect.right-rect.left < 180 or rect.bottom-rect.top < 300:
        raise RuntimeError('游戏窗口太小')
    return (rect.left, rect.top, rect.right, rect.bottom)


def is_foreground(hwnd):
    return user32.GetAncestor(user32.GetForegroundWindow(), 2) == hwnd


def capture(hwnd, crop=None):
    if not is_foreground(hwnd):
        raise RuntimeError('游戏失去前台焦点，已停止；请重新开始')
    rect = window_rect(hwnd)
    picture = ImageGrab.grab(bbox=rect, all_screens=True).convert('RGB')
    width, height = picture.size
    # Upstream training images include the mini-program's title bar.
    crop = crop or (0, 0, 1, 1)
    box = tuple(round(v*(width if i % 2 == 0 else height)) for i, v in enumerate(crop))
    picture = picture.crop(box)
    return picture, rect, box


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('跳一跳 · 视觉辅助')
        self.ui_scale = max(1, self.root.winfo_fpixels('1i')/96)
        width = min(round(970*self.ui_scale), round(self.root.winfo_screenwidth()*.94))
        height = min(round(760*self.ui_scale), round(self.root.winfo_screenheight()*.90))
        # Keep control clicks to the left of the portrait game window so desktop
        # automation cursor decorations do not appear over the captured board.
        self.root.geometry(f'{width}x{height}+0+0')
        self.root.minsize(min(width, round(800*self.ui_scale)), min(height, round(680*self.ui_scale)))
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.hwnd = None
        self.crop = None
        self.bound_size = None
        self.saved_calibrated_size = None
        self.last_direction = None
        self.camera_middle = 242.5
        self.stop = threading.Event()
        self.events = queue.Queue()
        self.running = False
        self.inspecting = False
        self.photo = None
        self.preview_source = None
        self.preview_scale = 1
        self.selection_start = None
        self.selection_id = None
        self.frame_id = None
        self.selecting = False
        self.coefficient = tk.StringVar(value='1.00')
        self.wait = tk.StringVar(value='3.5')
        self.limit = tk.StringVar(value='2000')
        self.status = tk.StringVar(value='先在微信中进入游戏，再绑定窗口并检测。')
        self.calibrated = tk.BooleanVar(value=False)
        self.previous_hotkeys = {0x75: False, 0x76: False, 0x77: False, 0x78: False, 0x1B: False}
        self.load_config()
        self.build()
        self.root.after(50, self.poll)

    def build(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=6)
        bar = ttk.Frame(self.root, padding=14)
        bar.pack(fill='x')
        ttk.Label(bar, text='跳一跳视觉辅助', font=('Microsoft YaHei UI', 17, 'bold')).pack(side='left')
        ttk.Button(bar, text='绑定游戏窗口', command=self.bind).pack(side='right')
        ttk.Button(bar, text='开始全自动', command=self.start).pack(side='right', padx=8)
        body = ttk.Frame(self.root, padding=(14, 0, 14, 10))
        body.pack(fill='both', expand=True)
        panel = ttk.Frame(body, width=280)
        panel.pack(side='right', fill='y', padx=(14, 0))
        ttk.Label(panel, text='按压微调（默认 1.00）').pack(anchor='w', pady=(8, 2))
        ttk.Entry(panel, textvariable=self.coefficient, width=23).pack(fill='x')
        adjust = ttk.Frame(panel)
        adjust.pack(fill='x', pady=5)
        ttk.Button(adjust, text='跳短了 +3%', command=lambda: self.adjust(1.03)).pack(side='left')
        ttk.Button(adjust, text='跳远了 −3%', command=lambda: self.adjust(1/1.03)).pack(side='right')
        ttk.Label(panel, text='落地等待含奖励（秒，1.2—8）').pack(anchor='w', pady=(12, 2))
        ttk.Entry(panel, textvariable=self.wait).pack(fill='x')
        ttk.Label(panel, text='本次最多跳数（1—5000）').pack(anchor='w', pady=(12, 2))
        ttk.Entry(panel, textvariable=self.limit).pack(fill='x')
        ttk.Button(panel, text='检测一次  F6（只截图）', command=self.inspect).pack(fill='x', pady=(22, 6))
        ttk.Button(panel, text='重新框选游戏区域', command=self.select_region).pack(fill='x', pady=6)
        ttk.Button(panel, text='试跳一次  F7', command=lambda: self.start(single=True)).pack(fill='x', pady=6)
        ttk.Checkbutton(panel, text='已用试跳校准系数', variable=self.calibrated).pack(anchor='w', pady=8)
        ttk.Button(panel, text='开始全自动  F8', command=self.start).pack(fill='x', pady=6)
        ttk.Button(panel, text='立即停止  Esc / F8', command=self.stop.set).pack(fill='x', pady=6)
        ttk.Label(panel, text='F9：等待落地后安全暂停').pack(anchor='w', pady=4)
        ttk.Label(panel, text='目标：超过 38,594 分。\n落地预留 3.5 秒领取停留奖励。\n\n开始后控制面板会最小化。\n识别失败、切走游戏会停止。\n\n仅适配默认紫色棋子皮肤。\n初始系数需要实跳校准。', wraplength=round(270*self.ui_scale)).pack(anchor='w', pady=15)
        self.canvas = tk.Canvas(body, bg='#202833', highlightthickness=0)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<ButtonPress-1>', self.begin_selection)
        self.canvas.bind('<B1-Motion>', self.drag_selection)
        self.canvas.bind('<ButtonRelease-1>', self.end_selection)
        self.canvas.bind('<Configure>', lambda e: self.redraw())
        ttk.Label(self.root, textvariable=self.status, wraplength=round(900*self.ui_scale), padding=12).pack(fill='x')

    def load_config(self):
        try:
            cfg = json.loads((BASE/'settings.json').read_text(encoding='utf-8'))
            if cfg.get('algorithm') != ALGORITHM:
                return
            self.coefficient.set(str(cfg.get('coefficient', 1.00)))
            self.wait.set(str(cfg.get('wait', 3.5)))
            self.limit.set(str(cfg.get('limit', 2000)))
            if cfg.get('last_direction') in ('left', 'right'):
                self.last_direction = cfg['last_direction']
            self.camera_middle = float(cfg.get('camera_middle', 242.5))
            value = cfg.get('calibrated_size')
            if isinstance(value, list) and len(value) == 2:
                self.saved_calibrated_size = tuple(value)
        except (OSError, ValueError, TypeError):
            pass

    def settings(self):
        coefficient, wait, limit = float(self.coefficient.get()), float(self.wait.get()), int(self.limit.get())
        if not .3 <= coefficient <= 4 or not 1.2 <= wait <= 8 or not 1 <= limit <= 5000:
            raise ValueError('系数须为 0.3—4，等待须为 1.2—8 秒，跳数须为 1—5000')
        return coefficient, wait, limit

    def save_config(self):
        try:
            coefficient, wait, limit = self.settings()
            calibrated_size = self.bound_size if self.calibrated.get() else None
            (BASE/'settings.json').write_text(json.dumps(dict(algorithm=ALGORITHM, coefficient=coefficient,
                 wait=wait, limit=limit, calibrated_size=calibrated_size,
                 last_direction=self.last_direction, camera_middle=self.camera_middle), indent=2), encoding='utf-8')
            return True
        except (OSError, ValueError) as error:
            self.status.set(f'设置暂未保存：{error}')
            return False

    def bind(self):
        if self.running or self.inspecting:
            return
        windows = game_windows()
        if len(windows) != 1:
            messagebox.showinfo('绑定窗口', f'找到 {len(windows)} 个“跳一跳”窗口。请只保留一个，并停在游戏进行中的画面。')
            return
        self.hwnd = windows[0][0]
        self.crop = None
        self.calibrated.set(False)
        rect = window_rect(self.hwnd)
        self.bound_size = (rect[2]-rect[0], rect[3]-rect[1])
        if self.bound_size == self.saved_calibrated_size:
            self.calibrated.set(True)
        self.status.set('已绑定。点击“检测一次”，检查绿点是否位于棋子底部、红点是否位于下一平台中心。')

    def adjust(self, factor):
        self.stop.set()
        try:
            self.coefficient.set(f'{float(self.coefficient.get())*factor:.4f}')
            self.save_config()
        except (ValueError, OSError) as error:
            self.status.set(str(error))

    def inspect(self, full=False):
        if self.running or self.inspecting:
            return
        if self.hwnd is None:
            self.bind()
        if self.hwnd is None:
            return
        hwnd, crop = self.hwnd, self.crop
        try:
            coefficient, _, _ = self.settings()
        except ValueError as error:
            self.status.set(str(error))
            return
        self.inspecting = True
        self.root.iconify()

        def worker():
            try:
                user32.SetForegroundWindow(hwnd)
                rect = window_rect(hwnd)
                user32.SetCursorPos((rect[0]+rect[2])//2, rect[1]+round((rect[3]-rect[1])*.90))
                # Let desktop capture/automation pointer decorations fade before analysis.
                time.sleep(2.5)
                if full:
                    picture, _, _ = capture(hwnd, (0, 0, 1, 1))
                    self.events.put(('select', picture))
                else:
                    picture, _, _ = capture(hwnd, crop)
                    self.events.put(('preview', picture))
                    result = detect(np.array(picture))
                    ms = duration_ms(result, picture.width, coefficient)
                    self.events.put(('preview', self.annotate(picture, result)))
                    self.events.put(('status', f'识别成功：距离 {result.distance:.1f}px，预计按压 {ms}ms。先试跳并校准，再开启全自动。'))
            except Exception as error:
                self.events.put(('status', str(error)))
            finally:
                self.events.put(('restore', None))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def annotate(picture, result):
        out = picture.copy()
        draw = ImageDraw.Draw(out)
        draw.line([result.piece, result.target], fill='#37c6ff', width=2)
        for point, color in [(result.piece, '#00ff88'), (result.target, '#ff3c60')]:
            x, y = point
            draw.ellipse((x-5, y-5, x+5, y+5), fill=color)
        return out

    def select_region(self):
        self.inspect(full=True)

    def begin_selection(self, event):
        if not self.selecting:
            return
        self.selection_start = (event.x, event.y)
        if self.selection_id:
            self.canvas.delete(self.selection_id)
        self.selection_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#00ff88', width=2)

    def drag_selection(self, event):
        if self.selecting and self.selection_start:
            self.canvas.coords(self.selection_id, *self.selection_start, event.x, event.y)

    def end_selection(self, event):
        if not self.selecting or not self.selection_start or self.preview_source is None:
            return
        x, y = self.selection_start
        coords = (min(x, event.x), min(y, event.y), max(x, event.x), max(y, event.y))
        width, height = self.preview_source.size
        box = [max(0, min((width if i % 2 == 0 else height), value/self.preview_scale)) for i, value in enumerate(coords)]
        if box[2]-box[0] < 180 or box[3]-box[1] < 300:
            self.status.set('区域太小，请框选完整游戏窗口，包含顶部工具栏。')
            return
        self.crop = tuple(value/(width if i % 2 == 0 else height) for i, value in enumerate(box))
        self.selecting = False
        self.calibrated.set(False)
        self.status.set('游戏区域已更新。请点击“检测一次”重新检查。')

    def redraw(self):
        if self.preview_source is None:
            return
        width, height = self.preview_source.size
        self.preview_scale = min(max(1, self.canvas.winfo_width())/width, max(1, self.canvas.winfo_height())/height, 1.5)
        scaled = self.preview_source.resize((max(1, round(width*self.preview_scale)), max(1, round(height*self.preview_scale))))
        self.photo = ImageTk.PhotoImage(scaled)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

    def start(self, single=False):
        if self.inspecting:
            return
        if self.running:
            self.stop.set()
            return
        if self.hwnd is None:
            self.bind()
        if self.hwnd is None:
            return
        try:
            coefficient, wait, limit = self.settings()
            self.save_config()
            (BASE/'runtime'/'pause.request').unlink(missing_ok=True)
            if not single and not self.calibrated.get():
                self.status.set('请先检测并试跳，校准后勾选“已用试跳校准系数”。')
                return
            rect = window_rect(self.hwnd)
            size = (rect[2]-rect[0], rect[3]-rect[1])
            if size != self.bound_size:
                self.calibrated.set(False)
                raise RuntimeError('窗口大小已变化，请重新绑定、检测并校准')
        except (ValueError, RuntimeError, OSError) as error:
            self.status.set(str(error))
            return
        self.stop.clear()
        self.running = True
        self.selecting = False
        self.root.iconify()
        threading.Thread(target=self.run, args=(self.hwnd, self.crop, coefficient, wait, 1 if single else limit), daemon=True).start()

    def run(self, hwnd, crop, coefficient, wait, limit):
        completed = 0
        input_worker = None
        previous = None
        score = None
        runtime = BASE/'runtime'
        runtime.mkdir(exist_ok=True)

        def record(phase, picture=None, **extra):
            state = dict(phase=phase, presses=completed, score=score,
                         coefficient=coefficient, updated=time.time(), target_score=38595, **extra)
            try:
                if picture is not None:
                    picture.save(runtime/'last_frame.png')
                    if phase == 'detecting':
                        picture.save(runtime/f'previous_{completed%4}.png')
                temporary = runtime/'status.tmp'
                temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                for attempt in range(5):
                    try:
                        temporary.replace(runtime/'status.json')
                        break
                    except PermissionError:
                        if attempt == 4:
                            break
                        time.sleep(.005)
                with (runtime/'history.jsonl').open('a', encoding='utf-8') as history:
                    history.write(json.dumps(state, ensure_ascii=False)+'\n')
            except OSError:
                # Diagnostics must never interrupt input or a live game.
                pass

        try:
            record('starting')
            input_worker = PreciseInput(hwnd)
            user32.SetForegroundWindow(hwnd)
            initial_rect = window_rect(hwnd)
            user32.SetCursorPos((initial_rect[0]+initial_rect[2])//2,
                                initial_rect[1]+round((initial_rect[3]-initial_rect[1])*.90))
            if self.stop.wait(3):
                return
            for _ in range(limit):
                if self.stop.is_set() or (runtime/'pause.request').exists():
                    break
                picture, rect, box = capture(hwnd, crop)
                current_score = read_score(picture)
                if current_score is not None:
                    score = current_score
                record('detecting', picture)
                if score is not None and score >= 38595:
                    if self.stop.wait(.5):
                        return
                    confirmation, _, _ = capture(hwnd, crop)
                    confirmed_score = read_score(confirmation)
                    if confirmed_score is not None and confirmed_score >= 38595 and abs(confirmed_score-score) <= 2:
                        score = confirmed_score
                        confirmation.save(runtime/'goal_reached.png')
                        self.events.put(('status', f'目标达成：{score} 分，已停止。'))
                        record('goal_reached', confirmation)
                        return
                    raise RuntimeError('目标分数读数需人工核对，已停止')
                current_size = (rect[2]-rect[0], rect[3]-rect[1])
                if current_size != self.bound_size:
                    raise RuntimeError('窗口大小变化，已停止；请重新绑定并校准')
                result = detect(np.array(picture))
                if score == 0:
                    self.last_direction = None
                    self.camera_middle = (result.piece[0]+result.target[0])*467/picture.width/2
                if previous is not None:
                    old_result, old_pixels, old_score = previous
                    unchanged = (math.dist(result.piece, old_result.piece) < picture.width*.005
                                 and math.dist(result.target, old_result.target) < picture.width*.005)
                    pixels = np.array(picture).astype(np.int16)
                    if unchanged and pixels.shape == old_pixels.shape and np.mean(np.abs(pixels-old_pixels)) < 2:
                        raise RuntimeError('上一跳后棋盘没有变化，已停止；请检查游戏是否接收了按压')
                    center_x = landing_center_x(np.array(picture), result.piece)
                    move_x = old_result.target[0]-old_result.piece[0]
                    # A +1 score identifies a non-centre landing without an idle bonus.
                    # Update only on a reliably symmetric visible top surface.
                    if (center_x is not None and old_score is not None and score is not None
                            and score-old_score == 1 and abs(move_x) > picture.width*.12):
                        error_x = result.piece[0]-center_x
                        if abs(error_x) > picture.width/467:
                            relative_error = error_x*(1 if move_x > 0 else -1)/abs(move_x)
                            adjustment = max(-.0025, min(.0025, -.10*relative_error))
                            coefficient = max(.98, min(1.02, coefficient*(1+adjustment)))
                            self.events.put(('coefficient', coefficient))
                            record('calibrated', landing_error_x=error_x, adjustment=adjustment)
                virtual_start, direction, turning = press_start(result, picture.width,
                                                                self.last_direction, self.camera_middle)
                ms = duration_ms(result, picture.width, coefficient, start_x=virtual_start)
                record('ready', press_ms=ms, piece=result.piece, target=result.target,
                       virtual_start_x=virtual_start, turning=turning, direction=direction,
                       hint_used=result.hint_used)
                if self.stop.wait(.25):
                    break
                second, rect2, box2 = capture(hwnd, crop)
                result2 = detect(np.array(second))
                if rect != rect2 or box != box2:
                    raise RuntimeError('窗口发生移动，已停止')
                movement = max(math.dist(result.piece, result2.piece), math.dist(result.target, result2.target))
                if movement > picture.width*.012:
                    raise RuntimeError('画面尚未稳定或平台在移动，已停止；可增加落地等待')
                if self.stop.is_set() or (runtime/'pause.request').exists():
                    break
                click_x = rect[0]+box[0]+round(picture.width*.5)
                click_y = rect[1]+box[1]+round(picture.height*.83)
                if not is_foreground(hwnd):
                    raise RuntimeError('游戏失去焦点，已停止')
                hit = user32.WindowFromPoint(W.POINT(click_x, click_y))
                if user32.GetAncestor(hit, 2) != hwnd:
                    raise RuntimeError('游戏按压区域被其他窗口遮挡，已停止')
                user32.SetCursorPos(click_x, click_y)
                if self.stop.is_set() or not is_foreground(hwnd):
                    break
                # A separate managed process owns both DOWN and UP. Python/Tk
                # cannot hold the GIL across the release deadline. The worker
                # independently checks foreground, Escape and F8 while held.
                timing = input_worker.hold(ms)
                record('pressed', desired_ms=ms, **timing)
                completed += 1
                if timing['cancelled']:
                    self.stop.set()
                    break
                self.last_direction = direction
                self.events.put(('direction', direction))
                previous = (result2, np.array(second).astype(np.int16), score)
                self.events.put(('status', f'已执行 {completed} 次按压；上一跳 {ms}ms。Esc / F8 可停止。'))
                if self.stop.wait(wait):
                    break
            self.events.put(('status', f'已停止，本次执行 {completed} 次按压。请查看落地位置；跳短了加系数，跳远了减系数。'))
            after, _, _ = capture(hwnd, crop)
            score = read_score(after)
            if score is not None:
                detect(np.array(after))
                self.events.put(('validated', True))
            record('stopped', after)
        except Exception as error:
            record('error', reason=str(error))
            self.events.put(('status', f'{error}（已执行 {completed} 次按压）'))
        finally:
            if input_worker is not None:
                input_worker.close()
            self.events.put(('done', None))

    def poll(self):
        for key in (0x75, 0x76, 0x77, 0x78, 0x1B):
            down = bool(user32.GetAsyncKeyState(key) & 0x8000)
            if down and not self.previous_hotkeys[key]:
                if self.running and key == 0x78:
                    try:
                        (BASE/'runtime'/'pause.request').touch()
                    except OSError as error:
                        self.status.set(str(error))
                elif key == 0x1B or (self.running and key == 0x77):
                    self.stop.set()
                elif self.running:
                    pass
                elif user32.GetAncestor(user32.GetForegroundWindow(), 2) not in (
                        self.hwnd, user32.GetAncestor(self.root.winfo_id(), 2)):
                    pass
                elif key == 0x75:
                    self.inspect()
                elif key == 0x76:
                    self.start(single=True)
                elif key == 0x77:
                    self.start()
            self.previous_hotkeys[key] = down
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'status':
                self.status.set(payload)
            elif kind in ('preview', 'select'):
                self.preview_source = payload
                self.selecting = kind == 'select'
                if self.selecting:
                    self.status.set('在预览中拖出完整游戏窗口，包含顶部工具栏。')
                self.redraw()
            elif kind == 'done':
                self.running = False
                self.root.deiconify()
            elif kind == 'coefficient':
                self.coefficient.set(f'{payload:.5f}')
                self.save_config()
            elif kind == 'validated':
                self.calibrated.set(True)
                self.saved_calibrated_size = self.bound_size
                self.save_config()
            elif kind == 'direction':
                self.save_config()
            elif kind == 'restore':
                self.inspecting = False
                self.root.deiconify()
        self.root.after(5, self.poll)

    def close(self):
        self.stop.set()
        if self.running or self.inspecting:
            self.status.set('正在停止并释放鼠标，请稍候再关闭。')
            return
        self.root.destroy()


if __name__ == '__main__':
    App().root.mainloop()
