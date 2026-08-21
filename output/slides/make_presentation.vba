Sub CreatePresentation()
    Dim pptApp As Object
    Dim pptPres As Object
    Dim pptSlide As Object
    Dim slideIndex As Integer

    ' ========================================
    ' 创建 PowerPoint 应用程序
    ' ========================================
    On Error Resume Next
    Set pptApp = GetObject(, "PowerPoint.Application")
    If pptApp Is Nothing Then
        Set pptApp = CreateObject("PowerPoint.Application")
    End If
    On Error GoTo 0

    pptApp.Visible = True
    Set pptPres = pptApp.Presentations.Add

    ' ========================================
    ' 配色（深色科技风）
    ' ========================================
    Dim COLOR_BG As Long: COLOR_BG = RGB(26, 26, 46)      ' #1A1A2E 深色背景
    Dim COLOR_ACCENT As Long: COLOR_ACCENT = RGB(74, 144, 217) ' #4A90D9 亮蓝
    Dim COLOR_TEXT As Long: COLOR_TEXT = RGB(255, 255, 255) ' 白字
    Dim COLOR_SUBTEXT As Long: COLOR_SUBTEXT = RGB(180, 185, 200) ' 浅灰
    Dim COLOR_CARD As Long: COLOR_CARD = RGB(38, 38, 64)  ' 卡片深色

    ' ========================================
    ' 第1页：封面
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 1) ' ppLayoutTitle
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "多智能体代码助手"
        .Shapes.Title.TextFrame.TextRange.Font.Size = 44
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Bold = msoTrue
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "项目 I · 2026 暑期 AI Agent 成长实践" & vbCrLf & "汇报人：小明"
        .Shapes(2).TextFrame.TextRange.Font.Size = 20
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_SUBTEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "开场：老师们好，我的项目是多智能体代码助手，用 AI 自动完成写代码、运行、修Bug、写文档的整个闭环。"
    End With

    ' ========================================
    ' 第2页：项目背景与目标
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "项目背景与目标"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "问题：日常开发中「写代码、跑代码、改Bug、写文档」占用了大量时间" & vbCrLf & _
            "思路：让多个 AI Agent 各司其职，协作完成这条流水线" & vbCrLf & _
            "目标1：输入一句自然语言，自动生成可运行的 Python 程序" & vbCrLf & _
            "目标2：运行失败时，Debug Agent 自动定位并修复（至多N轮）" & vbCrLf & _
            "目标3：成功后自动生成 README 文档，全流程可视化"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "这一页讲清楚为什么做：把写代码中重复、机械的部分交给多Agent协作完成。"
    End With

    ' ========================================
    ' 第3页：系统架构
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "系统架构：多智能体编排"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "Coordinator（总控编排）" & vbCrLf & _
            "  ├── Code Agent   : 自然语言 → 生成 Python 代码" & vbCrLf & _
            "  ├── Debug Agent  : 沙箱运行 → 失败自动修复（循环）" & vbCrLf & _
            "  ├── Doc Agent    : 运行通过 → 生成 README.md" & vbCrLf & _
            "  └── 事件流(EventBus) : 全过程实时可见，前端/CLI 渲染"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "核心创新是多Agent分工：每个Agent职责单一，通过Coordinator编排和事件流联动。可对照wiki里的架构图讲。"
    End With

    ' ========================================
    ' 第4页：核心技术实现
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "核心技术实现"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "LLM 抽象层：默认 DeepSeek，接口统一，可换 Claude" & vbCrLf & _
            "沙箱执行：subprocess 隔离 + 临时目录 + 超时保护" & vbCrLf & _
            "修复循环：失败 → 报错喂回 LLM → 重跑，至多 N 轮" & vbCrLf & _
            "事件流：结构化事件经 EventBus 广播，CLI/SSE/Web 三种消费端" & vbCrLf & _
            "安全：API Key 存 .env 不入库，沙箱不装未知依赖"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "重点讲沙箱和安全设计，体现工程素养。"
    End With

    ' ========================================
    ' 第5页：功能演示
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "功能演示"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "命令行：python -m app.cli \"写一个计算斐波那契数列的程序\"" & vbCrLf & _
            "Web 界面：Streamlit 实时观看 Agent 工作过程" & vbCrLf & _
            "API：POST /api/run（同步）+ GET /api/run/stream（SSE 流式）" & vbCrLf & _
            "真实效果：生成→运行→修Bug→README，端到端 7.5 秒完成"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "这里切到演示视频或现场demo，展示真实运行。"
    End With

    ' ========================================
    ' 第6页：成果与数据
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "成果与数据"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "测试：15 个 pytest 测试全部通过（Fake LLM，不消耗 token）" & vbCrLf & _
            "CI/CD：GitHub Actions 自动验证，推送即跑，全绿" & vbCrLf & _
            "版本：GitHub Release v1.0.0，含完整 Release Note" & vbCrLf & _
            "工程规范：MIT License + CONTRIBUTING 贡献指南" & vbCrLf & _
            "三种入口：CLI / Web / API，全部实测可用"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "用数据说话，展示仓库地址和CI截图。"
    End With

    ' ========================================
    ' 第7页：总结与展望 + 致谢
    ' ========================================
    slideIndex = slideIndex + 1
    Set pptSlide = pptPres.Slides.Add(slideIndex, 2) ' ppLayoutText
    With pptSlide
        .Background.Fill.ForeColor.RGB = COLOR_BG
        .Shapes.Title.TextFrame.TextRange.Text = "总结与展望"
        .Shapes.Title.TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes.Title.TextFrame.TextRange.Font.Name = "微软雅黑"
        .Shapes(2).TextFrame.TextRange.Text = "收获：掌握了多Agent编排、事件驱动、沙箱隔离、CI/CD 全套工程方法" & vbCrLf & _
            "不足：仅支持单文件 Python 项目，Debug 依赖 LLM 质量" & vbCrLf & _
            "展望：支持多文件与依赖安装、加入测试生成 Agent、Benchmark 数据统计" & vbCrLf & vbCrLf & _
            "感谢聆听，敬请指正！"
        .Shapes(2).TextFrame.TextRange.Font.Size = 18
        .Shapes(2).TextFrame.TextRange.Font.Color.RGB = COLOR_TEXT
        .Shapes(2).TextFrame.TextRange.Font.Name = "微软雅黑"
        .NotesPage.Shapes(2).TextFrame.TextRange.Text = "收尾：感谢老师，欢迎提问。"
    End With

    MsgBox "PPT 创建完成！共 " & slideIndex & " 页", vbInformation, "完成"
End Sub
