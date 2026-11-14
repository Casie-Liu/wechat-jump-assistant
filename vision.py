"""Windows adapter for zeal-up/wechat_jump_game (Apache-2.0).

The adapted upstream detector is in third_party/zeal_detector.py.
This adapter normalizes screenshots, validates output and maps it to preview pixels.
Press-time curves are fitted from local centre-hit observations; see third_party/SOURCE.txt.
"""
from dataclasses import dataclass
import math
import cv2
import numpy as np
from third_party.zeal_detector import detect_all

ALGORITHM = 'zeal-8b6b780-camera-landing-v2'


class DetectionError(ValueError):
    pass


@dataclass(frozen=True)
class Detection:
    piece: tuple[float, float]
    target: tuple[float, float]
    distance: float
    normalized_distance: float
    hint_used: bool = False


def centre_hint(img_bgr, piece_y):
    """Find a unique filled horizontal centre-hint ellipse above the piece.

    Search independently of an unreliable textured platform estimate. Vertical
    face eyes, hollow rings, text and small particles fail the shape constraints.
    """
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    top, bottom = 300, min(500, int(piece_y)-12)
    if bottom <= top:
        return None
    candidates = []
    for threshold in (215, 235, 245, 250):
        mask = ((hsv[top:bottom, :, 2] > threshold)
                & (hsv[top:bottom, :, 1] < 35)).astype(np.uint8)
        count, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
        for i in range(1, count):
            x, y, w, h, area = stats[i]
            if not (12 <= area <= 230 and 4 <= h <= 14 and 7 <= w <= 24):
                continue
            if not (1.35 <= w/h <= 2.4 and area/(w*h) > .65):
                continue
            cx, cy = centers[i]
            cy += top
            expected_y = 434-.435*abs(cx-233.5)
            if 45 < cx < 422 and abs(cy-expected_y) <= 15:
                candidates.append((float(cx), float(cy), int(area)))
    clusters = []
    for candidate in sorted(candidates, key=lambda item:-item[2]):
        if not any(math.dist(candidate[:2], prior[:2]) < 3 for prior in clusters):
            clusters.append(candidate)
    if len(clusters) != 1:
        return None
    return (int(clusters[0][0]), int(round(clusters[0][1])))


def detect(rgb: np.ndarray) -> Detection:
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise DetectionError('需要 RGB 游戏截图')
    height, width = rgb.shape[:2]
    if width < 180 or height < 300:
        raise DetectionError('游戏区域太小，请重新框选')
    canonical = cv2.resize(rgb, (467, 831))
    result = detect_all(cv2.cvtColor(canonical, cv2.COLOR_RGB2BGR))
    if result['state'] != 'game':
        raise DetectionError('已检测到结束或其他界面，已停止')
    if not result.get('piece'):
        raise DetectionError('未识别到棋子或目标台，已停止')
    px, py = result['piece']
    hint = centre_hint(cv2.cvtColor(canonical, cv2.COLOR_RGB2BGR), py)
    if hint is not None:
        hx, hy = hint
        hd = math.hypot(hx-px, hy-py)
        if not (40 < hd < 430 and hy < py-8 and abs(hy-py)/max(1,abs(hx-px)) <= 2.4):
            hint = None
        # A filled bright patch on a face eye can imitate an ellipse. A real
        # centre hint belongs on the top, never substantially below its apex.
        coarse = result.get('target')
        if coarse is not None and hy > coarse[1]+8:
            hint = None
    target = hint if hint is not None else result.get('target')
    if not target:
        raise DetectionError('未识别到目标台，已停止')
    tx, ty = target
    normalized_distance = math.hypot(tx-px, ty-py)
    if not (45 < px < 422 and 250 < py < 700 and 45 < tx < 422 and 270 < ty < 500):
        raise DetectionError('棋子或落点超出可靠范围，已停止')
    if not 40 < normalized_distance < 430 or ty >= py-8:
        raise DetectionError('跳跃距离或方向异常，已停止')
    if abs(ty-py)/max(1, abs(tx-px)) > 2.4:
        raise DetectionError('落点几何异常，可能有悬浮图标遮挡，已停止')
    piece = (px*width/467, py*height/831)
    target = (tx*width/467, ty*height/831)
    return Detection(piece, target, math.dist(piece, target), normalized_distance, hint is not None)


def duration_ms(detection: Detection, image_width: int, coefficient: float, start_x=None) -> int:
    if not .3 <= coefficient <= 4:
        raise ValueError('按压系数需要在 0.3 到 4 之间')
    # Fit measured travel, including the rendered landing offset relative to
    # the board camera axis. Using only desired centre-hit distances biases a
    # curve toward whichever edge happened to remain inside the centre zone.
    # Observations use actual DOWN-return to UP-call intervals from the native
    # timing worker, so its average input-call latency is already in the fit.
    actual_start = detection.piece[0] if start_x is None else start_x
    dx = (detection.target[0]-actual_start)*467/image_width
    if dx > 0:
        linear, quadratic, intercept = 239.19572164, 32.10180413, 4.96289705
    else:
        linear, quadratic, intercept = 237.73781266, 35.46882983, 5.3338629
    seconds = (-linear+math.sqrt(linear**2+4*quadratic*(abs(dx)-intercept)))/(2*quadratic)
    value = seconds*1000*coefficient
    if not 100 <= value <= 1600:
        raise DetectionError('计算出的按压时长超出 100—1600 毫秒，已停止')
    return round(value)


def press_start(detection, width, last_direction, middle=242.5):
    """Mirror the target about the camera axis when changing jump direction.

    The preceding jump's offset belongs to the other 3D axis. Measuring from
    that rendered offset again introduces an additional error after a turn.
    """
    direction = 'right' if detection.target[0] > detection.piece[0] else 'left'
    turning = last_direction is not None and last_direction != direction
    start = (2*middle*width/467-detection.target[0]) if turning else detection.piece[0]
    return start, direction, turning


def landing_center_x(rgb: np.ndarray, piece: tuple[float, float]):
    """Estimate the current symmetric top's centre from consistent horizontal colour spans.

    Return None on patterned, occluded, narrow or asymmetric surfaces rather than
    feed an uncertain observation into press-time calibration.
    """
    height, width = rgb.shape[:2]
    img = cv2.resize(rgb, (467, 831)).astype(np.int16)
    px, py = round(piece[0]*467/width), round(piece[1]*831/height)
    background = np.median(np.concatenate([img[230:280, 15:60].reshape(-1, 3),
                                           img[230:280, -60:-15].reshape(-1, 3)]), axis=0)
    mids, widths = [], []
    for y in range(max(0, py-8), min(831, py+9), 2):
        row_mids = []
        for offset in (-40, -30, -22, 22, 30, 40):
            seed = px+offset
            if not 0 <= seed < 467:
                continue
            color = img[y, seed]
            if np.linalg.norm(color-background) < 35 or color[2] > color[0]+12:
                continue
            left, right = max(0, px-140), min(467, px+141)
            xs = np.where(np.max(np.abs(img[y, left:right]-color), axis=1) < 12)[0]+left
            if not len(xs):
                continue
            groups = np.split(xs, np.where(np.diff(xs) > 45)[0]+1)
            for group in groups:
                l, r = int(group[0]), int(group[-1])
                span = r-l
                if l < px-5 and r > px+5 and 40 < span < 225 and l > left and r < right-1:
                    row_mids.append(((l+r)/2, span))
        if row_mids:
            chosen = max(row_mids, key=lambda item:item[1])
            mids.append(chosen[0]); widths.append(chosen[1])
    if len(mids) < 3:
        return None
    # Shadows and the occluding piece shorten some spans. Trust the widest,
    # mutually consistent slices rather than their truncated neighbours.
    selected = np.array(mids)[np.array(widths) >= max(widths)*.96]
    if len(selected) < 3 or np.std(selected) > 3.5:
        return None
    center = float(np.median(selected))
    if abs(center-px) > 30:
        return None
    return center*width/467
