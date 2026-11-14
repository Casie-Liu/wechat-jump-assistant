"""Bounded local mouse-hold worker, isolated from Python/Tk scheduling."""
from pathlib import Path
import subprocess


class PreciseInput:
    def __init__(self, hwnd):
        executable = Path(__file__).with_name('PreciseInput.exe')
        self.process = subprocess.Popen([str(executable), str(int(hwnd))],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='ascii', creationflags=subprocess.CREATE_NO_WINDOW)
        if self.process.stdout.readline().strip() != 'READY 40':
            self.close()
            raise RuntimeError('独立按压计时器启动失败')

    def hold(self, milliseconds):
        if not 100 <= milliseconds <= 1600:
            raise ValueError('按压时长超出范围')
        self.process.stdin.write(f'{int(milliseconds)}\n')
        self.process.stdin.flush()
        response = self.process.stdout.readline().strip()
        if response == 'CANCELLED':
            raise RuntimeError('游戏失去焦点或收到停止键，已停止')
        fields = response.split()
        if len(fields) != 4:
            raise RuntimeError('独立按压计时器未正常返回，已停止')
        interval, down, up = map(float, fields[:3])
        return dict(command_interval_ms=interval, down_call_ms=down,
                    up_call_ms=up, cancelled=fields[3] == '1')

    def close(self):
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=2)
