"""One visual direction for every portrait and scene, including older saves."""
STYLE_ID='anime-v1'
STYLE_LABEL='统一日式青春系动画画风'
STYLE_COMPACT='日式青春系TV动画，纤细干净线稿，自然修长比例，清透赛璐璐上色，细腻眼神，柔和光影'
STYLE_DETAIL=(STYLE_COMPACT+'。精致而克制的五官，清晰瞳孔与有层次的虹膜，鼻口简洁，头发分束细腻，衣褶简洁自然。'
              '使用低饱和冷暖配色、柔和自然光与一到两层清楚阴影；背景为精细手绘动画美术。'
              '保留末世废墟、装备和动作，但以现代日式青春群像TV动画的细腻人物作画呈现。')
STYLE_NEGATIVE='写实照片，真人脸，3D渲染，厚涂，油画笔触，粗黑轮廓线，美式漫画，Q版，大头短身，幼态脸，塑料质感，强烈霓虹眼光'
STYLE_NONHUMAN='日式TV动画机械与背景设定美术，纤细清晰线稿，清透赛璐璐上色，低饱和配色，柔和光影，精细手绘背景，主体为非人类几何构造'

def unify(prompt,nonhuman=False):
    for old in ('精细末世动画电影概念插画','末世动画电影概念插画','末世动画电影角色参考插画','末世动画电影插画','末世动画电影'):
        prompt=prompt.replace(old,'末世题材日式TV动画设定稿')
    return (STYLE_NONHUMAN if nonhuman else STYLE_DETAIL)+'。'+prompt
