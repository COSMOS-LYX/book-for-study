import pymupdf, os, io, sys
REPO=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..'))
SRC=[os.path.join(REPO,f) for f in sorted(os.listdir(REPO)) if f.endswith('.pdf')][0]
IMG=OUT=os.path.join(REPO,'build','img')
import numpy as np
from PIL import Image, ImageOps
from multiprocessing import Pool
os.makedirs(OUT,exist_ok=True)
MAXW=1300  # 输出页宽(px)

def process(i):
    d=pymupdf.open(SRC)
    pg=d[i]
    x=pg.get_images(full=True)[0][0]
    im=Image.open(io.BytesIO(d.extract_image(x)['image'])).convert('RGB')
    a=np.asarray(im).astype(np.int16)
    sat=(a.max(2)-a.min(2))
    color = i==0 or (sat>60).mean()>0.02
    g=np.asarray(im.convert('L')).astype(np.float32)
    white=np.percentile(g,75)
    black=min(np.percentile(g,0.5),white-80)
    def lev(arr):
        arr=(arr-black)/(white-black-10)
        arr=np.clip(arr,0,1)**1.15
        return (arr*255).astype(np.uint8)
    if color:
        out=Image.fromarray(lev(np.asarray(im).astype(np.float32)))
        gl=np.asarray(out.convert('L'))
    else:
        gl=lev(g); out=Image.fromarray(gl)
    if i>0:
        dark=gl<150
        h,w=dark.shape
        rows=np.where(dark.mean(1)>0.003)[0]; cols=np.where(dark.mean(0)>0.003)[0]
        if len(rows) and len(cols):
            pad=int(0.03*w)
            y0=max(rows[0]-pad,0); y1=min(rows[-1]+pad,h); x0=max(cols[0]-pad,0); x1=min(cols[-1]+pad,w)
            if (y1-y0)>0.5*h and (x1-x0)>0.5*w:
                out=out.crop((x0,y0,x1,y1))
    if out.width>MAXW:
        out=out.resize((MAXW,round(out.height*MAXW/out.width)),Image.LANCZOS)
    if color:
        p=f'{OUT}/p{i+1:04d}.jpg'
        out.save(p,quality=80,optimize=True,progressive=True)
    else:
        a=np.asarray(out)
        h,w=a.shape; hh=h-h%16; ww=w-w%16
        m=((a[:hh,:ww]>60)&(a[:hh,:ww]<200)).reshape(hh//16,16,ww//16,16).mean((1,3))
        bits=4 if (m>0.6).mean()>0.01 else 2
        L=2**bits
        q=(np.round(a/255*(L-1))*(255//(L-1))).astype(np.uint8)
        p=f'{OUT}/p{i+1:04d}.png'
        Image.fromarray(q).quantize(L).save(p,optimize=True,bits=bits)
    return i,out.size,color,os.path.getsize(p)

if __name__=='__main__':
    n=pymupdf.open(SRC).page_count
    pages=[int(x) for x in sys.argv[1:]] or range(n)
    with Pool(8) as p:
        res=p.map(process,pages)
    tot=sum(r[3] for r in res)
    print('total MB',tot/1e6, 'color pages',[r[0] for r in res if r[2]])
    for r in res[:10]: print(r)
