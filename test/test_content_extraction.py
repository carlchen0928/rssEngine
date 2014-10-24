import requests
from vendor.readability import readability
import urllib2
from BeautifulSoup import BeautifulSoup
import httplib
import gzip, cStringIO


def headers():
    return {
        'User-Agent': 'NewsBlur Content Fetcher - %s subscriber%s - %s '
                      '(Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_1) '
                      'AppleWebKit/534.48.3 (KHTML, like Gecko) Version/5.1 '
                      'Safari/534.48.3)' % (
            10,
            's',
            'http://',
        ),
        'Connection': 'close',
    }

#url = "http://cn.engadget.com/2013/09/25/gold-samsung-galaxy-s4s/"
# url = 'http://go.rss.sina.com.cn/redirect.php?url=http://sports.sina.com.cn/cba/2013-12-22/19206948228.shtml'
# url = 'http://sports.sina.com.cn/cba/2013-12-22/19206948228.shtml'  #GZIP error
# url = 'http://www.douban.com/group/topic/47382118/'
# url = 'http://www.hi-pad.com/forum/viewthread.php?tid=1321679'
# url = 'http://www.ceconlinebbs.com/FORUM_POST_900001_900055_1058333_0.HTM?from=RSS'
# url = 'http://acqua.tumblr.com/post/70881960494'
url = 'http://blog.livedoor.jp/geek/archives/51422304.html'
print url
try:
  request = urllib2.Request(url,headers=headers())
  opener = urllib2.build_opener(urllib2.ProxyHandler({'http':'http://127.0.0.1:7777','https':'http://127.0.0.1:7777'}))
  text = opener.open(request).read()
  print 'hi'
  print len(text)
  if text[:6] == '\x1f\x8b\x08\x00\x00\x00':
    print 'GZIP'
    text = gzip.GzipFile(fileobj = cStringIO.StringIO(text)).read()
  # a=text.decode('gb2312')
  # print a[0:20]
except httplib.IncompleteRead as e:
    text = e.partial
# soup = BeautifulSoup(text)
# text = soup.renderContents()
if not text:
  print 'no text!'

doc = readability.Document(text)
content = doc.summary(html_partial=True)
print content


# httplib.HTTPConnection._http_vsn= 10 
# httplib.HTTPConnection._http_vsn_str = 'HTTP/1.0'
# proxies = {'http':'http://127.0.0.1:7777','https':'http://127.0.0.1:7777'}
# r = requests.get(url,proxies=proxies)
# print r.encoding
# t = r.text
# print type(t)
# d = readability.Document(t)
# c = d.summary(html_partial=True)
# c.encode(r.encoding)
# print type(c)