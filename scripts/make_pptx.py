"""生成答辩 PPT 的 .pptx 成品文件（深色科技风，7 页，含架构图/卡片/仪表盘）。

运行：python scripts/make_pptx.py
输出：output/slides/AI_Agent_Project_I_答辩.pptx
"""
from __future__ import annotations

import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

# 配色（深色科技风）
BG = RGBColor(26, 26, 46)          # #1A1A2E 背景
BG2 = RGBColor(38, 38, 64)         # 卡片背景
ACCENT = RGBColor(74, 144, 217)    # 亮蓝
ACCENT2 = RGBColor(46, 196, 182)   # 青绿点缀
WHITE = RGBColor(255, 255, 255)
GRAY = RGBColor(180, 185, 200)
FONT = "微软雅黑"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

SW, SH = 13.333, 7.5


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
    """通用文本框。lines: list[(text, {color,size,bold})] 或 list[str]"""
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


def _rect(slide, x, y, w, h, fill=BG2, line=None, line_w=Pt(1.5),
          radius=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(x), Inches(y), Inches(w), Inches(h))
    if radius is not None:
        shape.adjustments[0] = radius
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = line_w
    shape.shadow.inherit = False
    return shape


def _card(slide, x, y, w, h, title, body_lines, title_size=20, body_size=15,
          accent=ACCENT):
    """带标题栏的卡片。"""
    _rect(slide, x, y, w, h, fill=BG2, line=accent)
    _rect(slide, x, y, w, 0.14, fill=accent, line=None)  # 顶部彩条
    _textbox(slide, x + 0.25, y + 0.3, w - 0.5, 0.7, [(title, {"size": title_size, "bold": True, "color": WHITE})])
    _textbox(slide, x + 0.25, y + 1.0, w - 0.5, h - 1.2,
             [(t, {"size": body_size, "color": GRAY, "space_after": 6}) for t in body_lines])


def _dot(slide, x, y, color=ACCENT, d=0.16):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def _footer(slide, page_no):
    # 底部装饰细线
    ln = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(7.22),
                                Inches(SW), Inches(0.03))
    ln.fill.solid()
    ln.fill.fore_color.rgb = ACCENT
    ln.line.fill.background()
    ln.shadow.inherit = False
    _textbox(slide, SW - 1.2, 7.25, 1.0, 0.25, [(str(page_no), {"size": 12, "color": GRAY, "align": PP_ALIGN.RIGHT})])


# ============================================================
# 第 1 页：封面
# ============================================================
s = _blank()
# 顶部装饰线
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0.4), Inches(SW), Inches(0.06))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT; ln.line.fill.background(); ln.shadow.inherit = False
# 大标题
_textbox(s, 1.0, 2.2, 11.3, 1.2, [("多智能体代码助手", {"size": 54, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
# 副标题
_textbox(s, 1.0, 3.5, 11.3, 0.6, [("Coordinator + Code / Debug / Doc Agent 自动化流水线",
                                    {"size": 22, "color": ACCENT, "align": PP_ALIGN.CENTER})])
_textbox(s, 1.0, 4.2, 11.3, 0.5, [("2026 暑期 AI Agent 成长实践 · 项目 I", {"size": 16, "color": GRAY, "align": PP_ALIGN.CENTER})])
# 底部三个能力标签
tags = ["自动写代码", "自动修 Bug", "自动写文档"]
for i, t in enumerate(tags):
    x = 2.2 + i * 3.2
    _rect(s, x, 5.4, 2.6, 0.9, fill=BG2, line=ACCENT, radius=0.5)
    _textbox(s, x, 5.55, 2.6, 0.6, [(t, {"size": 18, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})], anchor=MSO_ANCHOR.MIDDLE)
# 汇报人
_textbox(s, 1.0, 6.6, 11.3, 0.4, [("汇报人：小明", {"size": 14, "color": GRAY, "align": PP_ALIGN.CENTER})])
s.notes_slide.notes_text_frame.text = "开场：老师们好，我的项目是多智能体代码助手，用 AI 自动完成写代码、运行、修Bug、写文档的整个闭环。"

# ============================================================
# 第 2 页：项目背景与目标
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("项目背景与目标", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False
# 左侧：背景卡片
_card(s, 0.8, 2.0, 5.4, 4.5, "背景：开发中的痛点",
      ["每次写代码都要手动写、跑、改、查文档",
       "重复机械的操作占用了大量时间",
       "希望用 AI 自动化这条完整流水线"],
      accent=ACCENT)
# 右侧：目标列表（带圆点）
goals = ["输入一句自然语言 → 自动生成可运行代码",
         "运行失败 → Debug Agent 自动定位并修复（至多 N 轮）",
         "成功 → Doc Agent 自动生成 README 文档",
         "全过程事件流可视化，随时可查"]
_textbox(s, 6.6, 2.0, 6.0, 0.6, [("目标", {"size": 22, "bold": True, "color": WHITE})])
for i, g in enumerate(goals):
    y = 2.9 + i * 1.0
    _dot(s, 6.7, y + 0.12)
    _textbox(s, 7.0, y, 5.6, 0.8, [(g, {"size": 17, "color": WHITE, "space_after": 0})])
_footer(s, 2)
s.notes_slide.notes_text_frame.text = "讲清楚为什么做：把写代码中重复、机械的部分交给多Agent协作完成。"

# ============================================================
# 第 3 页：系统架构（图形化）
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("系统架构：多智能体编排", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False

# Coordinator 顶部
_rect(s, 4.0, 1.8, 5.3, 1.1, fill=ACCENT, radius=0.25)
_textbox(s, 4.0, 2.05, 5.3, 0.7, [("Coordinator（总控编排）", {"size": 20, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})], anchor=MSO_ANCHOR.MIDDLE)

# 三个 Agent 方块
agents = [
    ("Code Agent", "生成代码", ACCENT2),
    ("Debug Agent", "运行 + 自动修复", ACCENT),
    ("Doc Agent", "生成 README", ACCENT2),
]
agent_x = [1.0, 5.2, 9.4]
agent_w, agent_h = 2.9, 1.7
for (name, sub, col), x in zip(agents, agent_x):
    _rect(s, x, 4.1, agent_w, agent_h, fill=BG2, line=col, line_w=Pt(2))
    _textbox(s, x, 4.4, agent_w, 0.6, [(name, {"size": 19, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
    _textbox(s, x, 5.05, agent_w, 0.5, [(sub, {"size": 14, "color": GRAY, "align": PP_ALIGN.CENTER})])
# 连线：Coordinator 底部 → 每个 Agent 顶部
for cx in (2.45, 6.65, 10.85):
    conn = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                  Inches(6.65), Inches(2.9),
                                  Inches(cx), Inches(4.1))
    conn.line.color.rgb = ACCENT
    conn.line.width = Pt(2)
    conn.shadow.inherit = False
# 事件流横条
_rect(s, 0.8, 6.2, 11.7, 0.7, fill=BG2, line=ACCENT2, radius=0.3)
_textbox(s, 0.8, 6.35, 11.7, 0.4, [("事件流 EventBus → CLI / SSE / Streamlit 实时展示", {"size": 16, "bold": True, "color": WHITE, "align": PP_ALIGN.CENTER})])
_footer(s, 3)
s.notes_slide.notes_text_frame.text = "核心创新是多Agent分工：每个Agent职责单一，通过Coordinator编排和事件流联动。"

# ============================================================
# 第 4 页：核心技术实现（4 卡片）
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("核心技术实现", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False

tech = [
    ("LLM 抽象层", ["统一 chat 接口", "DeepSeek 默认，可换 Claude", "FakeClient 测试不花 token"]),
    ("沙箱执行", ["subprocess 隔离", "临时目录 + 超时保护", "捕获输出 / 报错 / 退出码"]),
    ("修复循环", ["失败 → 报错喂回 LLM", "自动生成修复代码", "至多 N 轮（默认 3）"]),
    ("安全设计", ["API Key 存 .env 不入库", "沙箱不装未知依赖", "事件流全流程可观测"]),
]
pos = [(0.8, 1.9), (6.9, 1.9), (0.8, 4.6), (6.9, 4.6)]
for (t, lines), (x, y) in zip(tech, pos):
    _card(s, x, y, 5.6, 2.5, t, lines, title_size=20, body_size=15)
_footer(s, 4)
s.notes_slide.notes_text_frame.text = "重点讲沙箱和安全设计，体现工程素养。"

# ============================================================
# 第 5 页：功能演示（3 卡片 + 结果横幅）
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("功能演示", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False

demos = [
    ("⌨ 命令行", ["python -m app.cli", "\"写一个斐波那契程序\"", "实时打印 Agent 过程"]),
    ("🌐 Web 界面", ["Streamlit 可视化", "实时观看工作过程", "事件流逐条渲染"]),
    ("⚡ API / SSE", ["POST /api/run", "GET /api/run/stream", "流式推送事件"]),
]
for (t, lines), x in zip(demos, [0.8, 4.8, 8.8]):
    _card(s, x, 1.9, 3.7, 3.4, t, lines, title_size=20, body_size=15)
# 结果横幅
_rect(s, 0.8, 5.7, 11.7, 1.1, fill=ACCENT, radius=0.2)
_textbox(s, 0.8, 6.0, 11.7, 0.6, [("真实效果：生成 → 运行 → 修Bug → README，端到端 7.5 秒完成", {"size": 20, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})])
_footer(s, 5)
s.notes_slide.notes_text_frame.text = "这里切到演示视频或现场demo，展示真实运行。"

# ============================================================
# 第 6 页：成果与数据（数字仪表盘）
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("成果与数据", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False

stats = [
    ("15", "pytest 测试全部通过", ACCENT2),
    ("7.5s", "端到端真实运行耗时", ACCENT),
    ("100%", "CI 全绿，每次推送自动验证", ACCENT2),
    ("v1.0.0", "GitHub Release 已发布", ACCENT),
]
for (num, label, col), (x, y) in zip(stats, [(0.8, 1.9), (6.9, 1.9), (0.8, 4.6), (6.9, 4.6)]):
    _rect(s, x, y, 5.6, 2.5, fill=BG2, line=col, line_w=Pt(2))
    _textbox(s, x + 0.3, y + 0.35, 5.0, 1.1, [(num, {"size": 48, "bold": True, "color": col})])
    _textbox(s, x + 0.3, y + 1.6, 5.0, 0.6, [(label, {"size": 16, "color": WHITE})])
# 底部工程规范条
_rect(s, 0.8, 6.5, 11.7, 0.6, fill=BG2, line=ACCENT2, radius=0.3)
_textbox(s, 0.8, 6.6, 11.7, 0.4, [("工程规范：MIT License · CONTRIBUTING 贡献指南 · 三种入口全部实测可用", {"size": 15, "color": GRAY, "align": PP_ALIGN.CENTER})])
_footer(s, 6)
s.notes_slide.notes_text_frame.text = "用数据说话，展示仓库地址和CI截图。"

# ============================================================
# 第 7 页：总结与展望 + 致谢
# ============================================================
s = _blank()
_textbox(s, 0.8, 0.5, 11.7, 1.0, [("总结与展望", {"size": 34, "bold": True, "color": ACCENT})])
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.85), Inches(1.4), Inches(2.2), Inches(0.05))
ln.fill.solid(); ln.fill.fore_color.rgb = ACCENT2; ln.line.fill.background(); ln.shadow.inherit = False

cols = [
    ("收获", ["多Agent 编排与事件驱动", "沙箱隔离 / LLM 抽象 / CI-CD", "完整工程化交付经验"], ACCENT2),
    ("不足", ["仅支持单文件 Python 项目", "修复质量依赖 LLM 能力", "缺少系统 Benchmark 统计"], RGBColor(224, 122, 95)),
    ("展望", ["支持多文件与依赖安装", "新增测试生成 Agent", "建立成功率/耗时量化评估"], ACCENT),
]
for (t, lines, col), x in zip(cols, [0.8, 4.8, 8.8]):
    _card(s, x, 1.9, 3.7, 3.4, t, lines, title_size=20, body_size=15, accent=col)
# 致谢
_rect(s, 0.8, 5.7, 11.7, 1.1, fill=ACCENT, radius=0.2)
_textbox(s, 0.8, 6.0, 11.7, 0.6, [("感谢聆听，敬请指正！", {"size": 24, "bold": True, "color": BG, "align": PP_ALIGN.CENTER})])
_footer(s, 7)
s.notes_slide.notes_text_frame.text = "收尾：感谢老师，欢迎提问。"

out = "output/slides/AI_Agent_Project_I_答辩.pptx"
prs.save(out)
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
print(f"OK: {out} ({len(prs.slides)} slides)")
