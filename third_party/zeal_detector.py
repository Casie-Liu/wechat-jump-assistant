#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跳一跳 桌面版 - 识别模块 v6
基于 v4 改进，针对 all_labeled(158) 数据集把 target 误差压到 <35px。

关键改进（相对 v4）：
1. 拒绝 top_y < TOP_REJECT 的候选，杀掉左上角计分数字 / 小程序顶栏 UI（解 154/157）。
2. side 过滤不再只看质心：只要 blob 延伸到"目标侧"就保留，再用顶部 apex 簇取 top_x，
   从而解决"目标台与当前台粘连成一个大 blob"的情况（解 027/142）。
3. 白色中心圆点检测：若目标台顶面中心附近存在小白圆点，用它精修 target_x（建议 #1）。
4. detect_state 修正：避免把"大面积白色台子"的正常游戏帧误判成 gameover（解 158）。
"""

import cv2
import numpy as np

W, H = 467, 831
CENTER_X = W / 2
PERSPECTIVE_CENTER_Y = 434.0
PERSPECTIVE_SLOPE = 0.435

# 真实目标台顶端在透视下不可能高于此行；低于它的几乎都是计分数字/顶栏 UI
TOP_REJECT = 300

# 台面中心局部精修：apex 选定后，在其周围窗口、顶面带内取所有前景的左右极值中点。
# 对对称箱子≈apex 不变；对不规则/被纹理切碎的台面（木板凳等）能合并碎块取真正中心。
TOPFACE_BAND = 22    # 顶面带高度（像素）
TOPFACE_HALF = 100   # apex 左右搜索半宽（像素）
# 顶面精修只取含 apex 的连续列段，允许 <=TOPFACE_GAP 的小间隙桥接被木纹切碎的同一台面，
# 遇更大空隙即停，避免把紧邻的另一座台子并进来（解 j129 邻台/圆桌中心偏移）。
TOPFACE_GAP = 8

# white_mask 触发所需的最小背景色差：低饱和高亮像素还须与背景有此色差才算"白台"，
# 否则浅奶油色背景会被整片误判为白色（参见 160.png 粘连灾难）。
WHITE_DIST = 12

# 白色定心圆点垂直门控：真正的台面定心白点与基准估计中心在透视下接近(实测 dy<=17)，
# 而方块正面竖面上的装饰圆点(如"眼睛")明显更低(实测 dy>=24)。阈值 20 落在干净间隙内：
# 接受真定心点(含粘连导致基准略偏时的 dy=17)、拒绝装饰眼睛(dy>=24)。
# 参见 162/076/111/092(装饰眼睛 dy24~28) 与 083/089/140/061/164(真定心点 dy1~17)。
WHITE_DOT_DY = 20


def detect_piece(img_bgr):
    """HSV 蓝紫分割 + 连通域取最大簇，避免抓到棋子以外的蓝色像素"""
    h, w = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    h_chan = hsv[:, :, 0].astype(int)
    # V < 130 排除亮蓝色台子（piece V~92-96，蓝色台子 V~196）
    mask = (hsv[:, :, 1] > 50) & (hsv[:, :, 2] > 50) & (hsv[:, :, 2] < 130) & \
           (h_chan > 95) & (h_chan < 155)
    mask[:60, :] = 0
    border = w // 10
    mask[:, :border] = 0
    mask[:, w - border:] = 0

    mask_u8 = mask.astype('uint8') * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask_u8)
    if n <= 1:
        return 0, 0, None
    largest_i, largest_area = 1, 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > largest_area:
            largest_area, largest_i = area, i
    if largest_area < 30:
        return 0, 0, None
    mask = (labels == largest_i)
    ys, xs = np.where(mask)
    if len(ys) < 30:
        return 0, 0, None
    bottom_y = int(ys.max())
    near = xs[ys >= bottom_y - 8]
    if len(near) == 0:
        return 0, 0, None
    piece_x = int(near.mean())
    piece_y = bottom_y - 9
    return piece_x, piece_y, mask


def _apex_x(xs_i, ys_i, piece_x, top_y):
    """取 blob 顶部 25% 行里、靠目标侧最远端那一簇像素的均值 x"""
    top_thresh = top_y + (ys_i.max() - top_y) * 0.25
    top_xs = xs_i[ys_i <= top_thresh]
    if len(top_xs) == 0:
        return None
    sorted_xs = np.sort(top_xs)
    clusters, cur = [], [sorted_xs[0]]
    for x in sorted_xs[1:]:
        if x - cur[-1] <= 10:
            cur.append(x)
        else:
            clusters.append(cur)
            cur = [x]
    clusters.append(cur)
    if piece_x < CENTER_X:
        best = max(clusters, key=lambda c: np.mean(c))
    else:
        best = min(clusters, key=lambda c: np.mean(c))
    return int(np.mean(best))


def _white_dot_refine(img_bgr, tx, ty):
    """在 (tx,ty) 附近找目标台顶面的小白圆点，命中则用其圆心精修 target_x。"""
    h, w = img_bgr.shape[:2]
    y0, y1 = max(0, ty - 40), min(h, ty + 30)
    x0, x1 = max(0, tx - 45), min(w, tx + 45)
    roi = img_bgr[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # 白圆点：高亮、低饱和
    wm = ((hsv[:, :, 2] > 215) & (hsv[:, :, 1] < 35)).astype('uint8') * 255
    n, labels, stats, cent = cv2.connectedComponentsWithStats(wm)
    best = None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bw = stats[i, cv2.CC_STAT_WIDTH]
        bh = stats[i, cv2.CC_STAT_HEIGHT]
        if area < 12 or area > 350:
            continue
        if bw == 0 or bh == 0:
            continue
        aspect = bw / float(bh)
        fill = area / float(bw * bh)
        # 近似圆/椭圆：长宽比适中、填充率高
        if 0.5 <= aspect <= 2.2 and fill > 0.55:
            cx = cent[i][0] + x0
            cy = cent[i][1] + y0
            # 垂直门控：装饰性竖面圆点比顶面中心低很多，丢弃
            if abs(cy - ty) > WHITE_DOT_DY:
                continue
            d = abs(cx - tx)
            if best is None or d < best[0]:
                best = (d, int(cx), int(cy))
    if best and best[0] <= 35:
        return best[1], best[2]
    return None


def _topface_refine(nonbg_bool, apex_x, top_y):
    """在 apex 周围窗口、顶面带内取所有前景列的左右极值中点。
    合并被纹理切碎的台面碎块 → 不规则台面也能取到真正中心。
    对对称台面返回值≈apex_x。"""
    h, w = nonbg_bool.shape
    x0, x1 = max(0, apex_x - TOPFACE_HALF), min(w, apex_x + TOPFACE_HALF)
    y0, y1 = top_y, min(h, top_y + TOPFACE_BAND)
    sub = nonbg_bool[y0:y1, x0:x1]
    cols = np.where(sub.any(axis=0))[0]
    if len(cols) == 0:
        return apex_x
    # 只取包含 apex 的连续列段：允许 <=TOPFACE_GAP 的小间隙桥接被木纹切碎的同一台面，
    # 但遇到更大的空隙就停止，避免把紧邻的另一座台子并进来（解 j129 邻台/圆桌偏移）。
    apex_rel = int(min(max(apex_x - x0, cols.min()), cols.max()))
    j = int(np.argmin(np.abs(cols - apex_rel)))
    lo = hi = cols[j]
    k = j
    while k - 1 >= 0 and cols[k] - cols[k - 1] <= TOPFACE_GAP:
        k -= 1
        lo = cols[k]
    k = j
    while k + 1 < len(cols) and cols[k + 1] - cols[k] <= TOPFACE_GAP:
        k += 1
        hi = cols[k]
    return x0 + (int(lo) + int(hi)) // 2


def detect_board(img_bgr, piece_x, piece_y):
    """
    目标台识别：背景色差+白色 → 连通域 → 候选打分选最优。
    side 判据用"是否延伸到目标侧"，对侧粘连也能解；top_x 取 apex 簇。
    """
    h, w = img_bgr.shape[:2]
    # 背景估计：从顶部角落的可靠空白区采样（计分栏之下、台子之上），避免被台子像素污染。
    # 旧版从棋子行采样，遇到浅色背景会把整片背景误判成前景而粘连成巨块。
    patches = [img_bgr[250:300, 15:85], img_bgr[250:300, w - 85:w - 15],
               img_bgr[305:345, 15:75], img_bgr[305:345, w - 75:w - 15]]
    corner = np.concatenate([p.reshape(-1, 3) for p in patches], axis=0)
    if corner.size == 0:
        return 0, 0
    bg = np.median(corner, axis=0).astype(int)
    # Local Windows adaptation: estimate the vertical background gradient from
    # the empty upper side strips. A constant colour merges the lower background
    # into platforms in some grey themes, shifting or clipping the selected apex.
    sample_y = np.arange(250, min(h, 345))
    strips = np.concatenate([img_bgr[250:min(h, 345), 15:75],
                             img_bgr[250:min(h, 345), w-75:w-15]], axis=1)
    row_colors = np.median(strips, axis=1)
    design = np.column_stack([sample_y, np.ones(len(sample_y))])
    keep = np.ones(len(sample_y), dtype=bool)
    for _ in range(3):
        fit = np.linalg.lstsq(design[keep], row_colors[keep], rcond=None)[0]
        residual = np.linalg.norm(row_colors-design@fit, axis=1)
        updated = residual < max(6, float(np.median(residual))*3)
        if updated.sum() < 30 or np.array_equal(updated, keep):
            break
        keep = updated
    bg_rows = np.clip(np.column_stack([np.arange(h), np.ones(h)])@fit, 0, 255)
    # Keep the upstream colour model for chromatic themes: translucent wood on
    # blue backgrounds relies on its original contrast segmentation (case 159).
    if np.ptp(bg) > 15:
        bg_rows = np.repeat(bg[None, :], h, axis=0)
    dist = np.sqrt(((img_bgr.astype(float) - bg_rows[:, None, :]) ** 2).sum(axis=2))
    nonbg = dist > 30
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    # 白色台子补充：低饱和高亮像素，且必须与背景有色差（dist>WHITE_DIST），
    # 否则在浅奶油色背景上整片背景会被当成白色而粘连成巨块（解新屏幕浅背景）。
    white_mask = (hsv[:, :, 2] > 200) & (hsv[:, :, 1] < 10) & (dist > WHITE_DIST)
    nonbg = nonbg | white_mask
    # 棋子遮挡：用棋子实际颜色轮廓（膨胀）替代旧的 ±70 大方框。
    # 旧方框过宽，当目标台紧贴/触碰棋子时会吃掉目标顶面中心，导致 base 偏向未遮挡的
    # 一侧、白定心点被 35px 门控拒绝 → 过冲掉落（解 j129 黄盒紧贴棋子）。
    _, _, _piece_mask = detect_piece(img_bgr)
    nearby_layout = abs(piece_x-CENTER_X) < 65
    if _piece_mask is not None and _piece_mask.any():
        dilation_size = 9 if nearby_layout else 31
        dil = cv2.dilate(_piece_mask.astype('uint8'),
                         np.ones((dilation_size, dilation_size), np.uint8), iterations=1).astype(bool)
        nonbg[dil] = False
    if nearby_layout:
        # detect_piece returns the body component; mask the disconnected head
        # precisely as well, without a tall rectangle across the adjacent top.
        yy, xx = np.ogrid[:h, :w]
        head = (xx-piece_x)**2+(yy-(piece_y-63))**2 <= 19**2
        nonbg[head] = False
    # 棋子底部接触/阴影窄条（轮廓未必覆盖到，补一条窄的竖直遮挡）。
    contact_up = 10 if nearby_layout else 80
    contact_half = 16 if nearby_layout else 22
    nonbg[max(0, piece_y - contact_up):min(h, piece_y + 15),
          max(0, piece_x - contact_half):min(w, piece_x + contact_half)] = False
    nonbg[:TOP_REJECT, :] = False
    nonbg[:, :w // 10] = False
    nonbg[:, w - w // 10:] = False
    nonbg[int(h * 0.85):, :] = False

    kernel = np.ones((3, 3), np.uint8)
    nonbg_eroded = cv2.erode(nonbg.astype('uint8') * 255, kernel, iterations=2)

    def find_candidates(mask_img):
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_img)
        cands = []
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < 50:
                continue
            ys_i = np.where(labels == i)[0]
            xs_i = np.where(labels == i)[1]
            top_y = int(ys_i.min())
            if top_y < TOP_REJECT:
                continue
            top_x = _apex_x(xs_i, ys_i, piece_x, top_y)
            if top_x is None:
                top_x = int(centroids[i][0])
            exp_y = PERSPECTIVE_CENTER_Y - PERSPECTIVE_SLOPE * abs(top_x - CENTER_X)
            persp_err = abs(top_y - exp_y)
            cands.append((top_y, top_x, area, persp_err))
        return cands

    candidates = find_candidates(nonbg_eroded)
    if not candidates:
        candidates = find_candidates(nonbg.astype('uint8') * 255)
    if not candidates:
        return 0, 0

    # 直接取最靠上的候选（top_y 最小）。不要用 persp_err<25 过滤：
    # 高台子的 apex(后顶点)远高于中心，persp_err 天然很大，会被矮装饰物(指示牌等)挤掉。
    # 最高点即真实目标台顶（wangshub 经典思路），矮装饰物 top_y 更大不会被选中。
    pool = candidates
    pool.sort(key=lambda c: c[0])  # top_y 最小（最靠上）的优先
    chosen_top_y, target_x, _, _ = pool[0]
    # 台面中心局部精修（用未腐蚀 mask，合并被纹理切碎的台面碎块，解木板凳类不规则台面）
    target_x = _topface_refine(nonbg, int(target_x), int(chosen_top_y))
    if nearby_layout:
        # A neighbouring bottle can hide one wing of a small diamond top.
        # Its upper rows remain symmetric, unlike the clipped lower outline.
        row_centres = []
        lo, hi = max(0, int(target_x)-35), min(w, int(target_x)+36)
        for row in range(int(chosen_top_y), min(h, int(chosen_top_y)+7)):
            xs = np.where(nonbg[row, lo:hi])[0]+lo
            if len(xs) >= 3 and xs[-1]-xs[0] < 60:
                row_centres.append((float(xs[0])+float(xs[-1]))/2)
        if len(row_centres) >= 4 and np.std(row_centres) < 1.5:
            proposed = int(round(float(np.median(row_centres))))
            if abs(proposed-target_x) <= 15:
                target_x = proposed
    target_y = PERSPECTIVE_CENTER_Y - PERSPECTIVE_SLOPE * abs(target_x - CENTER_X)

    # 白点精修
    refined = _white_dot_refine(img_bgr, target_x, int(round(target_y)))
    if refined is not None:
        target_x = refined[0]
        target_y = PERSPECTIVE_CENTER_Y - PERSPECTIVE_SLOPE * abs(target_x - CENTER_X)

    return int(target_x), int(round(target_y))


def detect_state(img_bgr):
    h, w = img_bgr.shape[:2]
    roi = img_bgr[int(h * 0.25):int(h * 0.75), int(w * 0.15):int(w * 0.85)]
    n = roi.shape[0] * roi.shape[1]
    dark = np.sum((roi < 80).all(axis=2)) / n
    if dark > 0.65:
        return 'leaderboard'
    # gameover/排行榜结束帧：深色覆盖层铺满全屏 → dark 极高(实测 0.44~0.72)。
    # 实测正常游戏帧 dark<=0.023，真结束帧 dark>=0.44，0.10 阈值两侧余量都很大。
    # 注意：**不能用 white 占比判 gameover**——白盒多的浅色/粉色主题正常帧 white 可达 0.38，
    # 而真结束帧是深色覆盖层 white≈0，white 分支只会误判（参见实机第五局 #90 后被误停）。
    if dark > 0.10:
        return 'gameover'
    return 'game'


def detect_all(img_bgr):
    state = detect_state(img_bgr)
    if state != 'game':
        return {'state': state, 'piece': None, 'target': None}
    px, py, _ = detect_piece(img_bgr)
    if not px:
        return {'state': 'game', 'piece': None, 'target': None}
    bx, by = detect_board(img_bgr, px, py)
    return {'state': 'game', 'piece': (px, py), 'target': (bx, by) if bx else None}
