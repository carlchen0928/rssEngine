import requests
import zlib
from django.conf import settings
from socket import error as SocketError
from mongoengine.queryset import NotUniqueError
from vendor.readability import readability
from utils.feed_functions import timelimit, TimeoutError
import urllib2
from utils import log as logging
import httplib
from BeautifulSoup import BeautifulSoup
import traceback
from django.core.mail import mail_admins
import gzip, cStringIO

class TextImporter:

    def __init__(self, story, feed, request=None):
        self.story = story
        self.feed = feed
        self.request = request

    @property
    def headers(self):
        return {
            'User-Agent': 'NewsBlur Content Fetcher - %s subscriber%s - %s '
                          '(Mozilla/5.0 (Macintosh; Intel Mac OS X 10_7_1) '
                          'AppleWebKit/534.48.3 (KHTML, like Gecko) Version/5.1 '
                          'Safari/534.48.3)' % (
                self.feed.num_subscribers,
                's' if self.feed.num_subscribers != 1 else '',
                self.feed.permalink,
            ),
            'Connection': 'close',
        }

    def fetch(self, skip_save=False):
        #=====================
        #=Modified by SongJun=
        #=====================
        try:
            request = urllib2.Request(self.story.story_permalink,headers=self.headers)
            opener = urllib2.build_opener(urllib2.ProxyHandler({'http':settings.COW_PROXY_HANDLER,\
                                                                'https':settings.COW_PROXY_HANDLER}))
            #opener = urllib2.build_opener()
            text = opener.open(request).read()
            # logging.info(text)
            # Add by Xinyan Lu: some websites always return gzip files
            if text[:6] == '\x1f\x8b\x08\x00\x00\x00':
                text = gzip.GzipFile(fileobj = cStringIO.StringIO(text)).read()
        except httplib.IncompleteRead as e:
            text = e.partial
        except (Exception), e:
            logging.user(self.request, "~SN~FRFailed~FY to fetch ~FGoriginal text~FY: %s" % e)
            logging.error('error fetch_request'+str(e)+\
                # '  feed_id:'+str(self.story.story_feed_id)+\
                '  stroy_link:'+str(self.story.story_permalink))
            return
        finally:
            opener.close()

        if not text:
            logging.error('error fetch text: text is null')
            return
        #soup = BeautifulSoup(text)
        #text = soup.renderContents()
        try:
            original_text_doc = readability.Document(text, url=self.story.story_permalink)
            content = original_text_doc.summary(html_partial=True)
            print "the length of content: %s" % len(content)
            #content = content.encode("utf-8")
        except readability.Unparseable, e:
            logging.error('error getting summary: '+str(e)+\
                # '  feed_id:'+str(self.story.story_feed_id)+\
                '  stroy_link:'+str(self.story.story_permalink))
            # if settings.SEND_ERROR_MAILS:
            #     mail_admins("Error in text_importer Build Document",str(e)+\
            #         '  feed_id:'+str(self.story.story_feed_id)+\
            #         '  stroy_link:'+str(self.story.story_permalink)+\
            #         traceback.format_exc())
            return

        if len(content)<60:
            try:
                resp = self.fetch_request()
                text = None
            except TimeoutError:
                logging.user(self.request, "~SN~FRFailed~FY to fetch ~FGoriginal text~FY: timed out")
                resp = None
            except httplib.IncompleteRead as e:
                text = e.partial

            # if not resp:
            #     return
            if text:
                try:
                    text = resp.text
                except (LookupError, TypeError):
                    print 'error with resp.text'
                    text = resp.content

            #=====================
            #=modified by Songjun=
            #=====================

            # if resp.encoding and resp.encoding != 'utf-8':
            #     try:
            #         text = text.encode(resp.encoding)
            #     except (LookupError, UnicodeEncodeError):
            #         pass


            # print resp.encoding
            try:
                original_text_doc = readability.Document(text)
                content = original_text_doc.summary(html_partial=True)
                if resp.encoding and resp.encoding != 'utf-8':
                    try:
                        content = content.encode(resp.encoding,'xmlcharrefreplace')
                    except (LookupError, UnicodeEncodeError), e:
                        logging.user(self.request, "~SN~FRFailed~FY to encode ~FGcontent text~FY: %s , \
                            try to encode original text" % e)
                        try:
                            text = text.encode(resp.encoding)
                            original_text_doc = readability.Document(text)
                            content = original_text_doc.summary(html_partial=True)
                        except (LookupError, UnicodeEncodeError), e:
                            logging.user(self.request, "~SN~FRFailed~FY to encode ~FGoriginal_text text~FY: %s" % e)
                            pass
            except readability.Unparseable:
                print 'original readability error'
                return

        if content:
            if not skip_save:
                self.story.original_text = content
                self.story.save()
                self.story.original_text_z = zlib.compress(content)
                try:
                    self.story.save()
                except NotUniqueError:
                    print 'NotUniqueError'
                    pass
            logging.user(self.request, ("~SN~FYFetched ~FGoriginal text~FY: now ~SB%s bytes~SN vs. was ~SB%s bytes" % (
                len(content),
                self.story.story_content_z and len(zlib.decompress(self.story.story_content_z))
            )), warn_color=False)
        else:
            logging.user(self.request, ("~SN~FRFailed~FY to fetch ~FGoriginal text~FY: was ~SB%s bytes" % (
                self.story.story_content_z and len(zlib.decompress(self.story.story_content_z))
            )), warn_color=False)
        return content

    @timelimit(60)
    def fetch_request(self):
        try:
            proxies = {'http':settings.COW_PROXY_HANDLER,\
             'https':settings.COW_PROXY_HANDLER}
            r = requests.get(self.story.story_permalink, headers=self.headers, verify=False, proxies=proxies)
            #r = requests.get(self.story.story_permalink, headers=self.headers, verify=False)
        except (AttributeError, SocketError, requests.ConnectionError,
                requests.models.MissingSchema, requests.sessions.InvalidSchema), e:
            logging.user(self.request, "~SN~FRFailed~FY to fetch ~FGoriginal text~FY: %s" % e)
            logging.error('fetch_request with:ERROR \n'+str(e)+\
                '  feed_id:'+str(self.story.story_feed_id)+\
                '  stroy_link:'+str(self.story.story_permalink))
            if settings.SEND_ERROR_MAILS:
                mail_admins("Error in text_importer fetch_request",str(e)+'\n'+\
                    '  feed_id:'+str(self.story.story_feed_id)+'\n'+\
                    '  stroy_link:'+str(self.story.story_permalink)+'\n'+\
                    traceback.format_exc())
            return
        return r
