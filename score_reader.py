"""Recognize the game's fixed score font using locally bundled Apache-2.0 samples."""
import cv2
import numpy as np
from app_paths import resource_path

with np.load(resource_path('third_party/score_templates.npz'), allow_pickle=False) as data:
    TEMPLATES=data['glyphs'].astype(float)
    ASPECTS=data['aspects']


def read_score(rgb):
    frame=cv2.resize(np.array(rgb),(467,831))
    roi=frame[100:200,35:420]
    mask=(roi.max(axis=2)<130).astype(np.uint8)
    cols=np.where(mask.any(axis=0))[0]
    runs=np.split(cols,np.where(np.diff(cols)>1)[0]+1)
    digits=[]
    for run in runs:
        if len(run)==0: continue
        x=int(run[0]);right=int(run[-1])+1
        ys=np.where(mask[:,x:right].any(axis=1))[0]
        y=int(ys.min());bottom=int(ys.max())+1
        w=right-x;h=bottom-y;area=int(mask[y:bottom,x:right].sum())
        if h<18 or h>80 or area<40:
            continue
        if w>65 or w<4:
            return None
        glyph=cv2.resize(mask[y:y+h,x:x+w],(24,32),interpolation=cv2.INTER_NEAREST)
        errors=np.mean(np.abs(TEMPLATES-glyph),axis=(1,2))+.10*np.abs(np.log((w/h)/ASPECTS))
        order=np.argsort(errors)
        if errors[order[0]]>.23 or errors[order[1]]-errors[order[0]]<.025:
            return None
        digits.append((x,str(int(order[0]))))
    if not 1<=len(digits)<=7:
        return None
    return int(''.join(value for _,value in sorted(digits)))
