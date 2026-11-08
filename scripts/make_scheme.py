"""Схема решения SunCount (мастер-ТЗ 5.0): система поддержки принятия решений — подбор домашней станции.

По замечаниям наставника (06.11.2026): без блока экономики, без PVGIS и Streamlit как отдельных блоков; в центре —
подбор конфигурации под дом пользователя. Схема рисуется фигурами PowerPoint (python-pptx): та же функция
draw_scheme рисует её на слайде промежуточного доклада (scripts/make_interim_talk.py), поэтому схема везде одна.

Выход: reports/scheme/SunCount_scheme.pptx (схема одним слайдом, можно править и вставлять в презентации) и
reports/scheme/SunCount_scheme.png (картинка для документов; экспорт через PowerPoint, если он установлен —
иначе PNG остаётся прежним). Запуск: python scripts/make_scheme.py
"""
import subprocess
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "scheme"

BLUE = RGBColor(0x1E, 0x4E, 0x79)    # основной цвет шаблона АГУ
MID = RGBColor(0x2E, 0x75, 0xB6)
TINT = RGBColor(0xE9, 0xEF, 0xF6)
GREY_FILL = RGBColor(0xF2, 0xF2, 0xF2)
GREY_LINE = RGBColor(0xA6, 0xA6, 0xA6)
T1_FILL = RGBColor(0xFF, 0xF2, 0xCC)  # профили команды 1 — отдельным цветом
T1_LINE = RGBColor(0xBF, 0x90, 0x00)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
TEXT = RGBColor(0x26, 0x26, 0x26)
MUTED = RGBColor(0x59, 0x59, 0x59)
FONT = "Calibri"

WIDTH, HEIGHT = 10.5, 4.65   # размер схемы в дюймах при масштабе 1 (рабочее поле слайда шаблона)


class _Canvas:
    def __init__(self, slide, x0: float, y0: float, k: float):
        self.s, self.x0, self.y0, self.k = slide, x0, y0, k

    def _xywh(self, x, y, w, h):
        k = self.k
        return Inches(self.x0 + x * k), Inches(self.y0 + y * k), Inches(w * k), Inches(h * k)

    def box(self, x, y, w, h, fill, line=None, line_w=1.25, dashed=False, name="", radius=0.06):
        shp = self.s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, *self._xywh(x, y, w, h))
        shp.adjustments[0] = radius
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        if line is None:
            shp.line.fill.background()
        else:
            shp.line.color.rgb = line
            shp.line.width = Pt(line_w * self.k)
            if dashed:
                shp.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        shp.shadow.inherit = False
        shp.name = name
        return shp

    def text(self, x, y, w, h, paras, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, name=""):
        """paras: [(текст, размер, жирный, цвет, маркер-списка)]."""
        tb = self.s.shapes.add_textbox(*self._xywh(x, y, w, h))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(0.06 * self.k)
        tf.margin_top = tf.margin_bottom = Inches(0.02 * self.k)
        tf.vertical_anchor = anchor
        for i, (t, size, bold, color, bullet) in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = align
            p.space_after = Pt(3 * self.k)
            if bullet:   # маркер с висячим отступом: перенесённая строка встаёт под текст, а не под точку
                pPr = p._p.get_or_add_pPr()
                pPr.set("marL", str(Inches(0.2 * self.k)))
                pPr.set("indent", str(-Inches(0.2 * self.k)))
                pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•"}))
            r = p.add_run()
            r.text = t
            r.font.size, r.font.bold, r.font.name = Pt(size * self.k), bold, FONT
            r.font.color.rgb = color
        tb.name = name
        return tb

    def arrow(self, x, y, w, h, kind=MSO_SHAPE.RIGHT_ARROW, name=""):
        shp = self.s.shapes.add_shape(kind, *self._xywh(x, y, w, h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = MID
        shp.line.fill.background()
        shp.shadow.inherit = False
        shp.name = name
        return shp


def draw_scheme(slide, x0: float, y0: float, k: float = 1.0) -> None:
    """Схема в прямоугольнике WIDTH × HEIGHT дюймов (× k) с левым верхним углом (x0, y0)."""
    c = _Canvas(slide, x0, y0, k)

    # 1. Что знает сервис — база знаний команды 2 и профили команды 1
    c.text(0, 0, 6, 0.32, [("Что знает сервис", 14, True, BLUE, False)], name="Схема: подпись базы знаний")
    know = [("Правила микрогенерации", "лимит 50 кВт, договор с сетью, подключение", WHITE, MID),
            ("Тарифы и цена выкупа", "город и село, зоны суток, цена ТНС по тарифу", WHITE, MID),
            ("Каталог оборудования", "паспорта и цены проверенных магазинов", WHITE, MID),
            ("Профили потребления", "команда 1: потребление семьи по часам", T1_FILL, T1_LINE)]
    bw, gap = (WIDTH - 3 * 0.17) / 4, 0.17
    for i, (title, body, fill, line) in enumerate(know):
        x = i * (bw + gap)
        c.box(x, 0.36, bw, 1.0, fill, line, name=f"Схема: {title}")
        c.text(x + 0.08, 0.42, bw - 0.16, 0.9,
               [(title, 14, True, BLUE if fill == WHITE else RGBColor(0x7F, 0x60, 0x00), False),
                (body, 12, False, TEXT, False)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
               name=f"Схема: текст {title}")
    c.arrow(WIDTH / 2 - 0.2, 1.42, 0.4, 0.34, MSO_SHAPE.DOWN_ARROW, name="Схема: стрелка вниз")

    # 2. Пользователь → подбор → готовая станция
    top, h = 1.82, 2.28
    lw, cw, rw, aw = 2.5, 4.8, 2.5, 0.35
    cx, rx = lw + aw, lw + aw + cw + aw
    c.box(0, top, lw, h, GREY_FILL, GREY_LINE, name="Схема: пользователь")
    c.text(0.1, top + 0.1, lw - 0.2, h - 0.2,
           [("Пользователь сообщает", 14, True, BLUE, False)] +
           [(t, 13, False, TEXT, True) for t in ("дом и тариф", "потребление: типичная семья или квитанции",
                                                  "крыша: площадь, наклон, сторона", "договор с сетью",
                                                  "цель и бюджет")], name="Схема: текст пользователя")
    c.arrow(lw + 0.03, top + h / 2 - 0.17, aw - 0.06, 0.34, name="Схема: стрелка к подбору")

    c.box(cx, top, cw, h, TINT, BLUE, line_w=1.75, name="Схема: подбор")
    c.text(cx, top + 0.08, cw, 0.36, [("Подбор конфигурации", 15, True, BLUE, False)], align=PP_ALIGN.CENTER,
           name="Схема: заголовок подбора")
    steps = [("1. Энергорасчёт", "выработка по часам по паспорту панели и погоде"),
             ("2. Перебор", "панели, их число, инвертор; проверка правил, паспорта, крыши, бюджета"),
             ("3. Выбор", "по цели: свои нужды, быстрая окупаемость или выгода")]
    sw, sg = 1.46, 0.17
    sx0 = cx + (cw - 3 * sw - 2 * sg) / 2
    for i, (title, body) in enumerate(steps):
        x = sx0 + i * (sw + sg)
        c.box(x, top + 0.52, sw, h - 0.68, WHITE, MID, name=f"Схема: шаг {i + 1}")
        c.text(x + 0.04, top + 0.58, sw - 0.08, h - 0.8, [(title, 13, True, BLUE, False), (body, 12, False, TEXT,
                                                                                         False)],
               align=PP_ALIGN.CENTER, name=f"Схема: текст шага {i + 1}")
        if i < 2:
            c.arrow(x + sw + 0.02, top + 0.52 + (h - 0.68) / 2 - 0.09, sg - 0.04, 0.18,
                    name=f"Схема: стрелка шага {i + 1}")
    c.arrow(cx + cw + 0.03, top + h / 2 - 0.17, aw - 0.06, 0.34, name="Схема: стрелка к станции")

    c.box(rx, top, rw, h, BLUE, None, name="Схема: готовая станция")
    c.text(rx + 0.1, top + 0.1, rw - 0.2, h - 0.2,
           [("Готовая станция", 14, True, WHITE, False)] +
           [(t, 13, False, WHITE, True) for t in ("модели и число панелей", "инвертор и схема цепочек",
                                                  "смета «под ключ»", "срок окупаемости",
                                                  "что ограничило размер")], name="Схема: текст станции")

    # 3. Будущее и кто пользуется
    c.box(cx, 4.22, cw, 0.43, WHITE, MID, dashed=True, name="Схема: будущее")
    c.text(cx, 4.22, cw, 0.43, [("В будущем — ветер и микро-ГЭС: свой каталог и энергорасчёт", 12, False, MID,
                                 False)], align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
           name="Схема: текст будущее")
    c.text(rx, 4.22, rw, 0.43, [("для владельца дома и установщика", 12, False, MUTED, False)],
           align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, name="Схема: кто пользуется")


def export_png(pptx: Path, png: Path, width_px: int = 2550) -> bool:
    """Картинка слайда через PowerPoint (Windows). Нет PowerPoint — False, PNG не трогаем."""
    ps = (f"$ErrorActionPreference='Stop'; $app=New-Object -ComObject PowerPoint.Application; "
          f"$p=$app.Presentations.Open('{pptx}', $true, $false, $false); "
          f"$h=[int]({width_px}*$p.PageSetup.SlideHeight/$p.PageSetup.SlideWidth); "
          f"$p.Slides.Item(1).Export('{png}', 'PNG', {width_px}, $h); $p.Close(); $app.Quit()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], check=True,
                       capture_output=True, timeout=180)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> None:
    prs = Presentation()
    margin, head = 0.35, 0.8
    prs.slide_width = Inches(WIDTH + 2 * margin)
    prs.slide_height = Inches(HEIGHT + head + margin + 0.2)
    s = prs.slides.add_slide(prs.slide_layouts[6])   # пустой макет
    c = _Canvas(s, margin, 0.2, 1.0)
    c.text(0, 0, WIDTH, 0.5, [("SunCount — система поддержки принятия решений по выбору домашней солнечной "
                               "электростанции", 17, True, BLUE, False)], name="Заголовок схемы")
    draw_scheme(s, margin, head + 0.2)
    OUT.mkdir(parents=True, exist_ok=True)
    pptx = OUT / "SunCount_scheme.pptx"
    prs.save(str(pptx))
    print(pptx)
    png = OUT / "SunCount_scheme.png"
    print(png if export_png(pptx, png) else "PowerPoint не найден — PNG не обновлён, схема есть в .pptx")


if __name__ == "__main__":
    main()
