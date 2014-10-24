#!/usr/bin/python

import glob
import os
import sys
import time

from PIL import Image

EXTS = 'jpg', 'jpeg', 'JPG', 'JPEG', 'gif', 'GIF', 'png', 'PNG'

def avhash(im):
    if not isinstance(im, Image.Image):
        im = Image.open(im)
    im = im.resize((8, 8), Image.ANTIALIAS).convert('L')
    avg = reduce(lambda x, y: x + y, im.getdata()) / 64.
    return reduce(lambda x, (y, z): x | (z << y),
                  enumerate(map(lambda i: 0 if i < avg else 1, im.getdata())),
                  0)

def list_files():
    rootDir = '/home/udms/fastdfs_storage/data/'
    for root, dirs, files in os.walk(rootDir):
        for f in files: 
            if f.endswith('-m'):
                continue
            yield os.path.join(root,f) 
    

if __name__ == '__main__':
    num = 0
    codedict = {}
    start = time.time()
    for imgfile in list_files():
        try:
            h = avhash(imgfile)
            num += 1
            codedict[h] = codedict.get(h,0) + 1
            if num % 100 ==0:
                d = len(codedict.keys())
                print num,d,d*100.0/num
        except:
            print imgfile
            pass
    delta = time.time() - start
    print 'total images:',num
    print 'different images:',len(codedict.keys())
    print 'time:',delta
    #result:
    #total images: 224787
    # different images: 208584
    # ~92%
    # time: 8177.57365298