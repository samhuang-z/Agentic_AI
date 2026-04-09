"""Generate report.pdf for Assignment 3 (Chinese version)."""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register Chinese font
pdfmetrics.registerFont(TTFont('ArialUnicode', '/Library/Fonts/Arial Unicode.ttf'))

def build_report():
    doc = SimpleDocTemplate(
        "report.pdf",
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    CN = 'ArialUnicode'

    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontName=CN, fontSize=20, spaceAfter=6, alignment=TA_CENTER
    )
    subtitle_style = ParagraphStyle(
        'Subtitle', parent=styles['Normal'],
        fontName=CN, fontSize=12, alignment=TA_CENTER, spaceAfter=20,
        textColor=HexColor('#666666')
    )
    h1 = ParagraphStyle(
        'H1', parent=styles['Heading1'],
        fontName=CN, fontSize=16, spaceBefore=20, spaceAfter=10,
        textColor=HexColor('#1a5276')
    )
    h2 = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        fontName=CN, fontSize=13, spaceBefore=14, spaceAfter=8,
        textColor=HexColor('#2c3e50')
    )
    body = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontName=CN, fontSize=10, leading=16, alignment=TA_JUSTIFY, spaceAfter=8
    )
    code_style = ParagraphStyle(
        'Code', parent=styles['Normal'],
        fontName=CN, fontSize=8, leading=12,
        backColor=HexColor('#f5f5f5'), spaceAfter=6,
        leftIndent=10, rightIndent=10
    )
    caption_style = ParagraphStyle(
        'Caption', parent=styles['Normal'],
        fontName=CN, fontSize=9, alignment=TA_CENTER, spaceAfter=12,
        textColor=HexColor('#666666')
    )

    def make_table_style(header_color='#2c3e50'):
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(header_color)),
            ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
            ('FONTNAME', (0, 0), (-1, -1), CN),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#bdc3c7')),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#ffffff'), HexColor('#f8f9fa')]),
        ])

    story = []

    # ================================================================
    # Title Page
    # ================================================================
    story.append(Spacer(1, 2*inch))
    story.append(Paragraph("Assignment 3：自主式多文件財報分析師", title_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("Agentic AI — 國立中央大學", subtitle_style))
    story.append(Paragraph("LangChain ReAct Agent vs. LangGraph 狀態機", subtitle_style))
    story.append(Spacer(1, 0.5*inch))
    story.append(Paragraph("日期：2026 年 4 月 9 日", subtitle_style))
    story.append(PageBreak())

    # ================================================================
    # 1. 系統架構概述
    # ================================================================
    story.append(Paragraph("1. 系統架構概述", h1))
    story.append(Paragraph(
        "本報告呈現一個自主式多文件財報分析系統的設計、實作與評估，該系統以兩種方式建構："
        "（1）LangChain ReAct Agent（Legacy）以及（2）LangGraph 狀態機。"
        "系統對 Apple 與 Tesla 的 10-K 年報進行 Retrieval-Augmented Generation（RAG），"
        "回答使用者的財務查詢並附上來源引用。",
        body
    ))
    story.append(Paragraph(
        "核心 Pipeline 流程：<b>PDF 載入</b>（PyMuPDF）→ <b>文字清洗</b> → "
        "<b>分塊</b>（RecursiveCharacterTextSplitter）→ <b>向量嵌入</b>（HuggingFace sentence-transformers）→ "
        "<b>向量儲存</b>（ChromaDB）→ <b>檢索與生成</b>（Claude Sonnet via LangChain / LangGraph）。",
        body
    ))

    story.append(Paragraph("1.1 LangGraph 架構", h2))
    story.append(Paragraph(
        "LangGraph 實作使用 <b>StateGraph</b>，包含四個節點與條件邊：",
        body
    ))
    story.append(Paragraph(
        "retrieve_node → grade_documents_node → (相關) generate_node → END<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "→ (不相關) rewrite_node → retrieve_node（最多重試 2 次）",
        code_style
    ))
    story.append(Paragraph(
        "狀態字典追蹤：question、documents、generation、search_count 和 needs_rewrite。"
        "這使得圖能在重試過程中維持上下文，並在每一步做出智慧決策。",
        body
    ))

    # ================================================================
    # 2. 各 Task 實作說明
    # ================================================================
    story.append(Paragraph("2. 各 Task 實作說明", h1))

    story.append(Paragraph("2.1 Task A：LangChain ReAct Prompt（Legacy Agent）", h2))
    story.append(Paragraph(
        "ReAct prompt 模板的設計包含三層要求：",
        body
    ))
    story.append(Paragraph(
        "<b>技術要求：</b>包含所有必要佔位符（{tools}、{tool_names}、{input}、{agent_scratchpad}）。"
        "<b>結構要求：</b>強制執行 Question → Thought → Action → Action Input → Observation → Final Answer 迴圈。"
        "<b>行為約束：</b>（1）Final Answer 必須用英文、（2）年份精度警告——區分 2024 / 2023 / 2022 欄位、"
        "（3）誠實性約束——找不到資料時回答 \"I don't know\"、（4）比較題必須搜尋雙方資料源、"
        "（5）必須引用來源。",
        body
    ))

    story.append(Paragraph("2.2 Task B：Intelligent Router（智慧路由）", h2))
    story.append(Paragraph(
        "路由器透過 LLM 呼叫將查詢分類為四個類別：\"apple\"、\"tesla\"、\"both\" 或 \"none\"。"
        "Prompt 包含明確的路由規則與實體關鍵詞範例（例如 iPhone → apple、Elon Musk → tesla）。"
        "輸出格式為 JSON（{\"datasource\": \"...\"}），附帶 markdown 包裹的 fallback 解析。"
        "當解析失敗時預設路由到 \"both\"，確保所有查詢都能得到回答。",
        body
    ))

    story.append(Paragraph("2.3 Task C：Relevance Grader（相關性評分器）", h2))
    story.append(Paragraph(
        "評分器以二元「yes」/「no」判斷檢索到的文件是否與使用者問題相關。"
        "System Prompt 指定三項評分標準：（1）文件包含與問題直接相關的具體財務資料、"
        "（2）文件並非離題或來自錯誤的公司 / 年份、（3）對於詢問未來資料的陷阱問題，"
        "僅當文件能確認該資訊不存在時才判為「yes」。"
        "這種細緻的評分策略避免了不必要的改寫，讓系統能誠實地報告缺失資訊。",
        body
    ))

    story.append(Paragraph("2.4 Task D：Query Rewriter（查詢改寫器）", h2))
    story.append(Paragraph(
        "當評分器回傳「no」時，改寫器以五種策略轉換查詢："
        "（1）將模糊用語替換為精確財務術語（例：「花了多少在新科技上」→「Research and Development expenses」）、"
        "（2）補充明確年份（預設 FY2024）、（3）使用財務報表的確切項目名稱、"
        "（4）將中文查詢翻譯為英文財務術語、（5）明確指定公司名稱。"
        "系統包含 SystemMessage 以提供角色上下文。",
        body
    ))

    story.append(Paragraph("2.5 Task E：Final Generator（最終生成器）", h2))
    story.append(Paragraph(
        "生成器以六項嚴格規則合成答案：英文輸出、以 [Source: X 10-K] 格式引用來源、"
        "年份精度驗證、報告確切數字、對缺失資訊誠實回答、以及比較題的結構化格式。",
        body
    ))

    story.append(PageBreak())

    # ================================================================
    # 3. LangGraph vs LangChain 詳細比較（30 分）
    # ================================================================
    story.append(Paragraph("3. LangGraph vs LangChain 詳細比較", h1))

    story.append(Paragraph("3.1 評估結果", h2))
    story.append(Paragraph(
        "兩個系統在 14 個 benchmark 測試案例上進行評估，涵蓋單一公司查詢（中文 / 英文 / 混合）、"
        "跨公司比較、細節擷取及陷阱問題。LLM（Claude Sonnet）與嵌入模型"
        "（paraphrase-multilingual-MiniLM-L12-v2）保持不變。chunk_size=2000、k=5。",
        body
    ))

    eval_data = [
        ['測試案例', 'LangGraph', 'LangChain', '類別'],
        ['A: Apple 營收（中文）', 'PASS', 'FAIL', '單一公司'],
        ['B: Tesla R&D（中文）', 'FAIL', 'FAIL', '單一公司'],
        ['D: Apple 服務成本（中文）', 'PASS', 'FAIL', '細節'],
        ['E: Tesla 能源營收（中文）', 'FAIL', 'FAIL', '細節'],
        ['G: 未知資訊（中文）', 'PASS', 'PASS', '陷阱'],
        ['A1: Apple 營收（英文）', 'PASS', 'FAIL', '單一公司'],
        ['A2: Tesla 汽車營收（英文）', 'FAIL', 'FAIL', '單一公司'],
        ['B1: Apple R&D（混合）', 'PASS', 'PASS', '單一公司'],
        ['B2: Tesla 資本支出（混合）', 'FAIL', 'FAIL', '單一公司'],
        ['C1: R&D 比較（英文）', 'FAIL', 'FAIL', '比較'],
        ['C2: 毛利率比較（英文）', 'PASS', 'FAIL', '比較'],
        ['D1: Apple 服務成本（英文）', 'PASS', 'PASS', '細節'],
        ['E1: 2025 預測（混合）', 'PASS', 'PASS', '陷阱'],
        ['F1: CEO 身份（英文）', 'PASS', 'PASS', '細節'],
        ['合計', '9/14 (64%)', '5/14 (36%)', ''],
    ]

    table = Table(eval_data, colWidths=[170, 65, 65, 65])
    ts = make_table_style()
    ts.add('BACKGROUND', (0, -1), (-1, -1), HexColor('#ecf0f1'))
    table.setStyle(ts)
    story.append(table)
    story.append(Paragraph("表 1：Benchmark 結果 — LangGraph vs. LangChain ReAct Agent", caption_style))

    story.append(Paragraph("3.2 架構比較", h2))

    arch_data = [
        ['面向', 'LangChain ReAct', 'LangGraph'],
        ['執行模型', '線性迴圈 +\n字串解析', 'DAG + 型別化狀態\n+ 條件邊'],
        ['狀態管理', 'agent_scratchpad\n（扁平字串）', 'TypedDict\n（結構化欄位）'],
        ['錯誤恢復', 'handle_parsing_errors\n（重試同一步驟）', '條件路由至\nrewrite_node'],
        ['路由方式', 'LLM 每步決定\n呼叫哪個工具', '專用路由節點\n+ JSON 輸出'],
        ['品質控制', '無內建機制\n依賴 prompt', '明確的 grader 節點\n過濾不相關文件'],
        ['最大迭代', '5（硬限制）', '2 次重試 + 生成\n（優雅降級）'],
        ['可觀測性', 'verbose=True\n（文字日誌）', '每節點彩色\n狀態輸出'],
        ['可擴展性', '新增工具到列表', '新增節點與邊\n到圖中'],
    ]

    arch_table = Table(arch_data, colWidths=[80, 155, 155])
    ats = make_table_style('#1a5276')
    ats.add('BACKGROUND', (0, 1), (0, -1), HexColor('#eaf2f8'))
    arch_table.setStyle(ats)
    story.append(arch_table)
    story.append(Paragraph("表 2：架構比較", caption_style))

    story.append(Paragraph("3.3 效能差異分析", h2))
    story.append(Paragraph(
        "<b>LangGraph 為何比 LangChain 高出 80%（9 vs 5）：</b>",
        body
    ))
    story.append(Paragraph(
        "<b>1. 智慧路由消除交叉污染：</b>LangGraph 的專用路由節點在檢索前先分類每個查詢，"
        "確保僅關於 Apple 的問題不會檢索到 Tesla 的文件。ReAct Agent 則依賴 LLM 在每次迭代中"
        "選擇正確的工具，有時會先搜尋錯誤的來源，或在比較題中只搜尋單一來源。",
        body
    ))
    story.append(Paragraph(
        "<b>2. 透過 Grader-Rewrite 迴圈進行自我修正：</b>當檢索返回不相關文件時，"
        "評分器偵測到這一點並觸發查詢改寫，使用更精確的財務術語重新搜尋。"
        "ReAct Agent 缺乏此回饋機制——若首次檢索失敗，它只能以相同的模糊查詢重試，"
        "或在達到 max_iterations 後放棄。",
        body
    ))
    story.append(Paragraph(
        "<b>3. 結構化狀態防止資訊遺失：</b>LangGraph 的 TypedDict 狀態在各節點間保存"
        "原始問題、檢索文件與搜尋次數。ReAct Agent 使用扁平字串（agent_scratchpad），"
        "當多次迭代累積後可能變得冗長，使 LLM 混淆。",
        body
    ))
    story.append(Paragraph(
        "<b>4. 比較查詢受益最大：</b>LangGraph 將「both」查詢路由到同時從 Apple 和 Tesla 檢索，"
        "而 ReAct Agent 必須依序呼叫兩個工具並合併結果，"
        "有時無法呼叫第二個工具或耗盡迭代次數。",
        body
    ))

    story.append(Paragraph("3.4 延遲比較", h2))
    story.append(Paragraph(
        "LangGraph 簡單查詢平均約 <b>10 秒</b>，陷阱問題約 <b>20 秒</b>（因改寫重試）。"
        "ReAct Agent 簡單查詢同樣約 <b>10 秒</b>，但比較查詢需 <b>45-56 秒</b>"
        "（C1: 44s、C2: 56s），因多次工具呼叫迭代。"
        "LangGraph 對「both」查詢的並行檢索明顯比 ReAct 的循序工具呼叫更高效。",
        body
    ))

    story.append(PageBreak())

    # ================================================================
    # 4. Embedding 模型比較（20 分）
    # ================================================================
    story.append(Paragraph("4. Embedding 模型比較", h1))

    story.append(Paragraph(
        "針對 5 個財務查詢評估了三種 sentence-transformer 嵌入模型的檢索準確度，"
        "chunk_size 固定為 2000。三個模型皆成功檢索到正確的財務數字，"
        "但在計算成本與檢索細節上有顯著差異。",
        body
    ))

    emb_data = [
        ['模型', '維度', '命中', '建構 (s)', '查詢 (s)', '備註'],
        ['paraphrase-multilingual-\nMiniLM-L12-v2', '384', '5/5', '9.13', '0.20', '多語言支援\n速度與品質平衡'],
        ['all-MiniLM-L6-v2', '384', '5/5', '13.27', '0.27', '英文最佳化\n找到更多關鍵詞'],
        ['all-mpnet-base-v2', '768', '5/5', '50.30', '1.70', '品質最高\n建構慢 5.5 倍'],
    ]
    emb_table = Table(emb_data, colWidths=[95, 40, 35, 50, 50, 105])
    emb_table.setStyle(make_table_style('#1a5276'))
    story.append(emb_table)
    story.append(Paragraph("表 3：Embedding 模型效能比較（chunk_size=2000、k=5）", caption_style))

    story.append(Paragraph("4.1 關鍵觀察", h2))
    story.append(Paragraph(
        "<b>1. 在 chunk_size=2000 下所有模型皆達到完美檢索：</b>"
        "在足夠大的分塊下，即使是最小的模型（MiniLM-L6-v2，僅 6 層）也能檢索到正確的財務表格。"
        "這表明對於結構化財務文件，<b>分塊大小比嵌入品質更重要</b>。",
        body
    ))
    story.append(Paragraph(
        "<b>2. 多語言模型同樣能處理中文查詢：</b>paraphrase-multilingual-MiniLM-L12-v2 "
        "能將中文輸入查詢與英文財務文件內容進行匹配，這對我們的雙語測試集至關重要。"
        "純英文模型（all-MiniLM-L6-v2 和 all-mpnet-base-v2）仍然可用，"
        "因為財務術語（數字、公司名稱）本身與語言無關。",
        body
    ))
    story.append(Paragraph(
        "<b>3. mpnet-base-v2 邊際效益遞減：</b>儘管擁有 768 維（MiniLM 為 384 維）"
        "且在 STS 基準上分數更高，但 mpnet 模型建構慢 5.5 倍、查詢慢 8.5 倍，"
        "在此用例中檢索準確度卻無可衡量的提升。384 維的 MiniLM 模型已足以應對財務文件檢索。",
        body
    ))
    story.append(Paragraph(
        "<b>4. 推薦選擇：paraphrase-multilingual-MiniLM-L12-v2</b> ——"
        "在多語言支援、速度與檢索品質之間取得最佳平衡。",
        body
    ))

    story.append(PageBreak())

    # ================================================================
    # 5. Chunk Size 權衡分析（20 分）
    # ================================================================
    story.append(Paragraph("5. Chunk Size 權衡分析", h1))

    story.append(Paragraph(
        "我們系統性地將 chunk_size 從 500 調整至 4000（chunk_overlap 固定為 200），"
        "以理解「Context Precision（上下文精確度）」與「Context Completeness（上下文完整度）」"
        "之間的權衡關係。",
        body
    ))

    chunk_data = [
        ['chunk_size', 'Apple\n分塊數', 'Tesla\n分塊數', '命中', '平均文件\n長度', '建構 (s)'],
        ['500', '25', '1,553', '3/5', '487', '12.33'],
        ['1,000', '11', '628', '4/5', '938', '8.32'],
        ['2,000', '5', '318', '5/5', '1,621', '5.18'],
        ['4,000', '4', '192', '5/5', '2,254', '5.19'],
    ]
    chunk_table = Table(chunk_data, colWidths=[60, 55, 55, 40, 65, 55])
    chunk_table.setStyle(make_table_style('#1a5276'))
    story.append(chunk_table)
    story.append(Paragraph("表 4：Chunk Size 對檢索效能的影響", caption_style))

    story.append(Paragraph("5.1 Context Precision vs. Context Completeness", h2))
    story.append(Paragraph(
        "<b>Context Precision（小分塊，如 500）：</b>"
        "每個分塊高度集中於單一主題或段落，這提升了語義搜尋的相關性——檢索到的分塊精確對應查詢主題。"
        "然而，財務表格（如資產負債表、現金流量表）跨越數百個字元。"
        "小分塊會將這些表格拆散，失去各項目之間的關聯性。"
        "結果：3/5 命中——Tesla 的 R&amp;D 和 CapEx 資料被切碎散佈在多個分塊中，"
        "沒有任何單一分塊包含完整的行與正確年份的數字。",
        body
    ))
    story.append(Paragraph(
        "<b>Context Completeness（大分塊，如 2000-4000）：</b>"
        "每個分塊涵蓋完整的表格或區段，保留了財務報表的結構，"
        "使同一項目的所有年度資料保持在一起。"
        "權衡是每個分塊中可能包含較多不相關的資訊。"
        "結果：5/5 命中——完整的財務表格被完整檢索，LLM 能找到確切數字。",
        body
    ))

    story.append(Paragraph("5.2 最佳選擇：chunk_size=2000", h2))
    story.append(Paragraph(
        "我們的實驗顯示 <b>chunk_size=2000</b> 是財務文件 RAG 的最佳設定：",
        body
    ))
    story.append(Paragraph(
        "<b>1. 檢索準確度在 2000 時達到高原：</b>"
        "從 2000 增加到 4000 不會帶來額外的檢索命中，"
        "但平均文件長度增加 39%（1,621→2,254 字元），為 LLM 上下文增添噪音。",
        body
    ))
    story.append(Paragraph(
        "<b>2. 財務表格恰好適配 2000 字元：</b>"
        "損益表、資產負債表區段和現金流量表區段在文字清洗後通常跨越 1,500-2,000 字元。"
        "chunk_size=2000 能完整捕捉這些表格而不會有過多填充。",
        body
    ))
    story.append(Paragraph(
        "<b>3. 分塊數量維持可管理：</b>"
        "Apple 僅有 5 個分塊（4 頁精簡財報），Tesla 有 318 個分塊（144 頁）。"
        "更大的分塊會進一步減少 Tesla 的數量，但可能混合不同財務報表區段。",
        body
    ))
    story.append(Paragraph(
        "<b>4. 建構時間最小化：</b>"
        "較少的分塊（Tesla: 318 vs 1,553）意味著更快的嵌入計算和更小的向量資料庫。"
        "建構時間從 12.33 秒（chunk_size=500）降至 5.18 秒（chunk_size=2000）。",
        body
    ))

    story.append(Paragraph("5.3 對大型表格問題的影響", h2))
    story.append(Paragraph(
        "資產負債表和現金流量表查詢對分塊大小最為敏感。這些表格包含數十個項目與多年資料。"
        "在 chunk_size=500 時，現金流量表被切成約 6-10 個片段，"
        "檢索器可能返回包含相關文字（如營運活動）但不含特定項目（資本支出）的片段。"
        "在 chunk_size=2000 時，整個現金流量表區段通常被涵蓋在 1-2 個分塊中，"
        "確保 LLM 擁有任何項目查詢所需的完整資料。",
        body
    ))

    story.append(PageBreak())

    # ================================================================
    # 6. 結論
    # ================================================================
    story.append(Paragraph("6. 結論", h1))
    story.append(Paragraph(
        "本作業展示了 LangGraph 相較於 LangChain ReAct Agent 在財務文件 RAG 系統中的顯著優勢：",
        body
    ))
    story.append(Paragraph(
        "<b>1.</b> LangGraph 的狀態機架構提供了 <b>80% 更高的準確度</b>（9/14 vs 5/14），"
        "透過智慧路由、相關性評分和查詢改寫——這些功能在 ReAct 的扁平 prompt 方法中難以實現。",
        body
    ))
    story.append(Paragraph(
        "<b>2.</b> 嵌入模型的選擇對財務文件檢索的影響<b>小於分塊大小</b>。"
        "三個測試模型在 chunk_size=2000 時皆達到 5/5 命中，"
        "但多語言 MiniLM-L12-v2 在速度與多語言支援之間取得最佳平衡。",
        body
    ))
    story.append(Paragraph(
        "<b>3.</b> chunk_size=2000 是財務 10-K 文件的<b>最佳設定</b>，"
        "在上下文完整度（保留表格結構）與上下文精確度（避免過多噪音）之間取得平衡。"
        "較小的分塊（500）無法捕捉完整的財務表格，較大的分塊（4000）增加噪音卻不提升準確度。",
        body
    ))
    story.append(Paragraph(
        "<b>4.</b> 自我修正迴圈（grade → rewrite → re-retrieve）對於處理"
        "<b>陷阱問題</b>和<b>模糊查詢</b>至關重要。LangGraph 和 LangChain 系統皆能正確識別"
        "並拒絕回答關於不可用未來資料的問題，但 LangGraph 透過結構化的評分節點更高效地完成此任務。",
        body
    ))

    doc.build(story)
    print("report.pdf generated successfully!")


if __name__ == "__main__":
    build_report()
