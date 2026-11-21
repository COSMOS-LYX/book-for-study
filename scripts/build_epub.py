import pymupdf, os, zipfile, uuid, datetime, html
REPO=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..'))
SRC=[os.path.join(REPO,f) for f in sorted(os.listdir(REPO)) if f.endswith('.pdf')][0]
IMG=OUT=os.path.join(REPO,'build','img')
from PIL import Image
OUTF=os.path.join(REPO,'数字设计和计算机体系结构 (RISC-V版).epub')
TITLE='数字设计和计算机体系结构（RISC-V版）'
AUTHORS=['Sarah L. Harris','David Harris']
OFFSET=15  # printed page 1 == PDF page 16
d=pymupdf.open(SRC); n=d.page_count; toc=d.get_toc()
bid='urn:uuid:'+str(uuid.uuid5(uuid.NAMESPACE_URL,'book-for-study/ddca-riscv-zh'))
now=datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
names=[f'p{i:04d}.jpg' if os.path.exists(f'{IMG}/p{i:04d}.jpg') else f'p{i:04d}.png' for i in range(1,n+1)]
sizes=[Image.open(f'{IMG}/{x}').size for x in names]
esc=html.escape
def page_label(i): return str(i-OFFSET) if i>OFFSET else None

def page_xhtml(i,w,h):
    lab=page_label(i)
    pb=f'<span epub:type="pagebreak" id="pg{lab}" role="doc-pagebreak" aria-label="{lab}"></span>' if lab else ''
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
<head><meta charset="UTF-8"/><title>{esc(TITLE)} - {i}</title>
<meta name="viewport" content="width={w}, height={h}"/>
<link rel="stylesheet" type="text/css" href="../css/page.css"/></head>
<body>{pb}<div class="page"><img src="../images/{names[i-1]}" alt="第 {lab or i} 页" width="{w}" height="{h}"/></div></body>
</html>'''

def nav_xhtml():
    out=[]; lvl=0
    for (l,t,p) in toc:
        if l>lvl:
            out.append('<ol>'*(l-lvl))
        else:
            out.append('</li>'+'</ol></li>'*(lvl-l))
        out.append(f'<li><a href="xhtml/p{p:04d}.xhtml">{esc(t)}</a>')
        lvl=l
    out.append('</li>'+'</ol></li>'*(lvl-1)+'</ol>')
    pl=''.join(f'<li><a href="xhtml/p{i:04d}.xhtml#pg{page_label(i)}">{page_label(i)}</a></li>' for i in range(OFFSET+1,n+1))
    lm=[('cover','封面',1),('toc','目录',11),('bodymatter','第1章 数字系统',16)]
    lms=''.join(f'<li><a epub:type="{t}" href="xhtml/p{p:04d}.xhtml">{x}</a></li>' for t,x,p in lm)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN" xml:lang="zh-CN">
<head><meta charset="UTF-8"/><title>目录</title></head>
<body>
<nav epub:type="toc" id="toc" role="doc-toc"><h1>目录</h1>{''.join(out)}</nav>
<nav epub:type="landmarks" hidden="hidden"><ol>{lms}</ol></nav>
<nav epub:type="page-list" hidden="hidden"><ol>{pl}</ol></nav>
</body></html>'''

def ncx():
    pts=[]; stack=[]; c=0; order={}
    for (l,t,p) in toc:
        while stack and stack[-1]>=l: pts.append('</navPoint>'); stack.pop()
        c+=1
        po=order.setdefault(p,len(order)+1)
        pts.append(f'<navPoint id="np{c}" playOrder="{po}"><navLabel><text>{esc(t)}</text></navLabel><content src="xhtml/p{p:04d}.xhtml"/>')
        stack.append(l)
    pts+=['</navPoint>']*len(stack)
    depth=max(l for l,_,_ in toc)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-CN">
<head><meta name="dtb:uid" content="{bid}"/><meta name="dtb:depth" content="{depth}"/><meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>
<docTitle><text>{esc(TITLE)}</text></docTitle><navMap>{''.join(pts)}</navMap></ncx>'''

def opf():
    w0,h0=max(s[0] for s in sizes),max(s[1] for s in sizes)
    man=['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
         '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
         '<item id="css" href="css/page.css" media-type="text/css"/>']
    spine=[]
    for i in range(1,n+1):
        mt='jpeg' if names[i-1].endswith('jpg') else 'png'; cp=' properties="cover-image"' if i==1 else ''
        man.append(f'<item id="img{i:04d}" href="images/{names[i-1]}" media-type="image/{mt}"{cp}/>')
        man.append(f'<item id="p{i:04d}" href="xhtml/p{i:04d}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="p{i:04d}"/>')
    auth=''.join(f'<dc:creator id="a{k}">{a}</dc:creator>' for k,a in enumerate(AUTHORS))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="zh-CN" prefix="rendition: http://www.idpf.org/vocab/rendition/#">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{bid}</dc:identifier>
<dc:title>{esc(TITLE)}</dc:title>{auth}
<dc:contributor>张功萱 等（译）</dc:contributor>
<dc:language>zh-CN</dc:language>
<dc:subject>数字设计</dc:subject><dc:subject>计算机体系结构</dc:subject><dc:subject>RISC-V</dc:subject>
<meta property="dcterms:modified">{now}</meta>
<meta property="rendition:layout">pre-paginated</meta>
<meta property="rendition:orientation">auto</meta>
<meta property="rendition:spread">none</meta>
<meta name="cover" content="img0001"/>
<meta name="fixed-layout" content="true"/>
<meta name="original-resolution" content="{w0}x{h0}"/>
<meta name="book-type" content="comic"/>
<meta name="zero-gutter" content="true"/><meta name="zero-margin" content="true"/>
</metadata>
<manifest>{''.join(man)}</manifest>
<spine toc="ncx" page-progression-direction="ltr">{''.join(spine)}</spine>
</package>'''

CSS='''@page{margin:0}
html,body{margin:0;padding:0;background:#fff}
.page{margin:0;padding:0}
img{display:block;margin:0;padding:0;width:100%;height:auto}
'''
CONTAINER='''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'''
with zipfile.ZipFile(OUTF,'w') as z:
    z.writestr(zipfile.ZipInfo('mimetype'),'application/epub+zip',compress_type=zipfile.ZIP_STORED)
    D=zipfile.ZIP_DEFLATED
    z.writestr('META-INF/container.xml',CONTAINER,D)
    z.writestr('OEBPS/content.opf',opf(),D)
    z.writestr('OEBPS/nav.xhtml',nav_xhtml(),D)
    z.writestr('OEBPS/toc.ncx',ncx(),D)
    z.writestr('OEBPS/css/page.css',CSS,D)
    for i in range(1,n+1):
        w,h=sizes[i-1]
        z.writestr(f'OEBPS/xhtml/p{i:04d}.xhtml',page_xhtml(i,w,h),D)
        z.write(f'{IMG}/{names[i-1]}',f'OEBPS/images/{names[i-1]}',zipfile.ZIP_STORED)
print(OUTF, os.path.getsize(OUTF)/1e6,'MB')
