# book-for-study

| 书籍 | 格式 |
| --- | --- |
| 数字设计和计算机体系结构（RISC-V版） | PDF（原始扫描）、EPUB（适合阅读器） |

## EPUB 说明

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
