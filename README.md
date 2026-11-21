# book-for-study

| 书籍 | 格式 |
| --- | --- |
| 数字设计和计算机体系结构（RISC-V版） | PDF（原始扫描）、EPUB 文字版（手机阅读推荐）、EPUB 固定版式 |

## EPUB 文字版（推荐手机阅读）

`数字设计和计算机体系结构 (RISC-V版) 文字版.epub`：像电子小说一样可重排、字号可调、铺满屏幕。

- 对扫描页重新 OCR（MinerU），正文、标题、列表转为文字；页眉、页码、页边空白已去除
- 公式转为文字上下标（复杂公式用 MathML），电路图、时序图等保留为图片
- 表格转为可横向滚动的表格；代码示例保留原书图片，左右两栏改为上下排列，适合竖屏
- 按章、节生成目录；通过 EPUBCheck 校验
- 扫描识别难免有少量错字，遇到疑问可对照固定版式版或 PDF

## EPUB 固定版式说明

原 PDF 是扫描版（OCR 文字层错误较多，公式、电路图、时序图无法可靠转为文字），因此 EPUB 采用**固定版式（pre-paginated）**，保证公式与图表完全不失真：

- 去除扫描灰底、增强对比度，裁掉页边空白，手机/平板上字更大
- 完整的两级目录（章、节，共 133 项），可直接跳转；支持按纸书页码跳转（page-list）
- 黑白页使用 4 级灰度 PNG，含照片/灰底图的页用 16 级灰度，文件约 57 MB（原 PDF 232 MB）
- 通过 EPUBCheck 5.1（EPUB 3.3）校验，无错误/警告

推荐阅读器：Apple Books、Calibre、KOReader、Kobo、静读天下（Moon+ Reader）、Neat Reader 等。

## 重新生成

```bash
pip install pymupdf pillow numpy
python3 scripts/pdf_to_pages.py   # 处理页面图片 -> build/img
python3 scripts/build_epub.py     # 打包 EPUB
```

文字版：

```bash
pip install "mineru[core]==2.7.6" pymupdf pillow numpy rapidocr-onnxruntime latex2mathml wordninja
# 每 40 页一段做 OCR，输出目录名为起始页序号（如 p000、p040）
mineru -p p000.pdf -o out/p000 -b pipeline -l ch -m ocr
python3 scripts/reflow_epub.py "数字设计和计算机体系结构 (RISC-V版) 文字版.epub" chunks/p000 chunks/p040 ...
```
