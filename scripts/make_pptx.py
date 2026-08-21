"""生成答辩 PPT 的 .pptx 成品文件（深色科技风，7 页，含 AI 图案与多配色）。

运行：python scripts/make_pptx.py
输出：output/slides/AI_Agent_Project_I_答辩.pptx
"""
from __future__ import annotations

import math
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

# ---------------- 配色板（深色科技 + 多色点缀） ----------------
BG = RGBColor(13, 13, 30)          # 更深背景
BG2 = RGBColor(28, 30, 58)         # 卡片背景
BG3 = RGBColor(40, 43, 80)         # 悬浮卡片
ACCENT = RGBColor(74, 144, 217)    # 亮蓝
CYAN = RGBColor(46, 196, 182)      # 青绿
PURPLE = RGBColor(156, 120, 255)   # 紫
ORANGE = RGBColor(255, 146, 72)    # 橙
PINK = RGBColor(255, 105, 180)     # 粉
YELLOW = RGBColor(255, 209, 102)   # 黄
WHITE = RGBColor(255, 255, 255)
GRAY = RGBColor(160, 165, 190)
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
SW, SH = 13.333, 7.5


# ---------------- 基础工具 ----------------
def _set_bg(slide, color=BG):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _blank():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    _set_bg(s)
    return s


def _textbox(slide, x, y, w, h, lines, size=18, color=WHITE, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.0,
             font=FONT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, item in enumerate(lines):
        if isinstance(item, str):
            text, kw = item, {}
        else:
            text, kw = item[0], item[1]
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = kw.get("align", align)
        p.space_after = Pt(kw.get("space_after", 8))
        p.line_spacing = kw.get("line_spacing", line_spacing)
        r = p.add_run()
        r.text = text
        r.font.size = Pt(kw.get("size", size))
        r.font.bold = kw.get("bold", bold)
        r.font.color.rgb = kw.get("color", color)
        r.font.name = kw.get("font", font)
    return box


def _shape(slide, stype, x, y, w, h, fill=None, line=None, line_w=Pt(1.5),
           rot=None):
    sh = slide.shapes.add_shape(stype, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        sh.fill.background()
    else:
        sh.fill.solid()
        sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = line_w
    sh.shadow.inherit = False
    if rot is not None:
        sh.rotation = rot
    return sh


def _rect(slide, x, y, w, h, fill=BG2, line=None, line_w=Pt(1.5), radius=None):
    sh = _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill=fill, line=line, line_w=line_w)
    if radius is not None:
        try:
            sh.adjustments[0] = radius
        except Exception:
            pass
    return sh


def _circle(slide, x, y, d, fill=None, line=None, line_w=Pt(1.5)):
    return _shape(slide, MSO_SHAPE.OVAL, x, y, d, d, fill=fill, line=line, line_w=line_w)


def _card(slide, x, y, w, h, title, body_lines, title_size=20, body_size=15,
          accent=ACCENT, title_color=WHITE):
    _rect(slide, x, y, w, h, fill=BG2, line=accent, line_w=Pt(1.2))
    _rect(slide, x, y, w, 0.1, fill=accent)
    _textbox(slide, x + 0.3, y + 0.25, w - 0.6, 0.65,
             [(title, {"size": title_size, "bold": True, "color": title_color})])
    _textbox(slide, x + 0.3, y + 0.95, w - 0.6, h - 1.1,
             [(t, {"size": body_size, "color": GRAY, "space_after": 5}) for t in body_lines])


def _dot(slide, x, y, color=ACCENT, d=0.16):
    return _circle(slide, x, y, d, fill=color)


def _conn(slide, x1, y1, x2, y2, color=ACCENT, width=Pt(2)):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = width
    c.shadow.inherit = False
    return c


def _footer(slide, page_no, title=""):
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(7.24), Inches(SW), Inches(0.03))
    ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT; ln.line.fill.background(); ln.shadow.inherit = False
    if title:
        _textbox(slide, 0.4, 7.25, 6.0, 0.25, [(title, {"size": 10, "color": GRAY})])
    _textbox(slide, SW - 1.1, 7.25, 0.8, 0.25,
             [(str(page_no), {"size": 12, "color": GRAY, "align": PP_ALIGN.RIGHT})])


def _title_block(slide, title, subtitle=""):
    _textbox(slide, 0.8, 0.45, 11.7, 1.0, [(title, {"size": 34, "bold": True, "color": WHITE})])
    _rect(slide, 0.85, 1.35, 2.2, 0.05, fill=CYAN)
    if subtitle:
        _textbox(slide, 3.2, 1.2, 9.4, 0.4, [(subtitle, {"size": 13, "color": GRAY})])


# ---------------- AI 图案库 ----------------
def neural_net(slide, x, y, layers=(3, 4, 3), r=0.09, gap=0.5,
               colors=(CYAN, ACCENT, PURPLE), label=None):
    """画一个神经网络节点图（输入/隐藏/输出层 + 连线）。"""
    x_off = x
    xs = []
    for li, n in enumerate(layers):
        total_h = n * gap
        start_y = y + (layers[0] * gap - total_h) / 2
        pts = [(x_off + li * 1.3, start_y + j * gap) for j in range(n)]
        xs.append(pts)
        for (px, py) in pts:
            _circle(slide, px, py, r * 2, fill=colors[li % len(colors)])
    for i in range(len(xs) - 1):
        for a in xs[i]:
            for b in xs[i + 1]:
                _conn(slide, a[0] + r * 2, a[1] + r, b[0], b[1] + r, color=RGBColor(90, 100, 150), width=Pt(0.75))
    if label:
        lx, lw = x - 0.2, 4.0
        if lx + lw > SW:  # 防止标签框超出画布右缘
            lw = SW - lx
        _textbox(slide, lx, y + (layers[0] * gap) + 0.15, lw, 0.4,
                 [(label, {"size": 14, "color": GRAY, "align": PP_ALIGN.CENTER})])


def robot_face(slide, x, y, d=1.6, body=BG2, eye=ACCENT, ear=PURPLE):
    """一个可爱的机器人头像。"""
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, d, d * 0.85, fill=body, line=CYAN, line_w=Pt(2))
    _shape(slide, MSO_SHAPE.OVAL, x + d * 0.18, y + d * 0.28, d * 0.2, d * 0.2, fill=eye)
    _shape(slide, MSO_SHAPE.OVAL, x + d * 0.62, y + d * 0.28, d * 0.2, d * 0.2, fill=eye)
    _shape(slide, MSO_SHAPE.OVAL, x + d * 0.3, y + d * 0.6, d * 0.4, d * 0.12, fill=PINK)
    _shape(slide, MSO_SHAPE.OVAL, x - 0.12, y + d * 0.22, d * 0.12, d * 0.5, fill=ear)
    _shape(slide, MSO_SHAPE.OVAL, x + d - 0.02, y + d * 0.22, d * 0.12, d * 0.5, fill=ear)


def chip(slide, x, y, s=1.3, color=ACCENT):
    """一个芯片图案（方块 + 四周引脚）。"""
    _shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, s, s, fill=BG3, line=color, line_w=Pt(2))
    pin = 0.07
    for i in range(3):
        yy = y + s * 0.2 + i * s * 0.3
        _shape(slide, MSO_SHAPE.RECTANGLE, x - pin - 0.06, yy, pin + 0.06, 0.05, fill=color)
        _shape(slide, MSO_SHAPE.RECTANGLE, x + s, yy, pin + 0.06, 0.05, fill=color)
        xx = x + s * 0.2 + i * s * 0.3
        _shape(slide, MSO_SHAPE.RECTANGLE, xx, y - pin - 0.06, 0.05, pin + 0.06, fill=color)
        _shape(slide, MSO_SHAPE.RECTANGLE, xx, y + s, 0.05, pin + 0.06, fill=color)


def circuit(slide, x, y, w, h, color=PURPLE, nodes=4):
    """电路板装饰：折线 + 节点圆点。"""
    import random
    random.seed(7)
    pts = [(x, y + h / 2)]
    for i in range(1, nodes):
        pts.append((x + w * i / nodes, y + random.uniform(h * 0.2, h * 0.8)))
    pts.append((x + w, y + h / 2))
    for i in range(len(pts) - 1):
        _conn(slide, pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color=color, width=Pt(1.25))
    for (px, py) in pts:
        _circle(slide, px - 0.05, py - 0.05, 0.1, fill=color)


def bg_deco(slide, variant=0):
    """每页背景的角落装饰（多色小圆/半透明色块），让版面不空。"""
    import random
    random.seed(variant)
    palette = [ACCENT, CYAN, PURPLE, PINK, ORANGE, YELLOW]
    # 左上角淡色大圆
    c = _circle(slide, -0.9, -1.0, 2.4, fill=RGBColor(30, 34, 70))
    c.fill.solid(); c.fill.fore_color.rgb = RGBColor(30, 34, 70)
    # 右下角小圆点阵列
    for _ in range(6):
        col = random.choice(palette)
        _circle(slide, SW - 2.0 + random.uniform(0, 1.4), 6.4 + random.uniform(0, 0.7), 0.08, fill=col)
    # 底部一条浅色光带
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(6.9), Inches(SW), Inches(0.03))
    ln.fill.solid(); ln.fill.fore_color.rgb = RGBColor(60, 65, 110); ln.line.fill.background(); ln.shadow.inherit = False


# ============================================================
# 第 1 页：封面（神经网络 + 机器人 + 芯片）
# ============================================================
s = _blank()
# 顶部装饰
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0.4), Inches(SW), Inches(0.06))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT; ln.line.fill.background(); ln.shadow.inherit = False
# 神经网络背景（右上）
neural_net(s, 10.2, 0.9, layers=(3, 5, 3), r=0.08, gap=0.38, label="Multi-Agent")
# 机器人（左下）
robot_face(s, 1.0, 5.2, d=1.5)
# 芯片（右下）
chip(s, 11.5, 5.3, s=1.1, color=CYAN)
# 大标题
_textbox(s, 1.0, 2.1, 11.3, 1.3,
         [("多智能体代码助手", {"size": 56, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
_textbox(s, 1.0, 3.45, 11.3, 0.6,
         [("Coordinator + Code / Debug / Doc Agent 自动化流水线", {"size": 22, "color": CYAN, "align": PP_ALIGN.CENTER})])
_textbox(s, 1.0, 4.15, 11.3, 0.5,
         [("2026 暑期 AI Agent 成长实践 · 项目 I", {"size": 16, "color": GRAY, "align": PP_ALIGN.CENTER})])
# 底部标签
tags = [("自动写代码", ACCENT), ("自动修 Bug", PINK), ("自动写文档", CYAN)]
for i, (t, col) in enumerate(tags):
    x = 2.9 + i * 3.0
    _rect(s, x, 5.55, 2.4, 0.85, fill=BG2, line=col, line_w=Pt(2), radius=0.5)
    _textbox(s, x, 5.7, 2.4, 0.55, [(t, {"size": 18, "bold": True, "color": col, "align": PP_ALIGN.CENTER})], anchor=MSO_ANCHOR.MIDDLE)
_textbox(s, 1.0, 6.7, 11.3, 0.4, [("汇报人：小明", {"size": 14, "color": GRAY, "align": PP_ALIGN.CENTER})])
s.notes_slide.notes_text_frame.text = "开场：老师们好，我的项目是多智能体代码助手，用 AI 自动完成写代码、运行、修Bug、写文档的整个闭环。"

# ============================================================
# 第 2 页：项目背景与目标
# ============================================================
s = _blank()
bg_deco(s, 2)
_title_block(s, "项目背景与目标", "为什么做、做到什么程度")
_card(s, 0.8, 1.9, 5.4, 4.6, "背景：开发中的痛点",
      ["每次写代码都要手动：写、跑、改、查文档",
       "重复机械的操作占用大量时间",
       "多工具切换，上下文断裂",
       "希望用 AI 自动化这条流水线"],
      accent=ORANGE)
# 右侧目标
goals = [
    ("一句话描述需求", "输入自然语言 → 自动生成可运行代码", ACCENT),
    ("自动定位修复", "运行失败 → Debug Agent 自动修（至多 N 轮）", PINK),
    ("自动写文档", "运行通过 → Doc Agent 生成 README", CYAN),
    ("全流程可视化", "事件流实时展示每个 Agent 的工作", PURPLE),
]
_textbox(s, 6.7, 1.9, 5.8, 0.6, [("目标", {"size": 22, "bold": True, "color": WHITE})])
for i, (t, g, col) in enumerate(goals):
    y = 2.7 + i * 1.15
    _dot(s, 6.8, y + 0.14, color=col)
    _textbox(s, 7.0, y + 0.05, 5.5, 0.4, [(t, {"size": 16, "bold": True, "color": col})])
    _textbox(s, 7.0, y + 0.42, 5.5, 0.6, [(g, {"size": 13, "color": GRAY})])
_footer(s, 2, "项目背景与目标")
s.notes_slide.notes_text_frame.text = "讲清楚为什么做：把写代码中重复、机械的部分交给多Agent协作完成。"

# ============================================================
# 第 3 页：系统架构（图形化 + 神经网络点缀）
# ============================================================
s = _blank()
bg_deco(s, 3)
_title_block(s, "系统架构：多智能体编排", "Coordinator 统一调度 · 事件流贯穿全流程")
# Coordinator
_rect(s, 4.4, 1.75, 4.5, 1.05, fill=ACCENT, radius=0.25)
_textbox(s, 4.4, 2.0, 4.5, 0.6, [("Coordinator（总控编排）", {"size": 19, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})], anchor=MSO_ANCHOR.MIDDLE)
# 三个 Agent
agents = [
    ("Code Agent", "生成代码", CYAN),
    ("Debug Agent", "运行 + 自动修复", PINK),
    ("Doc Agent", "生成 README", PURPLE),
]
ax = [1.1, 5.2, 9.4]
aw, ah = 2.9, 1.8
for (name, sub, col), x in zip(agents, ax):
    _rect(s, x, 4.0, aw, ah, fill=BG2, line=col, line_w=Pt(2))
    _textbox(s, x, 4.3, aw, 0.6, [(name, {"size": 19, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
    _textbox(s, x, 4.95, aw, 0.5, [(sub, {"size": 14, "color": col, "align": PP_ALIGN.CENTER})])
# 连线
for cx in (2.55, 6.65, 10.85):
    _conn(s, 6.65, 2.8, cx, 4.0, color=RGBColor(110, 120, 170), width=Pt(1.5))
# 事件流横条
_rect(s, 0.8, 6.15, 11.7, 0.7, fill=BG3, line=CYAN, radius=0.3)
_textbox(s, 0.8, 6.3, 11.7, 0.4, [("事件流 EventBus → CLI / SSE / Streamlit 实时展示", {"size": 16, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
# 右上角芯片点缀
chip(s, 12.1, 0.55, s=0.5, color=PURPLE)
_footer(s, 3, "系统架构")
s.notes_slide.notes_text_frame.text = "核心创新是多Agent分工：每个Agent职责单一，通过Coordinator编排和事件流联动。"

# ============================================================
# 第 4 页：核心技术实现（4 卡片 + 芯片）
# ============================================================
s = _blank()
bg_deco(s, 4)
_title_block(s, "核心技术实现", "四个关键设计")
tech = [
    ("LLM 抽象层", ["统一 chat 接口", "DeepSeek 默认，可换 Claude", "FakeClient 测试不花 token"], ACCENT),
    ("沙箱执行", ["subprocess 隔离", "临时目录 + 超时保护", "捕获输出 / 报错 / 退出码"], CYAN),
    ("修复循环", ["失败 → 报错喂回 LLM", "自动生成修复代码", "至多 N 轮（默认 3）"], PINK),
    ("安全设计", ["API Key 存 .env 不入库", "沙箱不装未知依赖", "事件流全流程可观测"], PURPLE),
]
pos = [(0.8, 1.9), (6.9, 1.9), (0.8, 4.6), (6.9, 4.6)]
for (t, lines, col), (x, y) in zip(tech, pos):
    _card(s, x, y, 5.6, 2.5, t, lines, title_size=20, body_size=15, accent=col)
chip(s, 0.3, 6.6, s=0.5, color=YELLOW)
_footer(s, 4, "核心技术")
s.notes_slide.notes_text_frame.text = "重点讲沙箱和安全设计，体现工程素养。"

# ============================================================
# 第 5 页：功能演示（3 卡片 + 结果横幅 + 机器人）
# ============================================================
s = _blank()
bg_deco(s, 5)
_title_block(s, "功能演示", "三种使用方式 · 全流程可视化")
demos = [
    ("⌨ 命令行 CLI", ["python -m app.cli", "\"写一个斐波那契程序\"", "实时打印 Agent 过程"], CYAN),
    ("🌐 Web 界面", ["Streamlit 可视化", "实时观看工作过程", "事件流逐条渲染"], PURPLE),
    ("⚡ API / SSE", ["POST /api/run 同步", "GET /api/run/stream 流式", "结构化事件推送"], ORANGE),
]
for (t, lines, col), x in zip(demos, [0.8, 4.8, 8.8]):
    _card(s, x, 1.9, 3.7, 3.5, t, lines, title_size=20, body_size=15, accent=col)
# 结果横幅
_rect(s, 0.8, 5.8, 11.7, 1.05, fill=ACCENT, radius=0.2)
_textbox(s, 0.8, 6.1, 11.7, 0.6, [("真实效果：生成 → 运行 → 修Bug → README，端到端 7.5 秒完成", {"size": 20, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})])
# 机器人点缀
robot_face(s, 11.7, 0.6, d=0.9)
_footer(s, 5, "功能演示")
s.notes_slide.notes_text_frame.text = "这里切到演示视频或现场demo，展示真实运行。"

# ============================================================
# 第 6 页：成果与数据（数字仪表盘 + 图表）
# ============================================================
s = _blank()
bg_deco(s, 6)
_title_block(s, "成果与数据", "用数据证明项目可用")
stats = [
    ("15", "pytest 测试全部通过", CYAN),
    ("7.5s", "端到端真实运行耗时", ACCENT),
    ("100%", "CI 全绿，推送自动验证", PURPLE),
    ("v1.0.0", "GitHub Release 已发布", ORANGE),
]
for (num, label, col), (x, y) in zip(stats, [(0.8, 1.9), (6.9, 1.9), (0.8, 4.6), (6.9, 4.6)]):
    h = 1.9 if y > 4.0 else 2.5  # 底部一排收缩，避免压到底部规范条
    _rect(s, x, y, 5.6, h, fill=BG2, line=col, line_w=Pt(2))
    _textbox(s, x + 0.3, y + 0.3, 5.0, 1.1, [(num, {"size": 50, "bold": True, "color": col})])
    _textbox(s, x + 0.3, y + 1.2, 5.0, 0.6, [(label, {"size": 16, "color": WHITE})])
# 底部工程规范条
_rect(s, 0.8, 6.55, 11.7, 0.55, fill=BG3, line=YELLOW, radius=0.3)
_textbox(s, 0.8, 6.65, 11.7, 0.4, [("工程规范：MIT License · CONTRIBUTING 贡献指南 · 三种入口全部实测可用", {"size": 15, "color": WHITE, "align": PP_ALIGN.CENTER})])
# 右下角芯片点缀
chip(s, 12.6, 6.6, s=0.5, color=PINK)
_footer(s, 6, "成果与数据")
s.notes_slide.notes_text_frame.text = "用数据说话，展示仓库地址和CI截图。"

# ============================================================
# 第 7 页：总结与展望 + 致谢
# ============================================================
s = _blank()
bg_deco(s, 7)
_title_block(s, "总结与展望", "一路收获，继续前行")
cols = [
    ("收获", ["多Agent 编排与事件驱动", "沙箱隔离 / LLM 抽象", "完整工程化交付经验"], CYAN),
    ("不足", ["仅支持单文件 Python", "修复质量依赖 LLM 能力", "缺少系统 Benchmark 统计"], ORANGE),
    ("展望", ["支持多文件与依赖安装", "新增测试生成 Agent", "建立成功率量化评估"], ACCENT),
]
for (t, lines, col), x in zip(cols, [0.8, 4.8, 8.8]):
    _card(s, x, 1.9, 3.7, 3.5, t, lines, title_size=20, body_size=15, accent=col)
# 致谢
_rect(s, 0.8, 5.8, 11.7, 1.05, fill=CYAN, radius=0.2)
_textbox(s, 0.8, 6.1, 11.7, 0.6, [("感谢聆听，敬请指正！", {"size": 26, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})])
# 机器人（右上角）+ 芯片（右侧边）
robot_face(s, 11.9, 0.5, d=0.85)
chip(s, 12.6, 3.0, s=0.5, color=PURPLE)
_footer(s, 7, "总结与展望")
s.notes_slide.notes_text_frame.text = "收尾：感谢老师，欢迎提问。"

out = "output/slides/AI_Agent_Project_I_答辩.pptx"
prs.save(out)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
print(f"OK: {out} ({len(prs.slides)} slides)")
