"""Недельный отчёт команды 2: reports/weekly/src/<неделя>.md → reports/weekly/SunCount_nedelya_<неделя>.docx.

Текст отчёта правится в markdown-источнике, docx пересобирается этим скриптом. Без аргументов собирает все недели.
Поддерживаемая разметка: «# » заголовок, «## » и «### » подзаголовки, «- » пункт списка,
**жирный**, `путь` (выводится обычным текстом); строки вида «**Поле:** значение» до первого «## » — шапка.

    python scripts/make_weekly_report.py [reports/weekly/src/2026-10-26_2026-11-01.md]
"""
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reports" / "weekly" / "src"
OUT = ROOT / "reports" / "weekly"
FONT, SIZE = "Times New Roman", 14   # как в записке команды (reports/SunCount_zapiska_problema_potrebitelya.docx)


def set_font(style, size=SIZE, bold=None):
    style.font.name, style.font.size = FONT, Pt(size)
    rfonts = style.element.rPr.rFonts
    rfonts.set(qn("w:eastAsia"), FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):   # иначе заголовки берут шрифт темы
        rfonts.attrib.pop(qn(attr), None)
    if bold is not None:
        style.font.bold = bold


def add_runs(par, text):
    """**жирный** → bold, `код` → обычный текст."""
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        run = par.add_run(re.sub(r"`([^`]+)`", r"\1", part[2:-2] if bold else part))
        run.bold = bold or None


def build(md_path: Path) -> Path:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin, sec.right_margin, sec.top_margin, sec.bottom_margin = Cm(3), Cm(1.5), Cm(2), Cm(2)

    normal = doc.styles["Normal"]
    set_font(normal)
    pf = normal.paragraph_format
    pf.line_spacing, pf.space_after, pf.first_line_indent = 1.5, Pt(0), Cm(1.25)
    pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for name, size in (("Heading 1", 14), ("Heading 2", 14)):
        st = doc.styles[name]
        set_font(st, size, bold=True)
        st.font.color.rgb = None
        st.font.italic = False
        st.paragraph_format.first_line_indent = Cm(0)
        st.paragraph_format.space_before, st.paragraph_format.space_after = Pt(12), Pt(6)
        st.paragraph_format.keep_with_next = True
    bullet = doc.styles["List Bullet"]
    set_font(bullet)
    bf = bullet.paragraph_format
    bf.first_line_indent, bf.alignment = Cm(0), WD_ALIGN_PARAGRAPH.LEFT   # без растяжки пробелов в пунктах
    bf.line_spacing, bf.space_after = 1.15, Pt(4)

    lines = md_path.read_text(encoding="utf-8").splitlines()
    in_header = True
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("# "):
            p = doc.add_paragraph()
            p.alignment, p.paragraph_format.first_line_indent = WD_ALIGN_PARAGRAPH.CENTER, Cm(0)
            r = p.add_run(line[2:].upper())
            r.bold = True
            p.paragraph_format.space_after = Pt(12)
        elif line.startswith("## "):
            in_header = False
            doc.add_heading(line[3:], level=1)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=2)
        elif line.startswith("- "):
            add_runs(doc.add_paragraph(style="List Bullet"), line[2:])
        else:
            p = doc.add_paragraph()
            if in_header:   # шапка: без отступа, по левому краю, одинарный интервал
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.line_spacing = 1.0
                p.paragraph_format.space_after = Pt(4)
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            elif re.fullmatch(r"\*\*[^*]+\*\*", line):   # строка-подзаголовок блока — без отступа, не отрывать от блока
                p.paragraph_format.keep_with_next = True
                p.paragraph_format.first_line_indent = Cm(0)
                p.paragraph_format.space_before = Pt(8)
            add_runs(p, line)

    out = OUT / f"SunCount_nedelya_{md_path.stem}.docx"
    doc.save(out)
    return out


if __name__ == "__main__":
    paths = [Path(a) for a in sys.argv[1:]] or sorted(SRC.glob("*.md"))
    for path in paths:
        print(build(path).relative_to(ROOT))
