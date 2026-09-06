import os
from PIL import Image, ImageDraw, ImageFont

def generate_kaira_terminal_gif(output_path="kaira_demo.gif"):
    # GIF Canvas Dimensions
    width, height = 820, 520
    
    # Fonts
    font_path = "C:/Windows/Fonts/consola.ttf"
    font_bold_path = "C:/Windows/Fonts/consolab.ttf"
    if not os.path.exists(font_bold_path):
        font_bold_path = font_path

    font_code = ImageFont.truetype(font_path, 15)
    font_bold = ImageFont.truetype(font_bold_path, 15)
    font_title = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)

    # Color Palette (Dark Modern Developer Theme)
    bg_color = (15, 23, 42)          # Canvas bg #0F172A
    term_bg = (13, 17, 23)           # Terminal window #0D1117
    term_border = (48, 54, 61)       # Border #30363D
    titlebar_bg = (22, 27, 34)       # Titlebar #161B22
    title_text = (139, 148, 158)     # Title text #8B949E
    
    # Terminal text colors
    c_prompt_user = (56, 189, 248)   # Sky 400
    c_prompt_path = (168, 85, 247)   # Purple 500
    c_command = (248, 250, 252)      # White
    c_text_muted = (148, 163, 184)   # Slate 400
    c_success = (34, 197, 94)        # Green 500
    c_info = (59, 130, 246)          # Blue 500
    c_accent = (245, 158, 11)        # Amber 500
    c_cyan = (6, 182, 212)           # Cyan 500

    def draw_terminal_base():
        img = Image.new("RGBA", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Terminal outer box
        t_left, t_top, t_right, t_bottom = 20, 20, width - 20, height - 20
        draw.rounded_rectangle([t_left, t_top, t_right, t_bottom], radius=10, fill=term_bg, outline=term_border, width=1)

        # Title bar
        draw.rounded_rectangle([t_left, t_top, t_right, t_top + 36], radius=10, fill=titlebar_bg)
        draw.rectangle([t_left, t_top + 26, t_right, t_top + 36], fill=titlebar_bg) # Flatten bottom radius
        draw.line([t_left, t_top + 36, t_right, t_top + 36], fill=term_border, width=1)

        # Window controls (macOS style dots)
        draw.ellipse([t_left + 14, t_top + 13, t_left + 24, t_top + 23], fill=(255, 95, 86))    # Close (Red)
        draw.ellipse([t_left + 30, t_top + 13, t_left + 40, t_top + 23], fill=(255, 189, 46))   # Minimize (Yellow)
        draw.ellipse([t_left + 46, t_top + 13, t_left + 56, t_top + 23], fill=(39, 201, 63))    # Expand (Green)

        # Title text
        title_str = "kaira-cli  |  devflow@workspace"
        draw.text((width // 2 - 80, t_top + 10), title_str, fill=title_text, font=font_title)

        return img

    base_frame = draw_terminal_base()

    # Timeline / Script of terminal events
    # Each event: list of line objects to draw in sequence
    # Line object: list of (text, color, is_bold)
    timeline_states = []

    # Sequence of commands to simulate
    # 1. Prompt 1 typed
    cmd1 = "kaira init blog_api --db sqlite --auth jwt"
    # 2. Output 1
    # 3. Prompt 2 typed
    cmd2 = 'kaira generate model User --fields "username:str, email:str"'
    # 4. Output 2
    # 5. Prompt 3 typed
    cmd3 = 'kaira migrate make "init" && kaira migrate run'
    # 6. Output 3
    # 7. Prompt 4 typed
    cmd4 = "uvicorn main:app --reload"
    # 8. Server output

    lines_history = []

    def prompt_prefix():
        return [
            ("devflow", c_prompt_user, True),
            (":", c_text_muted, False),
            ("~/blog_api", c_prompt_path, True),
            ("$ ", c_text_muted, False)
        ]

    # Frame generation helper
    frames = []
    frame_durations = []

    def render_current_screen(current_lines, cursor=True):
        img = base_frame.copy()
        draw = ImageDraw.Draw(img)
        
        start_x = 40
        start_y = 70
        line_height = 22

        for i, line in enumerate(current_lines):
            cur_x = start_x
            y = start_y + (i * line_height)
            for segment in line:
                text, color, is_bold = segment
                f = font_bold if is_bold else font_code
                draw.text((cur_x, y), text, fill=color, font=f)
                # Calculate width
                bbox = draw.textbbox((cur_x, y), text, font=f)
                cur_x = bbox[2] + 1
            
            # Cursor at the end of last line if active
            if cursor and i == len(current_lines) - 1:
                draw.rectangle([cur_x + 2, y + 2, cur_x + 10, y + 17], fill=(248, 250, 252))

        return img.convert("P", palette=Image.ADAPTIVE)

    # === FRAME GENERATION ===

    # Initial empty prompt with blinking cursor (2 blinks)
    cur_lines = [prompt_prefix() + [("", c_command, True)]]
    for _ in range(2):
        frames.append(render_current_screen(cur_lines, cursor=True))
        frame_durations.append(400)
        frames.append(render_current_screen(cur_lines, cursor=False))
        frame_durations.append(300)

    # 1. Type CMD 1
    for step in range(1, len(cmd1) + 1, 3):
        typed = cmd1[:step]
        cur_lines = [prompt_prefix() + [(typed, c_command, True)]]
        frames.append(render_current_screen(cur_lines, cursor=True))
        frame_durations.append(70)

    cur_lines = [prompt_prefix() + [(cmd1, c_command, True)]]
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(350)

    # Output for CMD 1 (Init)
    cur_lines.append([("[KAIRA] ", c_accent, True), ("Scaffolding FastAPI project 'blog_api'...", c_text_muted, False)])
    cur_lines.append([("  + ", c_success, True), ("Created 5-layer architecture (core, models, repos, services, routers)", (226, 232, 240), False)])
    cur_lines.append([("  + ", c_success, True), ("Wired JWT Authentication & SlowAPI Rate Limiting", (226, 232, 240), False)])
    cur_lines.append([("  + ", c_success, True), ("Configured SQLite async engine (aiosqlite)", (226, 232, 240), False)])
    cur_lines.append([("[SUCCESS] ", c_success, True), ("Project ready! cd blog_api", c_cyan, True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(1200)

    # 2. Type CMD 2 (Generate User)
    for step in range(1, len(cmd2) + 1, 4):
        typed = cmd2[:step]
        temp_lines = cur_lines + [prompt_prefix() + [(typed, c_command, True)]]
        frames.append(render_current_screen(temp_lines, cursor=True))
        frame_durations.append(60)

    cur_lines.append(prompt_prefix() + [(cmd2, c_command, True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(300)

    # Output for CMD 2 (Generate 5 layers)
    cur_lines.append([("[GENERATE] ", c_info, True), ("Building complete 5-layer pipeline for 'User'...", c_text_muted, False)])
    cur_lines.append([("  [1/5] ", c_accent, True), ("models/user.py ", c_cyan, False), ("(SQLAlchemy ORM)", c_text_muted, False)])
    cur_lines.append([("  [2/5] ", c_accent, True), ("repositories/user_repository.py ", c_cyan, False), ("(Async CRUD)", c_text_muted, False)])
    cur_lines.append([("  [3/5] ", c_accent, True), ("schemas/user_schema.py ", c_cyan, False), ("(Pydantic v2)", c_text_muted, False)])
    cur_lines.append([("  [4/5] ", c_accent, True), ("services/user_service.py ", c_cyan, False), ("(Business Logic)", c_text_muted, False)])
    cur_lines.append([("  [5/5] ", c_accent, True), ("routers/user_router.py ", c_cyan, False), ("(REST Endpoints)", c_text_muted, False)])
    cur_lines.append([("[SUCCESS] ", c_success, True), ("5 layers generated & registered in main.py", (248, 250, 252), True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(1500)

    # Clear top lines to simulate terminal scrolling
    cur_lines = cur_lines[7:] # Keep recent output

    # 3. Type CMD 3 (Migrate)
    for step in range(1, len(cmd3) + 1, 4):
        typed = cmd3[:step]
        temp_lines = cur_lines + [prompt_prefix() + [(typed, c_command, True)]]
        frames.append(render_current_screen(temp_lines, cursor=True))
        frame_durations.append(60)

    cur_lines.append(prompt_prefix() + [(cmd3, c_command, True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(300)

    cur_lines.append([("[MIGRATE] ", c_info, True), ("Auto-generating Alembic revision...", c_text_muted, False)])
    cur_lines.append([("  * ", c_success, True), ("Generated revision 8f2a1d_init.py", c_cyan, False)])
    cur_lines.append([("  * ", c_success, True), ("Running upgrade head -> Target: 'users' table created", (226, 232, 240), False)])
    cur_lines.append([("[SUCCESS] ", c_success, True), ("Database schema up to date.", c_success, True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(1200)

    # 4. Type CMD 4 (Uvicorn Start)
    cur_lines = cur_lines[5:] # Keep clean
    for step in range(1, len(cmd4) + 1, 3):
        typed = cmd4[:step]
        temp_lines = cur_lines + [prompt_prefix() + [(typed, c_command, True)]]
        frames.append(render_current_screen(temp_lines, cursor=True))
        frame_durations.append(70)

    cur_lines.append(prompt_prefix() + [(cmd4, c_command, True)])
    frames.append(render_current_screen(cur_lines, cursor=False))
    frame_durations.append(400)

    cur_lines.append([("INFO:     ", c_success, True), ("Uvicorn running on ", c_text_muted, False), ("http://127.0.0.1:8000", c_cyan, True)])
    cur_lines.append([("INFO:     ", c_info, True), ("Application startup complete. Swagger docs at ", c_text_muted, False), ("/docs", c_accent, True)])
    cur_lines.append([("INFO:     ", c_info, True), ("Router registered: ", c_text_muted, False), ("GET/POST/PUT/DELETE  /api/v1/users/", c_success, True)])
    cur_lines.append([("⚡ KAIRA:  ", c_accent, True), ("Zero boilerplate. Full production architecture ready.", (248, 250, 252), True)])
    
    # Hold final frame
    final_frame = render_current_screen(cur_lines, cursor=True)
    frames.append(final_frame)
    frame_durations.append(3000)

    # Save animated GIF
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=frame_durations,
        loop=0,
        optimize=True
    )
    print(f"Successfully generated animated demo GIF at {output_path} (Frames: {len(frames)})")

if __name__ == "__main__":
    generate_kaira_terminal_gif("kaira_demo.gif")
