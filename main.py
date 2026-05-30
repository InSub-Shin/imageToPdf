import sys
import os
from io import BytesIO
from pathlib import Path
from collections import defaultdict

import img2pdf
from PIL import Image, ImageDraw
import pandas as pd  # noqa: F401

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QDialog, QFrame,
    QTabWidget, QGroupBox, QCheckBox, QSpinBox, QComboBox,
    QProgressBar, QMessageBox, QAbstractItemView, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont, QPixmap

# ──────────────────────────────────────────────────────────────────
SUPPORTED_EXT = {'.tif', '.tiff', '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}

def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXT


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{stem} ({i}){ext}"):
        i += 1
    return f"{stem} ({i}){ext}"


def images_to_pdf(image_paths: list[str], output_path: str):
    converted, tmp_files = [], []
    for p in image_paths:
        img = Image.open(p)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
            tmp = p + '__tmp__.jpg'
            img.save(tmp, 'JPEG')
            converted.append(tmp)
            tmp_files.append(tmp)
        else:
            converted.append(p)
    with open(output_path, 'wb') as f:
        f.write(img2pdf.convert(converted))
    for tmp in tmp_files:
        try:
            os.remove(tmp)
        except Exception:
            pass


# ── 스핀박스 화살표 PNG 사전 생성 ────────────────────────────────
_ARROW: dict[str, str] = {}

def _init_arrows() -> None:
    """QSpinBox ▲▼ 버튼에 쓸 화살표 PNG를 임시 폴더에 생성"""
    try:
        import tempfile

        def _hex_to_rgb(h: str) -> tuple[int, int, int]:
            h = h.lstrip('#')
            if len(h) == 3:
                h = h[0]*2 + h[1]*2 + h[2]*2
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        def _make(direction: str, rgb: tuple, path: str) -> None:
            w, h = 10, 6
            img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            pts = ([(0, h-1), (w//2, 0), (w-1, h-1)] if direction == 'up'
                   else [(0, 0), (w//2, h-1), (w-1, 0)])
            draw.polygon(pts, fill=(*rgb, 255))
            img.save(path)

        arrow_dir = os.path.join(tempfile.gettempdir(), 'itpdf_arrows')
        os.makedirs(arrow_dir, exist_ok=True)

        # 라이트/다크 테마 색상은 아래 LIGHT/DARK 정의 전에 직접 지정
        for name, color in [('light', '#444466'), ('dark', '#aaaacc')]:
            rgb = _hex_to_rgb(color)
            for direction in ('up', 'down'):
                path = os.path.join(arrow_dir, f'arrow_{direction}_{name}.png')
                _make(direction, rgb, path)
                _ARROW[f'{direction}_{name}'] = path.replace('\\', '/')
    except Exception:
        pass  # 실패 시 화살표 없이 진행 (버튼 동작은 유지)


_init_arrows()


# ── 테마 ─────────────────────────────────────────────────────────
DARK = dict(
    bg='#131c26',     bg2='#1e2a3a',     bg_list='#16202e',
    text='#cde',      text_dim='#aac',
    border='#334',    border2='#2a3a4a',
    accent='#2e6da4', accent_h='#3a84c9',
    accent2='#2e7a4a', accent2_h='#3a9a5e',
    hover='#243345',
    drop_bg='#1e2a3a',  drop_border='#7B9CCC',
    drop_text='#8ab4d4', drop_hover_bg='#243345', drop_drag_bg='#1a3a5a',
    info_bg='#1a2a1a',  info_text='#8dca8d',
    tab_text='#99b',    grp_title='#aac',
)

LIGHT = dict(
    bg='#f0f2f5',   bg2='#ffffff',     bg_list='#fafafa',
    text='#1a1a2e', text_dim='#444466',
    border='#ccd',  border2='#aabbcc',
    accent='#2e6da4', accent_h='#1a5a90',
    accent2='#2e7a4a', accent2_h='#1a6035',
    hover='#dde8f5',
    drop_bg='#e8f0f8',  drop_border='#5580bb',
    drop_text='#2255aa', drop_hover_bg='#d0e4f4', drop_drag_bg='#b0cce8',
    info_bg='#e8f4e8',  info_text='#1a6020',
    tab_text='#334466', grp_title='#334466',
)


def build_stylesheet(t: dict) -> str:
    _theme = 'dark' if t is DARK else 'light'
    _up_img  = _ARROW.get(f'up_{_theme}',   '')
    _dn_img  = _ARROW.get(f'down_{_theme}', '')
    _up_css  = f'image: url({_up_img}); ' if _up_img  else ''
    _dn_css  = f'image: url({_dn_img}); ' if _dn_img  else ''
    return f"""
    QWidget {{
        background: {t['bg']}; color: {t['text']}; font-size: 12px;
    }}
    QGroupBox {{
        border: 1px solid {t['border2']}; border-radius: 6px;
        margin-top: 8px; padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 10px; padding: 0 4px;
        color: {t['grp_title']}; font-weight: bold;
    }}
    QLineEdit, QComboBox {{
        background: {t['bg2']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 4px; padding: 4px 6px;
    }}
    QSpinBox {{
        background: {t['bg2']}; color: {t['text']};
        border: 1px solid {t['border']}; border-radius: 4px;
        padding: 3px 22px 3px 6px;
    }}
    QSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 20px;
        border-left: 1px solid {t['border']};
        border-bottom: 1px solid {t['border']};
        border-top-right-radius: 3px;
        background: {t['bg2']};
    }}
    QSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 20px;
        border-left: 1px solid {t['border']};
        border-bottom-right-radius: 3px;
        background: {t['bg2']};
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {t['hover']};
    }}
    QSpinBox::up-arrow   {{ {_up_css}width: 10px; height: 6px; }}
    QSpinBox::down-arrow {{ {_dn_css}width: 10px; height: 6px; }}
    QPushButton {{
        background: {t['bg2']}; color: {t['text_dim']};
        border: 1px solid {t['border']}; border-radius: 4px; padding: 5px 12px;
    }}
    QPushButton:hover  {{ background: {t['hover']}; }}
    QPushButton:disabled {{ background: {t['bg']}; color: {t['border2']}; }}
    QCheckBox {{ color: {t['text_dim']}; }}
    QLabel    {{ color: {t['text_dim']}; }}
    QTableWidget, QListWidget {{
        background: {t['bg_list']}; color: {t['text']};
        border: 1px solid {t['border']}; gridline-color: {t['border2']};
    }}
    QTableWidget::item:hover, QListWidget::item:hover {{
        background: {t['hover']};
    }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {t['accent']}; color: white;
    }}
    QHeaderView::section {{
        background: {t['bg2']}; color: {t['text_dim']};
        border: 1px solid {t['border2']}; padding: 4px;
    }}
    QProgressBar {{
        background: {t['bg2']}; border: 1px solid {t['border']};
        border-radius: 4px; text-align: center;
    }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
    QTabWidget::pane {{ border: 1px solid {t['border']}; background: {t['bg']}; }}
    QTabBar::tab {{
        background: {t['bg2']}; color: {t['tab_text']};
        padding: 10px 22px; border-radius: 4px 4px 0 0;
        margin-right: 2px; font-size: 13px;
    }}
    QTabBar::tab:selected {{
        background: {t['accent']}; color: white; font-weight: bold;
    }}
    QStatusBar {{ background: {t['bg']}; color: {t['border2']}; }}
    QScrollBar:vertical {{
        background: {t['bg']}; width: 10px; border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {t['border2']}; border-radius: 4px; min-height: 20px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

    QLabel#drop_area {{
        border: 2px dashed {t['drop_border']}; border-radius: 12px;
        background: {t['drop_bg']}; color: {t['drop_text']};
        font-size: 14px; padding: 30px;
    }}
    QLabel#drop_area:hover        {{ background: {t['drop_hover_bg']}; }}
    QLabel#drop_area[dragging="true"] {{ background: {t['drop_drag_bg']}; }}

    QLabel#info_label {{
        background: {t['info_bg']}; color: {t['info_text']};
        padding: 10px; border-radius: 6px;
    }}

    QPushButton#run_btn {{
        background: {t['accent']}; color: white; font-size: 15px;
        border-radius: 8px; font-weight: bold; border: none;
    }}
    QPushButton#run_btn:hover    {{ background: {t['accent_h']}; }}
    QPushButton#run_btn:disabled {{ background: {t['border2']}; color: {t['bg']}; border: none; }}

    QPushButton#run_btn_green {{
        background: {t['accent2']}; color: white; font-size: 15px;
        border-radius: 8px; font-weight: bold; border: none;
    }}
    QPushButton#run_btn_green:hover    {{ background: {t['accent2_h']}; }}
    QPushButton#run_btn_green:disabled {{ background: {t['border2']}; color: {t['bg']}; border: none; }}

    QPushButton#theme_btn {{
        background: transparent; color: {t['text_dim']};
        border: 1px solid {t['border']}; border-radius: 12px;
        padding: 3px 14px; font-size: 12px;
    }}
    QPushButton#theme_btn:hover {{ background: {t['hover']}; }}
    """


# ── 워커 스레드 ──────────────────────────────────────────────────
class PdfWorker(QThread):
    progress = pyqtSignal(int, int)
    done     = pyqtSignal(list)
    error    = pyqtSignal(str)

    def __init__(self, jobs: list[tuple[list, str]]):
        super().__init__()
        self.jobs = jobs

    def run(self):
        results = []
        total = len(self.jobs)
        for i, (imgs, out) in enumerate(self.jobs, 1):
            try:
                out = unique_path(out)
                images_to_pdf(imgs, out)
                results.append(out)
            except Exception as e:
                self.error.emit(f"{out}\n{e}")
            self.progress.emit(i, total)
        self.done.emit(results)


# ── 탭 1 : 드래그 앤 드롭 ────────────────────────────────────────
class DropArea(QLabel):
    files_dropped = pyqtSignal(list)
    clicked       = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("drop_area")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("🖼  이미지 파일을 여기에 드래그하거나 클릭하세요\n(TIF · JPG · PNG · BMP 등)")
        self.setMinimumHeight(120)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)

    def _set_dragging(self, val: bool):
        self.setProperty("dragging", val)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_dragging(True)

    def dragLeaveEvent(self, e):
        self._set_dragging(False)

    def dropEvent(self, e: QDropEvent):
        self._set_dragging(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        images = [p for p in paths if is_image(p)]
        if images:
            self.files_dropped.emit(images)


class Tab1_DragDrop(QWidget):
    def __init__(self):
        super().__init__()
        self.image_paths: list[str] = []
        self._rotations:  list[int] = []   # 시계방향 누적 각도 (0/90/180/270)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.drop_area = DropArea()
        self.drop_area.files_dropped.connect(self._add_images)
        self.drop_area.clicked.connect(self._browse_files)
        layout.addWidget(self.drop_area)

        grp = QGroupBox("추가된 이미지 목록")
        grp_outer = QHBoxLayout(grp)
        grp_outer.setSpacing(8)

        # 왼쪽: 테이블 + 버튼
        left_w = QWidget()
        grp_layout = QVBoxLayout(left_w)
        grp_layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["#", "파일명"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 44)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        self.table.itemSelectionChanged.connect(self._show_preview)
        grp_layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_add    = QPushButton("파일 추가")
        btn_folder = QPushButton("폴더 열기")
        btn_up     = QPushButton("▲")
        btn_down   = QPushButton("▼")
        btn_del    = QPushButton("선택 삭제")
        btn_clear  = QPushButton("전체 지우기")
        for b in [btn_add, btn_folder, btn_up, btn_down, btn_del, btn_clear]:
            b.setFixedHeight(30)
            btn_row.addWidget(b)
        btn_add.clicked.connect(self._browse_files)
        btn_folder.clicked.connect(self._browse_folder_images)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)
        btn_del.clicked.connect(self._delete_selected)
        btn_clear.clicked.connect(self._clear)
        grp_layout.addLayout(btn_row)

        # 회전 버튼 행
        rot_row = QHBoxLayout()
        rot_lbl = QLabel("선택 이미지 회전:")
        rot_lbl.setFixedWidth(110)
        rot_row.addWidget(rot_lbl)
        btn_rot_ccw = QPushButton("↺  반시계")
        btn_rot_cw  = QPushButton("↻  시계")
        for b in [btn_rot_ccw, btn_rot_cw]:
            b.setFixedHeight(28)
            b.setFixedWidth(90)
            rot_row.addWidget(b)
        rot_row.addStretch()
        btn_rot_ccw.clicked.connect(self._rotate_ccw)
        btn_rot_cw.clicked.connect(self._rotate_cw)
        grp_layout.addLayout(rot_row)

        grp_outer.addWidget(left_w, 1)

        # 오른쪽: 미리보기 패널
        self.preview_lbl = QLabel("선택된\n이미지\n미리보기")
        self.preview_lbl.setFixedWidth(170)
        self.preview_lbl.setMinimumHeight(170)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_lbl.setStyleSheet(
            "border: 1px dashed #aabbcc; border-radius: 6px; color: #889; font-size: 11px;"
        )
        grp_outer.addWidget(self.preview_lbl)

        layout.addWidget(grp)

        out_grp = QGroupBox("출력 설정")
        out_layout = QHBoxLayout(out_grp)
        out_layout.addWidget(QLabel("파일명:"))
        self.name_edit = QLineEdit("samplePDF")
        self.name_edit.setFixedWidth(200)
        out_layout.addWidget(self.name_edit)
        out_layout.addWidget(QLabel(".pdf"))
        out_layout.addStretch()
        out_layout.addWidget(QLabel("저장 위치:"))
        self.out_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        out_layout.addWidget(self.out_dir_edit)
        btn_browse_out = QPushButton("…")
        btn_browse_out.setFixedWidth(30)
        btn_browse_out.clicked.connect(self._browse_out)
        out_layout.addWidget(btn_browse_out)
        layout.addWidget(out_grp)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.btn_run = QPushButton("▶  PDF 생성")
        self.btn_run.setObjectName("run_btn")
        self.btn_run.setFixedHeight(42)
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    # ── 슬롯 ──────────────────────────────────────
    def _add_images(self, paths: list[str]):
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                self._rotations.append(0)
                row = self.table.rowCount()
                self.table.insertRow(row)
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 0, num_item)
                self.table.setItem(row, 1, QTableWidgetItem(os.path.basename(p)))

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "이미지 선택", "",
            "이미지 (*.tif *.tiff *.jpg *.jpeg *.png *.bmp)")
        self._add_images(files)

    def _browse_folder_images(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder:
            return
        images = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.is_file() and is_image(str(p))
        )
        if not images:
            QMessageBox.information(self, "알림", "선택한 폴더에 이미지 파일이 없습니다.")
            return
        self._add_images(images)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if d:
            self.out_dir_edit.setText(d)

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        self.image_paths[row - 1], self.image_paths[row] = (
            self.image_paths[row], self.image_paths[row - 1]
        )
        self._rotations[row - 1], self._rotations[row] = (
            self._rotations[row], self._rotations[row - 1]
        )
        self.table.item(row - 1, 1).setText(os.path.basename(self.image_paths[row - 1]))
        self.table.item(row,     1).setText(os.path.basename(self.image_paths[row]))
        self.table.setCurrentCell(row - 1, 1)

    def _move_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self.image_paths[row], self.image_paths[row + 1] = (
            self.image_paths[row + 1], self.image_paths[row]
        )
        self._rotations[row], self._rotations[row + 1] = (
            self._rotations[row + 1], self._rotations[row]
        )
        self.table.item(row,     1).setText(os.path.basename(self.image_paths[row]))
        self.table.item(row + 1, 1).setText(os.path.basename(self.image_paths[row + 1]))
        self.table.setCurrentCell(row + 1, 1)

    def _delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            self.image_paths.pop(row)
            self._rotations.pop(row)
        self._refresh_numbers()

    def _refresh_numbers(self):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setText(str(i + 1))

    def _clear(self):
        self.image_paths.clear()
        self._rotations.clear()
        self.table.setRowCount(0)
        self.preview_lbl.clear()
        self.preview_lbl.setText("선택된\n이미지\n미리보기")

    def _show_preview(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.image_paths):
            self.preview_lbl.clear()
            self.preview_lbl.setText("선택된\n이미지\n미리보기")
            return
        path = self.image_paths[row]
        rot  = self._rotations[row] if row < len(self._rotations) else 0
        try:
            img = Image.open(path)
            if rot:
                img = img.rotate(-rot, expand=True)
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.getvalue())
            w = self.preview_lbl.width() - 10
            h = self.preview_lbl.height() - 10
            if w > 0 and h > 0:
                scaled = pix.scaled(w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self.preview_lbl.setPixmap(scaled)
        except Exception:
            self.preview_lbl.clear()
            self.preview_lbl.setText("미리보기\n불가")

    def _rotate_cw(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.image_paths):
            return
        self._rotations[row] = (self._rotations[row] + 90) % 360
        self._show_preview()

    def _rotate_ccw(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.image_paths):
            return
        self._rotations[row] = (self._rotations[row] - 90) % 360
        self._show_preview()

    def _run(self):
        if not self.image_paths:
            QMessageBox.warning(self, "경고", "이미지를 먼저 추가하세요.")
            return

        # 회전이 있는 이미지를 미리 회전된 임시 파일로 변환
        paths_for_pdf = []
        self._tmp_rot_files: list[str] = []
        for i, p in enumerate(self.image_paths):
            rot = self._rotations[i] % 360 if i < len(self._rotations) else 0
            if rot == 0:
                paths_for_pdf.append(p)
            else:
                try:
                    img = Image.open(p)
                    img = img.rotate(-rot, expand=True)
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    tmp = p + f'__rot{rot}__.jpg'
                    img.save(tmp, 'JPEG')
                    paths_for_pdf.append(tmp)
                    self._tmp_rot_files.append(tmp)
                except Exception:
                    paths_for_pdf.append(p)

        name = self.name_edit.text().strip() or "samplePDF"
        out_dir = self.out_dir_edit.text().strip()
        out_path = os.path.join(out_dir, name + ".pdf")

        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 1)

        self._worker = PdfWorker([(paths_for_pdf, out_path)])
        self._worker.progress.connect(lambda c, _t: self.progress.setValue(c))
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(lambda e: QMessageBox.critical(self, "오류", e))
        self._worker.start()

    def _on_done(self, results: list):
        self.btn_run.setEnabled(True)
        self.progress.setVisible(False)
        for tmp in getattr(self, '_tmp_rot_files', []):
            try:
                os.remove(tmp)
            except Exception:
                pass
        self._tmp_rot_files = []
        if results:
            QMessageBox.information(self, "완료", f"PDF 생성 완료!\n{results[0]}")


class _Reverse:
    def __init__(self, v): self.v = v
    def __lt__(self, o): return self.v > o.v
    def __eq__(self, o): return self.v == o.v


# ── 탭 2 : 커스텀 파싱 ──────────────────────────────────────────
class Tab3_HyundaiHDS(QWidget):
    def __init__(self):
        super().__init__()
        self.image_paths: list[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ─ 파싱 설정 ──────────────────────────────────────────────
        parse_grp = QGroupBox("파싱 설정")
        pl = QVBoxLayout(parse_grp)
        pl.setSpacing(6)

        memo_row = QHBoxLayout()
        memo_row.addWidget(QLabel("파일명 구조 메모:"))
        self.memo_edit = QLineEdit(
            "약어(0) _ 보관일자(1) _ 서식코드(2) _ 증권번호(3) _ 서식코드(4) _ 순번(5) _ IMG _ 이미지명 _ 순번"
        )
        self.memo_edit.setToolTip("참고용 메모입니다. 파싱에 영향을 주지 않습니다.")
        memo_row.addWidget(self.memo_edit)
        btn_reset_cfg = QPushButton("↺  초기화")
        btn_reset_cfg.setFixedWidth(84)
        btn_reset_cfg.clicked.connect(self._reset_settings)
        memo_row.addWidget(btn_reset_cfg)
        pl.addLayout(memo_row)

        idx_row = QHBoxLayout()
        idx_row.addWidget(QLabel("구분자:"))
        self.delim_edit = QLineEdit("_")
        self.delim_edit.setFixedWidth(46)
        self.delim_edit.setToolTip(
            "파일명을 나누는 구분 문자입니다.\n"
            "\n"
            "예) 파일명: AA_20240101_FC01_123456789_FC02_003\n"
            "    구분자 '_' 로 분리하면:\n"
            "    [0]AA  [1]20240101  [2]FC01  [3]123456789  [4]FC02  [5]003"
        )
        idx_row.addWidget(self.delim_edit)
        idx_row.addSpacing(16)
        idx_row.addWidget(QLabel("그룹 기준 인덱스:"))
        self.group_spin = QSpinBox()
        self.group_spin.setRange(0, 30)
        self.group_spin.setValue(3)
        self.group_spin.setToolTip(
            "같은 값을 가진 파일들을 하나의 PDF로 묶을 항목 번호입니다 (0부터 시작).\n"
            "\n"
            "예) 인덱스 3 = 증권번호\n"
            "    → 증권번호가 같은 파일들이 하나의 PDF로 합쳐집니다."
        )
        idx_row.addWidget(self.group_spin)
        idx_row.addSpacing(16)
        idx_row.addWidget(QLabel("상세 표시 인덱스:"))
        self.detail_spin = QSpinBox()
        self.detail_spin.setRange(0, 30)
        self.detail_spin.setValue(4)
        self.detail_spin.setToolTip(
            "미리보기 '상세 목록' 컬럼에 표시할 항목 번호입니다.\n"
            "그룹 안에 어떤 값들이 포함됐는지 확인하는 용도입니다.\n"
            "\n"
            "예) 인덱스 4 = 서식코드\n"
            "    → 미리보기에 'FC01, FC02' 처럼 포함된 서식코드 목록이 표시됩니다."
        )
        idx_row.addWidget(self.detail_spin)
        idx_row.addStretch()
        pl.addLayout(idx_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("정렬 인덱스 1:"))
        self.sort1_spin = QSpinBox()
        self.sort1_spin.setRange(-1, 30)
        self.sort1_spin.setValue(4)
        self.sort1_spin.setToolTip(
            "같은 그룹 안에서 파일 순서를 결정하는 1차 기준입니다.\n"
            "숫자 값은 숫자로, 문자는 알파벳 순으로 자동 비교합니다.\n"
            "-1 입력 시 미사용.\n"
            "\n"
            "예) 인덱스 4(서식코드) 오름차순\n"
            "    → FC01, FC02, FC03 순으로 정렬"
        )
        sort_row.addWidget(self.sort1_spin)
        self.sort1_combo = QComboBox()
        self.sort1_combo.addItems(["오름차순", "내림차순"])
        sort_row.addWidget(self.sort1_combo)
        sort_row.addSpacing(16)
        sort_row.addWidget(QLabel("정렬 인덱스 2:"))
        self.sort2_spin = QSpinBox()
        self.sort2_spin.setRange(-1, 30)
        self.sort2_spin.setValue(5)
        self.sort2_spin.setToolTip(
            "정렬 1이 같을 때 적용되는 2차 정렬 기준입니다.\n"
            "-1 입력 시 미사용.\n"
            "\n"
            "예) 인덱스 5(순번) 오름차순\n"
            "    → 001, 002, 003 순으로 정렬"
        )
        sort_row.addWidget(self.sort2_spin)
        self.sort2_combo = QComboBox()
        self.sort2_combo.addItems(["오름차순", "내림차순"])
        sort_row.addWidget(self.sort2_combo)
        sort_row.addStretch()
        pl.addLayout(sort_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        pl.addWidget(sep)

        ex_row = QHBoxLayout()
        ex_lbl = QLabel("파일명 예시:")
        ex_lbl.setFixedWidth(76)
        ex_row.addWidget(ex_lbl)
        self.example_edit = QLineEdit("AA_20240101_FC01_123456789_FC02_003_IMG_img_001")
        self.example_edit.setPlaceholderText("파일명 입력 시 아래에 파싱 결과가 실시간으로 표시됩니다 (확장자 제외)")
        ex_row.addWidget(self.example_edit)
        pl.addLayout(ex_row)

        self.example_result = QLabel()
        self.example_result.setTextFormat(Qt.TextFormat.RichText)
        self.example_result.setWordWrap(True)
        pl.addWidget(self.example_result)

        self.delim_edit.textChanged.connect(self._update_example)
        self.example_edit.textChanged.connect(self._update_example)
        for sp in (self.group_spin, self.detail_spin, self.sort1_spin, self.sort2_spin):
            sp.valueChanged.connect(self._update_example)
        self._update_example()

        layout.addWidget(parse_grp)

        # ─ 이미지 목록 ────────────────────────────────────────────
        img_grp = QGroupBox("이미지 목록")
        ig = QVBoxLayout(img_grp)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["#", "파일명"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 44)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        ig.addWidget(self.table)

        file_btn_row = QHBoxLayout()
        btn_add    = QPushButton("파일 추가")
        btn_folder = QPushButton("폴더 열기")
        btn_up     = QPushButton("▲")
        btn_down   = QPushButton("▼")
        btn_del    = QPushButton("선택 삭제")
        btn_clr    = QPushButton("전체 지우기")
        for b in [btn_add, btn_folder, btn_up, btn_down, btn_del, btn_clr]:
            b.setFixedHeight(30)
            file_btn_row.addWidget(b)
        btn_add.clicked.connect(self._browse_files)
        btn_folder.clicked.connect(self._browse_folder_images)
        btn_up.clicked.connect(self._move_up)
        btn_down.clicked.connect(self._move_down)
        btn_del.clicked.connect(self._delete_selected)
        btn_clr.clicked.connect(self._clear_list)
        ig.addLayout(file_btn_row)

        btn_grp_prev = QPushButton("🔍  그룹 미리보기")
        btn_grp_prev.setFixedHeight(34)
        btn_grp_prev.clicked.connect(self._show_group_preview)
        ig.addWidget(btn_grp_prev)

        layout.addWidget(img_grp)

        # ─ 출력 설정 ──────────────────────────────────────────────
        out_grp = QGroupBox("출력 설정")
        ol = QHBoxLayout(out_grp)
        ol.addWidget(QLabel("저장 위치:"))
        self.out_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        ol.addWidget(self.out_dir_edit)
        btn_out = QPushButton("…")
        btn_out.setFixedWidth(30)
        btn_out.clicked.connect(self._browse_out)
        ol.addWidget(btn_out)
        ol.addSpacing(20)
        ol.addWidget(QLabel("PDF 파일명:"))
        self.name_combo = QComboBox()
        self.name_combo.addItems(["그룹 키", "그룹 키 + 상세 목록"])
        ol.addWidget(self.name_combo)
        layout.addWidget(out_grp)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.btn_run = QPushButton("▶  그룹별 PDF 일괄 생성")
        self.btn_run.setObjectName("run_btn_green")
        self.btn_run.setFixedHeight(42)
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    # ── 파일 관리 ──────────────────────────────────────────────────
    def _add_images(self, paths: list[str]):
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
                row = self.table.rowCount()
                self.table.insertRow(row)
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, 0, num_item)
                self.table.setItem(row, 1, QTableWidgetItem(os.path.basename(p)))

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "이미지 선택", "",
            "이미지 (*.tif *.tiff *.jpg *.jpeg *.png *.bmp)")
        self._add_images(files)

    def _browse_folder_images(self):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if not folder:
            return
        images = sorted(
            str(p) for p in Path(folder).iterdir()
            if p.is_file() and is_image(str(p))
        )
        if not images:
            QMessageBox.information(self, "알림", "선택한 폴더에 이미지 파일이 없습니다.")
            return
        self._add_images(images)

    def _move_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        self.image_paths[row - 1], self.image_paths[row] = (
            self.image_paths[row], self.image_paths[row - 1]
        )
        self.table.item(row - 1, 1).setText(os.path.basename(self.image_paths[row - 1]))
        self.table.item(row,     1).setText(os.path.basename(self.image_paths[row]))
        self.table.setCurrentCell(row - 1, 1)

    def _move_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        self.image_paths[row], self.image_paths[row + 1] = (
            self.image_paths[row + 1], self.image_paths[row]
        )
        self.table.item(row,     1).setText(os.path.basename(self.image_paths[row]))
        self.table.item(row + 1, 1).setText(os.path.basename(self.image_paths[row + 1]))
        self.table.setCurrentCell(row + 1, 1)

    def _delete_selected(self):
        rows = sorted({i.row() for i in self.table.selectedItems()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
            self.image_paths.pop(row)
        self._refresh_numbers()

    def _clear_list(self):
        self.image_paths.clear()
        self.table.setRowCount(0)

    def _refresh_numbers(self):
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setText(str(i + 1))

    def _reset_settings(self):
        self.memo_edit.setText(
            "약어(0) _ 보관일자(1) _ 서식코드(2) _ 증권번호(3) _ 서식코드(4) _ 순번(5) _ IMG _ 이미지명 _ 순번"
        )
        self.delim_edit.setText("_")
        self.group_spin.setValue(3)
        self.detail_spin.setValue(4)
        self.sort1_spin.setValue(4)
        self.sort1_combo.setCurrentIndex(0)
        self.sort2_spin.setValue(5)
        self.sort2_combo.setCurrentIndex(0)
        self.example_edit.setText("AA_20240101_FC01_123456789_FC02_003_IMG_img_001")

    # ── 그룹 미리보기 다이얼로그 ──────────────────────────────────
    def _show_group_preview(self):
        if not self.image_paths:
            QMessageBox.warning(self, "경고", "먼저 이미지를 추가하세요.")
            return
        groups = self._get_groups()
        dlg = QDialog(self)
        dlg.setWindowTitle("그룹 미리보기")
        dlg.setMinimumSize(740, 440)
        dlg_layout = QVBoxLayout(dlg)

        dlg_layout.addWidget(QLabel(
            f"총 <b>{len(groups)}</b>개 그룹  /  <b>{len(self.image_paths)}</b>개 파일"
        ))

        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels(["그룹 키", "파일 수", "상세 목록", "출력 PDF명"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for group_key, files in sorted(groups.items()):
            details = sorted({self._extract(f)['detail'] for f in files})
            row = tbl.rowCount()
            tbl.insertRow(row)
            tbl.setItem(row, 0, QTableWidgetItem(group_key))
            tbl.setItem(row, 1, QTableWidgetItem(str(len(files))))
            tbl.setItem(row, 2, QTableWidgetItem(", ".join(details)))
            tbl.setItem(row, 3, QTableWidgetItem(f"{group_key}.pdf"))
        dlg_layout.addWidget(tbl)

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(dlg.accept)
        dlg_layout.addWidget(btn_close)
        dlg.exec()

    # ── 헬퍼 ──────────────────────────────────────────────────────
    def _extract(self, path: str) -> dict:
        delim = self.delim_edit.text() or '_'
        parts = Path(path).stem.split(delim)

        def get(idx: int) -> str:
            return parts[idx] if 0 <= idx < len(parts) else ''

        s1_raw = get(self.sort1_spin.value())
        s2_raw = get(self.sort2_spin.value())
        try: s1 = int(s1_raw)
        except: s1 = s1_raw
        try: s2 = int(s2_raw)
        except: s2 = s2_raw

        return {
            'group':  get(self.group_spin.value()),
            'detail': get(self.detail_spin.value()),
            'sort1':  s1,
            'sort2':  s2,
        }

    def _update_example(self):
        filename = self.example_edit.text().strip()
        if not filename:
            self.example_result.setText("")
            return

        delim  = self.delim_edit.text() or '_'
        parts  = filename.split(delim)
        g_idx  = self.group_spin.value()
        d_idx  = self.detail_spin.value()
        s1_idx = self.sort1_spin.value()
        s2_idx = self.sort2_spin.value()

        role_map: dict[int, list[str]] = {}
        for idx, label in [(g_idx, '그룹'), (d_idx, '상세'), (s1_idx, '정렬1'), (s2_idx, '정렬2')]:
            if idx >= 0:
                role_map.setdefault(idx, []).append(label)

        split_parts = []
        for i, p in enumerate(parts[:10]):
            roles = role_map.get(i, [])
            if roles:
                split_parts.append(f'<b>[{i}]&nbsp;{p}</b>({",".join(roles)})')
            else:
                split_parts.append(f'[{i}]&nbsp;{p}')
        if len(parts) > 10:
            split_parts.append('…')

        def val(idx: int) -> str:
            if idx < 0:
                return '(미사용)'
            return f'<b>{parts[idx]}</b>' if idx < len(parts) else '<i>⚠&nbsp;범위&nbsp;초과</i>'

        result_html = (
            '&nbsp;·&nbsp;'.join(split_parts)
            + '<br>→&nbsp;&nbsp;'
            + '&nbsp;&nbsp;|&nbsp;&nbsp;'.join([
                f'그룹&nbsp;키({g_idx}):&nbsp;{val(g_idx)}',
                f'상세({d_idx}):&nbsp;{val(d_idx)}',
                f'정렬1({s1_idx}):&nbsp;{val(s1_idx)}',
                f'정렬2({s2_idx}):&nbsp;{val(s2_idx)}',
            ])
        )
        self.example_result.setText(result_html)

    def _get_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list] = defaultdict(list)
        for f in self.image_paths:
            key = self._extract(f)['group']
            if key:
                groups[key].append(f)

        asc1 = self.sort1_combo.currentIndex() == 0
        asc2 = self.sort2_combo.currentIndex() == 0

        for key in groups:
            groups[key].sort(key=lambda f: (
                self._extract(f)['sort1'] if asc1 else _Reverse(self._extract(f)['sort1']),
                self._extract(f)['sort2'] if asc2 else _Reverse(self._extract(f)['sort2']),
            ))
        return dict(groups)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if d:
            self.out_dir_edit.setText(d)

    def _run(self):
        if not self.image_paths:
            QMessageBox.warning(self, "경고", "먼저 이미지를 추가하세요.")
            return
        groups = self._get_groups()
        out_dir = self.out_dir_edit.text().strip()
        use_detail = self.name_combo.currentIndex() == 1

        jobs = []
        for group_key, files in groups.items():
            if use_detail:
                details = sorted({self._extract(f)['detail'] for f in files})
                pdf_name = f"{group_key}_{'_'.join(details)}.pdf"
            else:
                pdf_name = f"{group_key}.pdf"
            jobs.append((files, os.path.join(out_dir, pdf_name)))

        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(jobs))

        self._worker = PdfWorker(jobs)
        self._worker.progress.connect(lambda c, _t: self.progress.setValue(c))
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(lambda e: QMessageBox.critical(self, "오류", e))
        self._worker.start()

    def _on_done(self, results: list):
        self.btn_run.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.information(self, "완료",
            f"{len(results)}개 PDF 생성 완료!\n저장 위치: {self.out_dir_edit.text()}")


# ── 탭 3 : 현대HDS 전용 (고정 파싱) ─────────────────────────────
class Tab3_HDS_Fixed(QWidget):
    """
    파일명: 약어_보관일자_서식코드_증권번호_서식코드_순번_IMG_이미지명_순번.TIF
    그룹: 증권번호(idx=3) / 정렬: 서식코드(idx=4) ASC → 순번(idx=5) ASC
    """
    def __init__(self):
        super().__init__()
        self._files: list[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        info = QLabel(
            "📋  장기계약팀 전용  |  파일명 구조: "
            "약어 _ 보관일자 _ 서식코드 _ <b>증권번호</b> _ 서식코드 _ 순번 _ IMG _ 이미지명 _ 순번 .TIF<br>"
            "같은 <b>증권번호</b>끼리 묶고, <b>서식코드 ASC → 순번 ASC</b> 순으로 정렬하여 PDF 생성"
        )
        info.setObjectName("info_label")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)

        grp = QGroupBox("폴더 선택")
        gl = QHBoxLayout(grp)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("TIF 파일이 들어있는 폴더")
        gl.addWidget(self.folder_edit)
        btn = QPushButton("찾아보기")
        btn.clicked.connect(self._browse)
        gl.addWidget(btn)
        self.chk_recursive = QCheckBox("하위 폴더 포함")
        gl.addWidget(self.chk_recursive)
        btn_scan = QPushButton("스캔")
        btn_scan.clicked.connect(self._scan)
        gl.addWidget(btn_scan)
        btn_reset = QPushButton("↺  초기화")
        btn_reset.clicked.connect(self._reset)
        gl.addWidget(btn_reset)
        layout.addWidget(grp)

        prev_grp = QGroupBox("증권번호별 그룹 미리보기")
        pl = QVBoxLayout(prev_grp)
        self.preview_table = QTableWidget(0, 4)
        self.preview_table.setHorizontalHeaderLabels(["증권번호", "파일 수", "서식코드 목록", "출력 PDF명"])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        pl.addWidget(self.preview_table)
        btn_prev = QPushButton("🔍 미리보기")
        btn_prev.clicked.connect(self._preview)
        pl.addWidget(btn_prev)
        layout.addWidget(prev_grp)

        out_grp = QGroupBox("출력 설정")
        ol = QHBoxLayout(out_grp)
        ol.addWidget(QLabel("저장 위치:"))
        self.out_dir_edit = QLineEdit(str(Path.home() / "Downloads"))
        ol.addWidget(self.out_dir_edit)
        btn_out = QPushButton("…")
        btn_out.setFixedWidth(30)
        btn_out.clicked.connect(self._browse_out)
        ol.addWidget(btn_out)
        ol.addSpacing(20)
        ol.addWidget(QLabel("PDF 파일명:"))
        self.name_combo = QComboBox()
        self.name_combo.addItems(["증권번호", "증권번호_서식코드목록"])
        ol.addWidget(self.name_combo)
        layout.addWidget(out_grp)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.btn_run = QPushButton("▶  증권번호별 PDF 일괄 생성")
        self.btn_run.setObjectName("run_btn_green")
        self.btn_run.setFixedHeight(42)
        self.btn_run.clicked.connect(self._run)
        layout.addWidget(self.btn_run)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if d:
            self.folder_edit.setText(d)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "저장 폴더 선택")
        if d:
            self.out_dir_edit.setText(d)

    def _scan(self):
        folder = self.folder_edit.text().strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "경고", "유효한 폴더를 선택하세요.")
            return
        exts = {'.tif', '.tiff'}
        if self.chk_recursive.isChecked():
            self._files = [str(p) for p in Path(folder).rglob('*') if p.suffix.lower() in exts]
        else:
            self._files = [str(p) for p in Path(folder).iterdir() if p.suffix.lower() in exts]
        QMessageBox.information(self, "스캔 완료", f"{len(self._files)}개 TIF 파일 발견")

    def _reset(self):
        self.folder_edit.clear()
        self._files.clear()
        self.preview_table.setRowCount(0)

    def _parse(self, path: str):
        parts = Path(path).stem.split('_')
        policy_no = parts[3] if len(parts) > 3 else ''
        form_code = parts[4] if len(parts) > 4 else ''
        seq       = parts[5] if len(parts) > 5 else ''
        try: seq_int = int(seq)
        except: seq_int = 0
        return policy_no, form_code, seq_int

    def _get_groups(self) -> dict[str, list[str]]:
        groups: dict[str, list] = defaultdict(list)
        for f in self._files:
            policy_no, _, _ = self._parse(f)
            if policy_no:
                groups[policy_no].append(f)
        for key in groups:
            groups[key].sort(key=lambda f: (self._parse(f)[1], self._parse(f)[2]))
        return dict(groups)

    def _preview(self):
        if not self._files:
            QMessageBox.warning(self, "경고", "먼저 폴더를 스캔하세요.")
            return
        groups = self._get_groups()
        self.preview_table.setRowCount(0)
        for policy_no, files in sorted(groups.items()):
            form_codes = sorted({self._parse(f)[1] for f in files})
            row = self.preview_table.rowCount()
            self.preview_table.insertRow(row)
            self.preview_table.setItem(row, 0, QTableWidgetItem(policy_no))
            self.preview_table.setItem(row, 1, QTableWidgetItem(str(len(files))))
            self.preview_table.setItem(row, 2, QTableWidgetItem(", ".join(form_codes)))
            self.preview_table.setItem(row, 3, QTableWidgetItem(f"{policy_no}.pdf"))

    def _run(self):
        if not self._files:
            QMessageBox.warning(self, "경고", "먼저 폴더를 스캔하세요.")
            return
        groups = self._get_groups()
        out_dir = self.out_dir_edit.text().strip()
        use_form = self.name_combo.currentIndex() == 1

        jobs = []
        for policy_no, files in groups.items():
            if use_form:
                form_codes = sorted({self._parse(f)[1] for f in files})
                pdf_name = f"{policy_no}_{'_'.join(form_codes)}.pdf"
            else:
                pdf_name = f"{policy_no}.pdf"
            jobs.append((files, os.path.join(out_dir, pdf_name)))

        self.btn_run.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(jobs))

        self._worker = PdfWorker(jobs)
        self._worker.progress.connect(lambda c, _t: self.progress.setValue(c))
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(lambda e: QMessageBox.critical(self, "오류", e))
        self._worker.start()

    def _on_done(self, results: list):
        self.btn_run.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.information(self, "완료",
            f"{len(results)}개 PDF 생성 완료!\n저장 위치: {self.out_dir_edit.text()}")


# ── 메인 윈도우 ──────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._theme = 'light'
        self.setWindowTitle("ImageToPDF  v1.0")
        self.setMinimumSize(860, 680)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        self._tabs.addTab(Tab1_DragDrop(),    "🖼  드래그 & 드롭")
        self._tabs.addTab(Tab3_HyundaiHDS(), "⚙  커스텀 파싱")
        self._tabs.addTab(Tab3_HDS_Fixed(),  "🏢  장기계약팀 전용")
        self.setCentralWidget(self._tabs)

        self._theme_btn = QPushButton("🌙  다크 모드")
        self._theme_btn.setObjectName("theme_btn")
        self._theme_btn.setFixedHeight(26)
        self._theme_btn.clicked.connect(self._toggle_theme)

        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 8, 6)
        corner_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        corner_layout.addWidget(self._theme_btn)
        self._tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.statusBar().showMessage("준비")
        self._apply_theme()

    def _toggle_theme(self):
        self._theme = 'light' if self._theme == 'dark' else 'dark'
        self._apply_theme()

    def _apply_theme(self):
        t = DARK if self._theme == 'dark' else LIGHT
        QApplication.instance().setStyleSheet(build_stylesheet(t))
        self._theme_btn.setText("☀  라이트 모드" if self._theme == 'dark' else "🌙  다크 모드")


def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
