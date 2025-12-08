#!/usr/bin/env python3
"""Create a PDF presentation for Coles Order Prediction workflow.

ENHANCEMENTS:
- Pain-point hooks on every slide
- Progress indicators (step X of Y)
- Time-to-value callouts
- Contrast/tension in headlines
- Scannable hierarchy
- Social proof / credibility markers
- Clear visual flow with numbered steps
"""

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.utils import ImageReader
from PIL import Image
import os

# Configuration
OUTPUT_FILE = "Coles-Order-Prediction-Claude-Skill-Guide.pdf"
PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)

# VIRAL Color Palette - High contrast, premium feel
COLES_RED = HexColor("#E01A22")
COLES_RED_DARK = HexColor("#B8132C")
NEAR_BLACK = HexColor("#0A0A0A")
DARK_GRAY = HexColor("#1A1A1A")
MID_GRAY = HexColor("#666666")
LIGHT_GRAY = HexColor("#F5F5F5")
OFF_WHITE = HexColor("#FAFAFA")
CODE_BG = HexColor("#1E1E1E")
CODE_BORDER = HexColor("#333333")
LINK_BLUE = HexColor("#3B82F6")
ACCENT_TEAL = HexColor("#14B8A6")
SUCCESS_GREEN = HexColor("#22C55E")

# TOTAL STEPS for progress indicator
TOTAL_STEPS = 4

# VIRAL Slides content with hooks, tension, and value props
slides = [
    {
        "title": "I FORGOT to Order Groceries Again!",
        "subtitle": "Work on my mistake and make my Coles orders automatically",
        "hook": "Never run out of milk at 7am again",
        "value_prop": "5-minute setup  |  Saves 2+ hours/month  |  Zero missed items",
        "is_title_slide": True,
        "image": None
    },
    {
        "step": 1,
        "step_label": "CAPTURE",
        "title": "Grab Your Invoice History",
        "hook": "Your past orders = Your shopping DNA",
        "time_estimate": "3 mins",
        "content": [
            {"type": "text", "text": "Use an AI browser agent:"},
            {"type": "url", "text": "perplexity.ai/comet"},
            {"type": "url", "text": "chatgpt.com/atlas/get-started"},
            {"type": "spacer"},
            {"type": "label", "text": "Copy this prompt:"},
            {"type": "prompt", "text": [
                "Open each invoice at",
                "coles.com.au/account/orders?status=past",
                "for the previous three months",
                "in a separate tab for me to review.",
                "Press [View Orders],",
                "then open [Download Invoice]",
                "in a separate tab."
            ]},
        ],
        "tip": "More history = Better predictions",
        "image": "01-get-invoices-via-Comet-or-Atlas.png"
    },
    {
        "step": 1,
        "step_label": "CAPTURE",
        "title": "Save Your Invoice PDFs",
        "hook": "One folder. All your data. Done.",
        "time_estimate": "1 min",
        "content": [
            {"type": "text", "text": "Create a dedicated folder:"},
            {"type": "code", "text": "/Documents/Coles-Invoices/"},
            {"type": "spacer"},
            {"type": "text", "text": "Save all downloaded PDFs here"},
            {"type": "text", "text": "The AI needs these to learn your patterns"},
        ],
        "tip": "Name format: YYYY-MM-DD-invoice.pdf",
        "image": "02-save-invoices.png"
    },
    {
        "step": 2,
        "step_label": "CONNECT",
        "title": "Enable the Prediction Engine",
        "hook": "One upload. Permanent capability.",
        "time_estimate": "30 secs",
        "content": [
            {"type": "text", "text": "Navigate to Claude settings:"},
            {"type": "url", "text": "claude.ai/settings/capabilities"},
            {"type": "spacer"},
            {"type": "text", "text": "Download the Claude skill zip:"},
            {"type": "code", "text": "github.com/evgeny-trushin/claude-skills-collection/raw/refs/heads/main/shopping/coles-invoice-"},
            {"type": "code", "text": "processor-claude-skill.zip"},
            {"type": "spacer"},
            {"type": "text", "text": "Upload the Coles skill file"},
            {"type": "text", "text": "This teaches Claude your shopping patterns"},
        ],
        "tip": "Only needs to be done once",
        "image": "03-upload-claude-skill.png"
    },
    {
        "step": 3,
        "step_label": "PREDICT",
        "title": "Generate Your Shopping Forecast",
        "hook": "From chaos to clarity in 60 seconds",
        "time_estimate": "1 min",
        "content": [
            {"type": "text", "text": "Start a new Claude chat:"},
            {"type": "url", "text": "claude.ai"},
            {"type": "spacer"},
            {"type": "label", "text": "Copy this prompt:"},
            {"type": "prompt", "text": [
                "Predict Coles orders from",
                "December 2025 to March 2026"
            ]},
            {"type": "spacer"},
            {"type": "text", "text": "Then drag-and-drop your invoice PDFs"},
        ],
        "tip": "Adjust the date range to your needs",
        "image": "04-predict-your-orders.png"
    },
    {
        "step": 3,
        "step_label": "PREDICT",
        "title": "Processing Your Patterns",
        "hook": "Claude skill is reading your shopping habits",
        "time_estimate": "~60 secs wait",
        "content": [
            {"type": "text", "text": "Claude analyses your invoices:"},
            {"type": "spacer"},
            {"type": "check", "text": "Extracts every product you bought"},
            {"type": "check", "text": "Calculates your purchase intervals"},
            {"type": "check", "text": "Identifies consumption patterns"},
            {"type": "check", "text": "Predicts when you will run out"},
        ],
        "tip": "Sit back—this runs automatically",
        "image": "05-predict-your-orders-wip.png"
    },
    {
        "step": 3,
        "step_label": "PREDICT",
        "title": "Your Shopping Forecast",
        "hook": "Never guess what you need again",
        "time_estimate": "Review: 2 mins",
        "content": [
            {"type": "text", "text": "Your prediction includes:"},
            {"type": "spacer"},
            {"type": "check", "text": "Orders grouped by optimal date"},
            {"type": "check", "text": "Estimated cost per order"},
            {"type": "check", "text": "Monthly budget forecast"},
            {"type": "check", "text": "Items ranked by urgency"},
        ],
        "tip": "Export to spreadsheet if needed",
        "image": "06-predict-your-orders-result.png"
    },
    {
        "step": 4,
        "step_label": "ORDER",
        "title": "Auto-Order with Any Browser Agent",
        "hook": "From list to cart in 30 seconds",
        "time_estimate": "30 secs",
        "content": [
            {"type": "text", "text": "Open your AI browser:"},
            {"type": "url", "text": "perplexity.ai/comet"},
            {"type": "url", "text": "chatgpt.com/atlas/get-started"},
            {"type": "spacer"},
            {"type": "label", "text": "Copy this prompt:"},
            {"type": "prompt", "text": [
                "Reorder via https://www.coles.com.au",
                "these items:",
                "[paste predicted items here]"
            ]},
        ],
        "tip": "Review cart before checkout",
        "image": "07-reorder-via-Comet-or-Atlas.png"
    },
    {
        "title": "You Are Now on Autopilot",
        "subtitle": "Repeat monthly. Never forget groceries again.",
        "is_summary_slide": True,
        "summary_points": [
            ("CAPTURE", "Download 3 months of invoices"),
            ("CONNECT", "Upload skill to Claude once"),
            ("PREDICT", "Generate your shopping forecast"),
            ("ORDER", "Auto-add items to Coles cart"),
        ],
        "cta": "By Evgeny Trushin",
        "image": None
    },
]


def draw_progress_bar(c, current_step, total_steps, y_position):
    """Draw a visual progress indicator."""
    bar_width = 200
    bar_height = 6
    x_start = PAGE_WIDTH - bar_width - 40
    
    # Background bar
    c.setFillColor(HexColor("#333333"))
    c.roundRect(x_start, y_position, bar_width, bar_height, 3, fill=True, stroke=False)
    
    # Progress fill
    progress_width = (current_step / total_steps) * bar_width
    c.setFillColor(COLES_RED)
    c.roundRect(x_start, y_position, progress_width, bar_height, 3, fill=True, stroke=False)
    
    # Step indicator text
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x_start - 10, y_position - 2, f"Step {current_step} of {total_steps}")


def draw_time_badge(c, time_text, x, y):
    """Draw a time estimate badge."""
    badge_width = 80
    badge_height = 22
    
    c.setFillColor(ACCENT_TEAL)
    c.roundRect(x, y, badge_width, badge_height, 11, fill=True, stroke=False)
    
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    text_y = y + (badge_height / 2) - 3  # vertically center the label
    c.drawCentredString(x + badge_width/2, text_y, time_text)


def draw_tip_box(c, tip_text, x, y, width):
    """Draw a pro-tip callout box (centered vertically)."""
    padding = 12
    box_height = 48
    
    # Left accent bar
    c.setFillColor(ACCENT_TEAL)
    c.rect(x, y - box_height + padding, 4, box_height - padding, fill=True, stroke=False)
    
    # Background
    c.setFillColor(HexColor("#0D3D38"))
    c.rect(x + 4, y - box_height + padding, width - 4, box_height - padding, fill=True, stroke=False)
    
    # Text, vertically centered
    text_y = y - box_height/2 + 4
    c.setFillColor(ACCENT_TEAL)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + 14, text_y, "PRO TIP:")
    c.setFillColor(white)
    c.setFont("Helvetica", 10)
    c.drawString(x + 74, text_y, tip_text)
    
    return box_height


def draw_title_slide(c, slide):
    """Draw the VIRAL title slide with hook and value prop."""
    # Dark background for premium feel
    c.setFillColor(NEAR_BLACK)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    
    # Red accent bar at top
    c.setFillColor(COLES_RED)
    c.rect(0, PAGE_HEIGHT - 8, PAGE_WIDTH, 8, fill=True, stroke=False)
    
    # Badge
    badge_text = "CLAUDE SKILL"
    c.setFillColor(COLES_RED)
    badge_width = 200
    c.roundRect(40, PAGE_HEIGHT - 80, badge_width, 32, 16, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(40 + badge_width/2, PAGE_HEIGHT - 68, badge_text)
    
    # Main hook title - highlight the full phrase
    c.setFont("Helvetica-Bold", 44)
    title = slide["title"]
    x_pos = 40
    y_pos = PAGE_HEIGHT - 180
    keyword = "I FORGOT to Order Groceries Again!"
    if keyword in title:
        pre, _, post = title.partition(keyword)
        if pre:
            c.setFillColor(white)
            c.drawString(x_pos, y_pos, pre)
            x_pos += c.stringWidth(pre, "Helvetica-Bold", 44)

        c.setFillColor(COLES_RED)
        c.drawString(x_pos, y_pos, keyword)
        x_pos += c.stringWidth(keyword, "Helvetica-Bold", 44)
        
        if post:
            c.setFillColor(white)
            c.drawString(x_pos, y_pos, post)
    else:
        c.setFillColor(white)
        c.drawString(x_pos, y_pos, title)
    
    # Subtitle
    c.setFillColor(white)
    c.setFont("Helvetica", 26)
    c.drawString(40, PAGE_HEIGHT - 240, slide["subtitle"])
    
    # Hook line with accent bar
    c.setFillColor(COLES_RED)
    c.rect(40, PAGE_HEIGHT - 290, 4, 24, fill=True, stroke=False)
    c.setFillColor(HexColor("#AAAAAA"))
    c.setFont("Helvetica", 16)
    c.drawString(54, PAGE_HEIGHT - 280, slide.get("hook", ""))
    
    # Author links (top of deck) - bold, white for contrast on dark background
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(54, PAGE_HEIGHT - 310, "LinkedIn: linkedin.com/in/evgeny-trushin/")
    c.drawString(54, PAGE_HEIGHT - 330, "GitHub: github.com/evgeny-trushin/claude-skills-collection")
    
    # Value proposition boxes moved near bottom to avoid overlap with links
    if "value_prop" in slide:
        props = slide["value_prop"].split("  |  ")
        box_width = 180
        box_height = 50
        gap = 20
        start_x = 40
        y_pos = 120
        
        for i, prop in enumerate(props):
            x = start_x + i * (box_width + gap)
            
            # Box background
            c.setFillColor(HexColor("#1A1A1A"))
            c.roundRect(x, y_pos, box_width, box_height, 8, fill=True, stroke=False)
            
            # Box border accent
            c.setStrokeColor(HexColor("#333333"))
            c.setLineWidth(1)
            c.roundRect(x, y_pos, box_width, box_height, 8, fill=False, stroke=True)
            
            # Text
            c.setFillColor(white)
            c.setFont("Helvetica-Bold", 13)
            c.drawCentredString(x + box_width/2, y_pos + 18, prop)
    
    # Footer
    c.setFillColor(HexColor("#666666"))
    c.setFont("Helvetica", 11)
    c.drawCentredString(PAGE_WIDTH/2, 30, "Evgeny Trushin")
    
    # Claude icon
    c.setFillColor(COLES_RED)
    icon_size = 36
    c.roundRect(PAGE_WIDTH - 76, 20, icon_size, icon_size, 8, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(PAGE_WIDTH - 58, 30, "C")


def draw_summary_slide(c, slide):
    """Draw the final summary/CTA slide."""
    # Dark background
    c.setFillColor(NEAR_BLACK)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)
    
    # Red accent bar
    c.setFillColor(COLES_RED)
    c.rect(0, PAGE_HEIGHT - 8, PAGE_WIDTH, 8, fill=True, stroke=False)
    
    # Title
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 44)
    c.drawCentredString(PAGE_WIDTH/2, PAGE_HEIGHT - 100, slide["title"])
    
    # Subtitle
    c.setFillColor(HexColor("#AAAAAA"))
    c.setFont("Helvetica", 22)
    c.drawCentredString(PAGE_WIDTH/2, PAGE_HEIGHT - 150, slide["subtitle"])
    
    # Summary boxes
    if "summary_points" in slide:
        box_width = 180
        box_height = 100
        gap = 20
        total_width = len(slide["summary_points"]) * box_width + (len(slide["summary_points"]) - 1) * gap
        start_x = (PAGE_WIDTH - total_width) / 2
        y_pos = PAGE_HEIGHT - 320
        
        for i, (label, text) in enumerate(slide["summary_points"]):
            x = start_x + i * (box_width + gap)
            
            # Box
            c.setFillColor(HexColor("#1A1A1A"))
            c.roundRect(x, y_pos, box_width, box_height, 8, fill=True, stroke=False)
            
            # Step number
            c.setFillColor(COLES_RED)
            c.setFont("Helvetica-Bold", 28)
            c.drawCentredString(x + box_width/2, y_pos + box_height - 35, str(i + 1))
            
            # Label
            c.setFillColor(COLES_RED)
            c.setFont("Helvetica-Bold", 11)
            c.drawCentredString(x + box_width/2, y_pos + box_height - 55, label)
            
            # Description
            c.setFillColor(white)
            c.setFont("Helvetica", 10)
            # Word wrap
            words = text.split()
            lines = []
            current_line = []
            for word in words:
                test_line = " ".join(current_line + [word])
                if c.stringWidth(test_line, "Helvetica", 10) < box_width - 20:
                    current_line.append(word)
                else:
                    lines.append(" ".join(current_line))
                    current_line = [word]
            lines.append(" ".join(current_line))
            
            for j, line in enumerate(lines):
                c.drawCentredString(x + box_width/2, y_pos + 25 - j * 12, line)
    
    # CTA button
    if "cta" in slide:
        cta_width = 280
        cta_height = 50
        cta_x = (PAGE_WIDTH - cta_width) / 2
        cta_y = 80
        
        c.setFillColor(COLES_RED)
        c.roundRect(cta_x, cta_y, cta_width, cta_height, 25, fill=True, stroke=False)
        
        c.setFillColor(white)
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(PAGE_WIDTH/2, cta_y + 16, slide["cta"])
    
    # Author link at bottom
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(PAGE_WIDTH/2, 40, "github.com/evgeny-trushin/claude-skills-collection")


def draw_prompt_box(c, lines, x, y, width):
    """Draw a dark-themed copyable prompt box."""
    padding = 14
    line_height = 18
    box_height = len(lines) * line_height + padding * 2

    # Dark box background
    c.setFillColor(CODE_BG)
    c.setStrokeColor(CODE_BORDER)
    c.setLineWidth(1)
    c.roundRect(x, y - box_height + padding, width, box_height, 6, fill=True, stroke=True)
    
    # Monospace text
    c.setFillColor(HexColor("#E0E0E0"))
    c.setFont("Courier", 11)
    text_y = y - 4
    for line in lines:
        c.drawString(x + padding, text_y, line)
        text_y -= line_height

    return box_height + 10


def draw_content_slide(c, slide, img_dir):
    """Draw a VIRAL content slide."""
    # White background
    c.setFillColor(OFF_WHITE)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=True, stroke=False)

    # Header bar - darker for contrast
    c.setFillColor(DARK_GRAY)
    c.rect(0, PAGE_HEIGHT - 90, PAGE_WIDTH, 90, fill=True, stroke=False)
    
    # Red accent line under header
    c.setFillColor(COLES_RED)
    c.rect(0, PAGE_HEIGHT - 94, PAGE_WIDTH, 4, fill=True, stroke=False)

    # Step badge with label
    step_num = slide.get("step", 1)
    step_label = slide.get("step_label", "STEP")
    
    # Step circle
    c.setFillColor(COLES_RED)
    c.circle(60, PAGE_HEIGHT - 45, 22, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(60, PAGE_HEIGHT - 52, str(step_num))
    
    # Step label
    c.setFillColor(COLES_RED)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(90, PAGE_HEIGHT - 38, step_label)

    # Title
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(90, PAGE_HEIGHT - 62, slide["title"])
    
    # Progress bar
    draw_progress_bar(c, step_num, TOTAL_STEPS, PAGE_HEIGHT - 50)
    
    # Time badge (pinned to top-right of header)
    if "time_estimate" in slide:
        draw_time_badge(c, slide["time_estimate"], PAGE_WIDTH - 120, PAGE_HEIGHT - 32)

    # Hook line below header
    if "hook" in slide:
        c.setFillColor(COLES_RED)
        c.rect(40, PAGE_HEIGHT - 125, 4, 20, fill=True, stroke=False)
        c.setFillColor(MID_GRAY)
        c.setFont("Helvetica-Oblique", 14)
        c.drawString(54, PAGE_HEIGHT - 118, slide["hook"])

    # Content area - left side
    left_margin = 40
    content_width = PAGE_WIDTH * 0.40
    y_pos = PAGE_HEIGHT - 165

    for item in slide.get("content", []):
        item_type = item.get("type", "text")
        text = item.get("text", "")

        if item_type == "prompt":
            box_height = draw_prompt_box(c, text, left_margin, y_pos, content_width)
            y_pos -= box_height
        elif item_type == "url":
            c.setFillColor(LINK_BLUE)
            c.setFont("Courier", 12)
            c.drawString(left_margin + 10, y_pos, text)
            y_pos -= 22
        elif item_type == "code":
            c.setFillColor(HexColor("#444444"))
            c.setFont("Courier", 12)
            c.drawString(left_margin + 10, y_pos, text)
            y_pos -= 22
        elif item_type == "label":
            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(left_margin, y_pos, text)
            y_pos -= 24
        elif item_type == "bullet":
            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica", 13)
            c.drawString(left_margin + 15, y_pos, "\u2022  " + text)
            y_pos -= 22
        elif item_type == "check":
            # Checkmark style
            c.setFillColor(SUCCESS_GREEN)
            c.setFont("Helvetica-Bold", 14)
            c.drawString(left_margin + 10, y_pos, "\u2713")
            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica", 13)
            c.drawString(left_margin + 30, y_pos, text)
            y_pos -= 24
        elif item_type == "spacer":
            y_pos -= 12
        else:
            c.setFillColor(DARK_GRAY)
            c.setFont("Helvetica", 13)
            c.drawString(left_margin, y_pos, text)
            y_pos -= 22

    # Pro tip box at bottom of content
    if "tip" in slide:
        draw_tip_box(c, slide["tip"], left_margin, 60, content_width)

    # Image - right side with shadow
    if slide.get("image"):
        img_path = os.path.join(img_dir, slide["image"])
        if os.path.exists(img_path):
            try:
                img = Image.open(img_path)
                img_width, img_height = img.size

                max_img_width = PAGE_WIDTH * 0.50
                max_img_height = PAGE_HEIGHT - 160

                scale = min(max_img_width / img_width, max_img_height / img_height)
                new_width = img_width * scale
                new_height = img_height * scale

                x_pos = PAGE_WIDTH - new_width - 35
                y_pos = (PAGE_HEIGHT - 94 - new_height) / 2 - 10

                # Shadow
                c.setFillColor(HexColor("#CCCCCC"))
                c.roundRect(x_pos + 4, y_pos - 4, new_width, new_height, 8, fill=True, stroke=False)
                
                # Border
                c.setFillColor(white)
                c.roundRect(x_pos - 2, y_pos - 2, new_width + 4, new_height + 4, 6, fill=True, stroke=False)

                # Image
                c.drawImage(img_path, x_pos, y_pos, width=new_width, height=new_height)
            except Exception as e:
                print(f"Error loading image {img_path}: {e}")

    # Footer
    c.setFillColor(HexColor("#AAAAAA"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(PAGE_WIDTH/2, 15, "Coles Claude Skill  |  by Evgeny Trushin")


def create_presentation():
    """Create the VIRAL PDF presentation."""
    img_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(img_dir, OUTPUT_FILE)

    c = canvas.Canvas(output_path, pagesize=landscape(A4))

    for i, slide in enumerate(slides):
        if slide.get("is_title_slide"):
            draw_title_slide(c, slide)
        elif slide.get("is_summary_slide"):
            draw_summary_slide(c, slide)
        else:
            draw_content_slide(c, slide, img_dir)

        if i < len(slides) - 1:
            c.showPage()

    c.save()
    print(f"Created: {output_path}")
    print(f"\nVIRAL ENHANCEMENTS APPLIED:")
    print("  - Pain-point hook on title slide")
    print("  - Progress indicators (Step X of Y)")
    print("  - Time-to-value badges")
    print("  - PRO TIP callouts for retention")
    print("  - Checkmark lists for completion feel")
    print("  - Summary slide with 4-step recap")
    print("  - CTA button for action")


if __name__ == "__main__":
    create_presentation()
