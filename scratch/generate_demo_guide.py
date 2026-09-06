import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas that computes total pages dynamically for footer page numbering."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#475569"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(50, 11 * inch - 36, "KAIRA CLI  |  Portfolio Demo Video Playbook & Action Guide")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.75)
            self.line(50, 11 * inch - 42, 8.5 * inch - 50, 11 * inch - 42)
            
        # Footer
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(8.5 * inch - 50, 34, page_str)
        self.drawString(50, 34, "Kaira -- Automated 5-Layer FastAPI Scaffolding CLI  |  Portfolio Video Guide")
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(50, 44, 8.5 * inch - 50, 44)
        self.restoreState()


def create_demo_guide_pdf(filename="Kaira_Demo_Video_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=50,
        rightMargin=50,
        topMargin=48,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Color Palette
    primary_color = colors.HexColor("#0F172A")    # Deep Slate
    accent_blue = colors.HexColor("#1D4ED8")      # Royal Blue
    accent_indigo = colors.HexColor("#4338CA")    # Indigo
    accent_teal = colors.HexColor("#0D9488")      # Teal
    dark_gray = colors.HexColor("#334155")        # Slate 700
    light_bg = colors.HexColor("#F8FAFC")         # Slate 50
    card_bg = colors.HexColor("#F1F5F9")          # Slate 100
    border_color = colors.HexColor("#CBD5E1")     # Slate 300
    code_bg = colors.HexColor("#0F172A")          # Dark Terminal
    code_text = colors.HexColor("#38BDF8")        # Cyan

    # Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=primary_color,
        spaceAfter=2
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=8
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=16,
        textColor=accent_blue,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=primary_color,
        spaceBefore=5,
        spaceAfter=2,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=dark_gray,
        spaceAfter=4
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=dark_gray,
        leftIndent=10,
        spaceAfter=3
    )

    code_block_style = ParagraphStyle(
        'CodeBlock',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#E2E8F0")
    )

    callout_text = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1E293B")
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=dark_gray
    )

    story = []

    # =========================================================================
    # PAGE 1: HEADER, OVERVIEW, TIMELINE TABLE, STEP 1 & STEP 2
    # =========================================================================
    story.append(Paragraph("KAIRA CLI -- Portfolio Demo Video Guide", title_style))
    story.append(Paragraph("Essential Commands, Step-by-Step Recording Flow, and Spoken Script for Maximum Impact", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=accent_blue, spaceBefore=0, spaceAfter=6))

    # Executive Overview Box
    overview_html = (
        "<b>Executive Summary &amp; Goal:</b> Create a concise <b>2.0 to 2.5-minute</b> showcase video demonstrating "
        "how Kaira transforms tedious FastAPI boilerplate into clean, production-ready 5-layer architecture in seconds. "
        "Focus <b>strictly on the essentials</b>: initialization, 5-layer pipeline generation, model relationships, "
        "zero-config migrations, and instant live Swagger API testing."
    )
    overview_box = Table([[Paragraph(overview_html, callout_text)]], colWidths=[512])
    overview_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('BORDER', (0,0), (-1,-1), 1, colors.HexColor("#93C5FD")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(overview_box)
    story.append(Spacer(1, 6))

    # Section 1: Video Timeline Table
    story.append(Paragraph("1. High-Impact Video Timeline &amp; Structure (2:30 Total)", h1_style))
    timeline_data = [
        [
            Paragraph("Timestamp", table_header_style),
            Paragraph("Demo Stage", table_header_style),
            Paragraph("Key Action &amp; Command", table_header_style),
            Paragraph("Visual Focus", table_header_style)
        ],
        [
            Paragraph("<b>0:00 - 0:20</b>", table_cell_style),
            Paragraph("<b>Hook &amp; Problem</b>", table_cell_style),
            Paragraph("FastAPI boilerplate friction -&gt; Introduce Kaira CLI", table_cell_style),
            Paragraph("Terminal title / clean workspace", table_cell_style)
        ],
        [
            Paragraph("<b>0:20 - 0:50</b>", table_cell_style),
            Paragraph("<b>1. Init Project</b>", table_cell_style),
            Paragraph("<code>kaira init blog_api --db sqlite --auth jwt</code>", table_cell_style),
            Paragraph("5-layer project structure generated", table_cell_style)
        ],
        [
            Paragraph("<b>0:50 - 1:25</b>", table_cell_style),
            Paragraph("<b>2. Generate 5-Layers</b>", table_cell_style),
            Paragraph("<code>kaira generate model User --fields \"...\"</code><br/><code>kaira generate model Post --fields \"...\"</code>", table_cell_style),
            Paragraph("Model, Repo, Schema, Service, Router", table_cell_style)
        ],
        [
            Paragraph("<b>1:25 - 1:50</b>", table_cell_style),
            Paragraph("<b>3. Relate &amp; Migrate</b>", table_cell_style),
            Paragraph("<code>kaira add relation Post --has-many Comment</code><br/><code>kaira migrate make &amp; run</code>", table_cell_style),
            Paragraph("Zero-config Alembic migrations applied", table_cell_style)
        ],
        [
            Paragraph("<b>1:50 - 2:20</b>", table_cell_style),
            Paragraph("<b>4. Live Swagger Test</b>", table_cell_style),
            Paragraph("<code>uvicorn main:app --reload</code> -&gt; <code>/docs</code>", table_cell_style),
            Paragraph("Browser side-by-side: Create User / Posts", table_cell_style)
        ],
        [
            Paragraph("<b>2:20 - 2:40</b>", table_cell_style),
            Paragraph("<b>5. Pro Diagnostic &amp; Outro</b>", table_cell_style),
            Paragraph("<code>kaira db info</code> / <code>kaira api export</code> -&gt; GitHub outro", table_cell_style),
            Paragraph("Terminal stats + GitHub repo link", table_cell_style)
        ]
    ]

    t_timeline = Table(timeline_data, colWidths=[65, 95, 212, 140])
    t_timeline.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 4),
        ('GRID', (0,0), (-1,-1), 0.5, border_color),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, light_bg]),
    ]))
    story.append(t_timeline)
    story.append(Spacer(1, 6))

    # Section 2 (Part 1): Step 1 & Step 2
    story.append(Paragraph("2. Step-by-Step Command Playbook (Part 1)", h1_style))

    # Step 1
    s1 = [
        Paragraph("<b>STEP 1: Initialize a Production FastAPI Project with JWT &amp; SQLite</b>", h2_style),
        Paragraph("Showcases instant scaffolding of architecture, async database session, JWT auth endpoints, and security middleware.", body_style),
        Table([[Paragraph("kaira init blog_api --db sqlite --auth jwt<br/>cd blog_api", code_block_style)]], colWidths=[512],
              style=[('BACKGROUND', (0,0), (-1,-1), code_bg), ('PADDING', (0,0), (-1,-1), 5)]),
        Spacer(1, 2),
        Paragraph("<b>On-Screen Callout:</b> Point out <code>core/database.py</code>, <code>middleware/security.py</code>, and <code>routers/auth.py</code> in VS Code.", callout_text),
        Spacer(1, 4)
    ]
    story.append(KeepTogether(s1))

    # Step 2
    s2 = [
        Paragraph("<b>STEP 2: Generate Full 5-Layer Pipelines (User &amp; Post)</b>", h2_style),
        Paragraph("In two fast commands, create 10 production files covering models, schemas, repositories, services, and routers.", body_style),
        Table([[Paragraph("kaira generate model User --fields \"username:str, email:str, is_active:bool\"<br/>kaira generate model Post --fields \"title:str, content:str, published:bool\"", code_block_style)]], colWidths=[512],
              style=[('BACKGROUND', (0,0), (-1,-1), code_bg), ('PADDING', (0,0), (-1,-1), 5)]),
        Spacer(1, 2),
        Paragraph("<b>On-Screen Callout:</b> Highlight <code>routers/user_router.py</code> with dependency injection and <code>services/user_service.py</code> business logic.", callout_text)
    ]
    story.append(KeepTogether(s2))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: PLAYBOOK (PART 2: STEPS 3-5) & FULL SPOKEN SCRIPT
    # =========================================================================
    story.append(Paragraph("2. Step-by-Step Command Playbook (Part 2)", h1_style))

    # Step 3
    s3 = [
        Paragraph("<b>STEP 3: Add Relationships &amp; Zero-Config Database Migrations</b>", h2_style),
        Paragraph("Demonstrate AST-powered relationship wiring, followed by automatic Alembic migration creation and execution.", body_style),
        Table([[Paragraph("kaira generate model Comment --fields \"content:str, author_name:str\"<br/>kaira add relation Post --has-many Comment --cascade \"all, delete-orphan\"<br/>kaira migrate make \"initial schema\"<br/>kaira migrate run", code_block_style)]], colWidths=[512],
              style=[('BACKGROUND', (0,0), (-1,-1), code_bg), ('PADDING', (0,0), (-1,-1), 5)]),
        Spacer(1, 2),
        Paragraph("<b>On-Screen Callout:</b> Emphasize zero manual Alembic setup needed -- tables are created in SQLite instantly.", callout_text),
        Spacer(1, 4)
    ]
    story.append(KeepTogether(s3))

    # Step 4 & 5
    s4 = [
        Paragraph("<b>STEP 4: Run Live Server &amp; Test Interactive Swagger UI</b>", h2_style),
        Paragraph("Boot the FastAPI dev server and demonstrate working CRUD endpoints directly in the interactive documentation.", body_style),
        Table([[Paragraph("uvicorn main:app --reload<br/># Open browser at http://127.0.0.1:8000/docs", code_block_style)]], colWidths=[512],
              style=[('BACKGROUND', (0,0), (-1,-1), code_bg), ('PADDING', (0,0), (-1,-1), 5)]),
        Spacer(1, 2),
        Paragraph("<b>On-Screen Callout:</b> Execute <code>POST /api/v1/users/</code> and <code>GET /api/v1/posts/</code> to show valid 200 OK responses.", callout_text),
        Spacer(1, 4)
    ]
    story.append(KeepTogether(s4))

    # Step 5
    s5 = [
        Paragraph("<b>STEP 5: Showcase 1 Pro CLI Feature &amp; Outro</b>", h2_style),
        Paragraph("Run a quick diagnostic or export command to demonstrate developer tooling depth before concluding.", body_style),
        Table([[Paragraph("kaira db info        # Displays active database health, tables, and column counts<br/>kaira api export     # Exports complete OpenAPI v3 specification to openapi.json", code_block_style)]], colWidths=[512],
              style=[('BACKGROUND', (0,0), (-1,-1), code_bg), ('PADDING', (0,0), (-1,-1), 5)]),
        Spacer(1, 2),
        Paragraph("<b>On-Screen Callout:</b> Show the clean ASCII table output of database schema health in the terminal.", callout_text),
        Spacer(1, 6)
    ]
    story.append(KeepTogether(s5))

    # Section 3: Spoken Voiceover Script
    story.append(Paragraph("3. Spoken Voiceover Script (Word-for-Word Guide)", h1_style))
    story.append(Paragraph("Read this alongside your screen recording or use it as concise voiceover narration (~2 minutes):", body_style))

    scripts = [
        ("0:00 - 0:20 (Hook)", "\"Building backend APIs with FastAPI is great, but writing repetitive boilerplate for models, schemas, repositories, and routes consumes hours. That's why I built <b>Kaira</b> -- an automated CLI that scaffolds full production-grade, 5-layer FastAPI backends in seconds.\""),
        ("0:20 - 0:50 (Init)", "\"Let's start by initializing a project: <code>kaira init blog_api --db sqlite --auth jwt</code>. In one command, Kaira sets up async database sessions, JWT auth endpoints, SlowAPI rate limiting, Loguru logging, and security middleware in a clean 5-layer layout.\""),
        ("0:50 - 1:25 (Generate)", "\"Now let's create our entities. Running <code>kaira generate model User</code> and <code>Post</code> automatically generates typed SQLAlchemy models, Pydantic v2 validation schemas, CRUD repositories, business logic services, and FastAPI routers with dependency injection.\""),
        ("1:25 - 1:50 (Relate & Migrate)", "\"Connecting models is effortless: <code>kaira add relation Post --has-many Comment</code> injects the ORM relationship. Then with zero Alembic configuration, <code>kaira migrate make</code> and <code>kaira migrate run</code> creates and applies the database schema instantly.\""),
        ("1:50 - 2:20 (Swagger UI)", "\"Now we launch with <code>uvicorn main:app --reload</code> and head to <code>/docs</code>. Our complete CRUD endpoints and auth flow are live. Let's create a user and fetch posts -- full validation and error handling working out of the box.\""),
        ("2:20 - 2:40 (Outro)", "\"Kaira also features database diagnostics, Redis caching, and OpenAPI client generation. Check out the GitHub repository linked below to learn more. Thanks for watching!\"")
    ]

    for timing, text in scripts:
        s_box = Table([[
            Paragraph(f"<b><font color='{accent_indigo.hexval()}'>[{timing}]</font></b><br/>{text}", callout_text)
        ]], colWidths=[512])
        s_box.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), card_bg),
            ('BORDER', (0,0), (-1,-1), 0.5, border_color),
            ('PADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(s_box)
        story.append(Spacer(1, 3))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: PRE-RECORDING CHECKLIST, PRO TIPS & COMPLETE RUN SCRIPT
    # =========================================================================
    story.append(Paragraph("4. Recording Setup &amp; Portfolio Pro-Tips", h1_style))

    setup_tips = [
        "<b>Screen Layout:</b> Use a 55/45 split screen -- Dark mode Terminal on the left (55%), VS Code file explorer or Chrome Swagger UI on the right (45%).",
        "<b>Terminal Font &amp; Padding:</b> Increase terminal font size to <b>16px - 18px</b> with clean padding so text is crisp even when viewed on mobile screens.",
        "<b>Clean State Reset:</b> Before hitting record, ensure no existing <code>blog_api</code> folder exists (run <code>rm -rf blog_api</code>) so there are no file overwrite prompts.",
        "<b>Typo Prevention:</b> Keep all commands in a text scratchpad or terminal history so you can execute them fluidly without long typing pauses.",
        "<b>On-Screen Overlays:</b> Add short, bold callout titles in post-editing (e.g. <i>'5 Layers Generated in 1s'</i>, <i>'Zero-Config Migrations'</i>) for viewers watching on mute.",
        "<b>Portfolio Placement:</b> Export as a high-bitrate 1080p 60fps video, or create a 15-second looping GIF/WebM highlight for the hero header of your portfolio."
    ]

    for tip in setup_tips:
        story.append(Paragraph(f"- {tip}", bullet_style))

    story.append(Spacer(1, 6))

    # Section 5: All-in-One Copy-Paste Cheatsheet
    story.append(Paragraph("5. All-in-One Copy-Paste Command Cheatsheet", h1_style))
    story.append(Paragraph("Copy and paste these exact commands into your terminal for a smooth dry-run or live record session:", body_style))

    all_commands = (
        "# 1. Clean previous run (if any)\n"
        "rm -rf blog_api\n\n"
        "# 2. Initialize project with SQLite & JWT Auth\n"
        "kaira init blog_api --db sqlite --auth jwt\n"
        "cd blog_api\n\n"
        "# 3. Generate 5-layer pipelines for User, Post, and Comment\n"
        "kaira generate model User --fields \"username:str, email:str, is_active:bool\"\n"
        "kaira generate model Post --fields \"title:str, content:str, published:bool\"\n"
        "kaira generate model Comment --fields \"content:str, author_name:str\"\n\n"
        "# 4. Link relationships\n"
        "kaira add relation Post --has-many Comment --cascade \"all, delete-orphan\"\n\n"
        "# 5. Run zero-config database migrations\n"
        "kaira migrate make \"initial schema with blog entities\"\n"
        "kaira migrate run\n\n"
        "# 6. Inspect database structure (Optional CLI flex)\n"
        "kaira db info\n\n"
        "# 7. Launch development server & open docs\n"
        "uvicorn main:app --reload\n"
        "# Browser: http://127.0.0.1:8000/docs"
    )

    full_code_box = Table([[Paragraph(all_commands.replace("\n", "<br/>"), code_block_style)]], colWidths=[512])
    full_code_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), code_bg),
        ('PADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(full_code_box)
    story.append(Spacer(1, 8))

    # Summary Footer Box
    footer_summary = (
        "<b>Portfolio Takeaway:</b> Following this blueprint will result in an engaging, professional developer "
        "showcase that demonstrates architectural expertise, clean CLI design, and full-stack backend automation in under 3 minutes."
    )
    summary_box = Table([[Paragraph(footer_summary, callout_text)]], colWidths=[512])
    summary_box.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
        ('BORDER', (0,0), (-1,-1), 1, colors.HexColor("#86EFAC")),
        ('PADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_box)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated {filename}")

if __name__ == "__main__":
    create_demo_guide_pdf("Kaira_Demo_Video_Guide.pdf")
