"""Packaging smoke test. Never captures another app or sends mouse input."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import struct
import sys
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-test', required=True, type=Path, metavar='REPORT.json')
    args = parser.parse_args()
    report = {'passed': False, 'frozen': bool(getattr(sys, 'frozen', False)),
              'python': sys.version.split()[0], 'bits': struct.calcsize('P')*8}
    try:
        import cv2
        import numpy as np
        import PIL
        from PIL import Image
        import tkinter
        from app_paths import resource_path, data_dir
        from score_reader import read_score, TEMPLATES, ASPECTS
        from vision import detect, DetectionError, Detection, duration_ms
        from precise_input import PreciseInput

        root = resource_path('')
        required = ['PreciseInput.exe', 'third_party/score_templates.npz']
        for relative in required:
            assert resource_path(relative).is_file(), relative
        assert struct.calcsize('P') == 8, 'x64 build required'
        report['libraries'] = {'numpy': np.__version__, 'opencv': cv2.__version__, 'pillow': PIL.__version__}
        report['resources'] = required
        report['resource_root'] = str(root)
        report['data_dir'] = str(data_dir())
        report['tcl'] = tkinter.Tcl().eval('info patchlevel')

        # Use the bundled glyph assets to verify data inclusion and CV operations.
        frame = np.full((831, 467, 3), 255, dtype=np.uint8)
        x = 45
        for char in '38595':
            digit = int(char)
            width = round(48*float(ASPECTS[digit]))
            glyph = cv2.resize(TEMPLATES[digit].astype(np.uint8), (width, 48), interpolation=cv2.INTER_NEAREST)
            frame[115:163, x:x+width] = np.where(glyph[:, :, None] > 0, 0, 255)
            x += width+8
        assert read_score(Image.fromarray(frame)) == 38595
        report['score_reader'] = 38595
        try:
            detect(np.full((831, 467, 3), 200, dtype=np.uint8))
        except DetectionError:
            report['blank_frame_rejected'] = True
        else:
            raise AssertionError('blank frame accepted')
        sample = Detection((145, 480), (340, 370), 224, 224)
        assert 100 <= duration_ms(sample, 467, 1.) <= 1600

        # HWND -1 cannot be a foreground window. The worker rejects the command
        # before SendInput, exercising the embedded executable without input.
        worker = PreciseInput(-1)
        try:
            try:
                worker.hold(147)
            except RuntimeError as error:
                assert '游戏失去焦点或收到停止键' in str(error), str(error)
                report['unbound_input_rejected'] = True
            else:
                raise AssertionError('invalid window accepted')
        finally:
            worker.close()
        assert worker.process.returncode == 0

        get_name = ctypes.windll.kernel32.GetModuleFileNameW
        get_name.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        get_name.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        assert get_name(ctypes.pythonapi._handle, buffer, len(buffer))
        report['python_dll'] = buffer.value
        if report['frozen']:
            for module in (np, cv2, PIL):
                assert Path(module.__file__).resolve().is_relative_to(root), module.__file__
            assert Path(buffer.value).resolve().is_relative_to(root), buffer.value
        report['passed'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    args.self_test.parent.mkdir(parents=True, exist_ok=True)
    args.self_test.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['passed'] else 1
