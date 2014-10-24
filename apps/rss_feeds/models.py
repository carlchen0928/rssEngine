import difflib
import datetime
import time
import random
import re
import math
import mongoengine as mongo
import zlib
import hashlib
import redis
import pymongo
import sys
from collections import defaultdict
from operator import itemgetter
from bson.objectid import ObjectId
from BeautifulSoup import BeautifulSoup
# from nltk.collocations import TrigramCollocationFinder, BigramCollocationFinder, TrigramAssocMeasures, BigramAssocMeasures
from django.db import models
from django.db import IntegrityError
from django.conf import settings
from django.db.models.query import QuerySet
from django.core.urlresolvers import reverse
# from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.template.defaultfilters import slugify
from mongoengine.queryset import OperationError, Q, NotUniqueError
from mongoengine.base import ValidationError
from vendor.timezones.utilities import localtime_for_timezone
from apps.rss_feeds.tasks import UpdateFeeds, PushFeeds
from apps.rss_feeds.text_importer import TextImporter
# from apps.search.models import SearchStarredStory, SearchFeed
# from apps.statistics.rstats import RStats
# from utils import json_functions as json
from utils import feedfinder, feedparser
from utils import urlnorm
from utils import log as logging
# from utils.fields import AutoOneToOneField
from utils.feed_functions import levenshtein_distance
from utils.feed_functions import timelimit, TimeoutError
from utils.feed_functions import relative_timesince
from utils.feed_functions import seconds_timesince
from utils.story_functions import strip_tags, htmldiff, strip_comments, strip_comments__lxml
import pytz
# from vendor.haystack.query import SearchQuerySet
from apps.search.models import SearchStory
from fdfs_client.client import Fdfs_client,DataError
from PIL import Image
import cStringIO
import urllib2
import traceback
# import gevent
# from gevent import monkey
# monkey.patch_all()  # gevent monkey patch
from django.core.mail import mail_admins
from utils.image_url_filters import IMAGE_BLACKLIST_FILTERS



# all the encode and decode functions in this file are added for supporting Unicode

ENTRY_NEW, ENTRY_UPDATED, ENTRY_SAME, ENTRY_ERR = range(4)


class Feed(models.Model):
    feed_address = models.URLField(max_length=764, db_index=True)
    feed_address_locked = models.NullBooleanField(
        default=False, blank=True, null=True)
    feed_link = models.URLField(
        max_length=1000, default="", blank=True, null=True)
    feed_link_locked = models.BooleanField(default=False)
    hash_address_and_link = models.CharField(max_length=64, unique=True)
    feed_title = models.CharField(
        max_length=255, default="[Untitled]", blank=True, null=True)
    is_push = models.NullBooleanField(default=False, blank=True, null=True)
    active = models.BooleanField(default=True, db_index=True)
    num_subscribers = models.IntegerField(default=-1)
    active_subscribers = models.IntegerField(default=-1, db_index=True)
    premium_subscribers = models.IntegerField(default=-1)
    active_premium_subscribers = models.IntegerField(default=-1)
    branch_from_feed = models.ForeignKey(
        'Feed', blank=True, null=True, db_index=True)
    last_update = models.DateTimeField(db_index=True)
    next_scheduled_update = models.DateTimeField()
    last_story_date = models.DateTimeField(null=True, blank=True)
    fetched_once = models.BooleanField(default=False)
    known_good = models.BooleanField(default=False)
    has_feed_exception = models.BooleanField(default=False, db_index=True)
    has_page_exception = models.BooleanField(default=False, db_index=True)
    has_page = models.BooleanField(default=True)
    exception_code = models.IntegerField(default=0)
    errors_since_good = models.IntegerField(default=0)
    min_to_decay = models.IntegerField(default=0)
    days_to_trim = models.IntegerField(default=90)
    creation = models.DateField(auto_now_add=True)
    etag = models.CharField(max_length=255, blank=True, null=True)
    last_modified = models.DateTimeField(null=True, blank=True)
    stories_last_month = models.IntegerField(default=0)
    average_stories_per_month = models.IntegerField(default=0)
    last_load_time = models.IntegerField(default=0)
    favicon_color = models.CharField(max_length=6, null=True, blank=True)
    favicon_not_found = models.BooleanField(default=False)
    s3_page = models.NullBooleanField(default=False, blank=True, null=True)
    s3_icon = models.NullBooleanField(default=False, blank=True, null=True)

    class Meta:
        db_table = "feeds"
        ordering = ["feed_title"]
        # unique_together=[('feed_address', 'feed_link')]

    def __unicode__(self):
        if not self.feed_title:
            self.feed_title = "[Untitled]"
            self.save()
        return "%s (%s - %s/%s/%s)%s" % (
            self.feed_title,
            self.pk,
            self.num_subscribers,
            self.active_subscribers,
            self.active_premium_subscribers,
            (" [B: %s]" % self.branch_from_feed.pk if self.branch_from_feed else ""))

    @property
    def title(self):
        return self.feed_title or "[Untitled]"

    @property
    def permalink(self):
        return "%s/site/%s/%s" % (settings.NEWSBLUR_URL, self.pk, slugify(self.feed_title.lower()[:50]))

    @property
    def favicon_url(self):
        if settings.BACKED_BY_AWS['icons_on_s3'] and self.s3_icon:
            return "http://%s/%s.png" % (settings.S3_ICONS_BUCKET_NAME, self.pk)
        return reverse('feed-favicon', kwargs={'feed_id': self.pk})

    @property
    def favicon_url_fqdn(self):
        if settings.BACKED_BY_AWS['icons_on_s3'] and self.s3_icon:
            return self.favicon_url
        return "http://%s%s" % (
            Site.objects.get_current().domain,
            self.favicon_url
        )

    @property
    def s3_pages_key(self):
        return "%s.gz.html" % self.pk

    @property
    def s3_icons_key(self):
        return "%s.png" % self.pk

    def canonical(self, full=False, include_favicon=True):
        feed = {
            'id': self.pk,
            'feed_title': self.feed_title,
            'feed_address': self.feed_address,
            'feed_link': self.feed_link,
            'num_subscribers': self.num_subscribers,
            'updated': relative_timesince(self.last_update),
            'updated_seconds_ago': seconds_timesince(self.last_update),
            'min_to_decay': self.min_to_decay,
            'subs': self.num_subscribers,
            'is_push': self.is_push,
            'fetched_once': self.fetched_once,
            'not_yet_fetched': not self.fetched_once,  # Legacy. Doh.
            'favicon_color': self.favicon_color,
            'favicon_fade': self.favicon_fade(),
            'favicon_border': self.favicon_border(),
            'favicon_text_color': self.favicon_text_color(),
            'favicon_fetching': self.favicon_fetching,
            'favicon_url': self.favicon_url,
            's3_page': self.s3_page,
            's3_icon': self.s3_icon,
        }

        if include_favicon:
            try:
                feed_icon = MFeedIcon.objects.get(feed_id=self.pk)
                feed['favicon'] = feed_icon.data
            except MFeedIcon.DoesNotExist:
                pass
        if self.has_page_exception or self.has_feed_exception:
            feed['has_exception'] = True
            feed[
                'exception_type'] = 'feed' if self.has_feed_exception else 'page'
            feed['exception_code'] = self.exception_code
        elif full:
            feed['has_exception'] = False
            feed['exception_type'] = None
            feed['exception_code'] = self.exception_code

        if not self.has_page:
            feed['disabled_page'] = True
        if full:
            feed['average_stories_per_month'] = self.average_stories_per_month
            # Deleted by Xinyan Lu : No this table
            # feed['tagline'] = self.data.feed_tagline
            # feed['feed_tags'] = json.decode(
            #     self.data.popular_tags) if self.data.popular_tags else []
            # feed['feed_authors'] = json.decode(
            #     self.data.popular_authors) if self.data.popular_authors else []

        return feed

    def save(self, *args, **kwargs):
        if not self.last_update:
            self.last_update = datetime.datetime.utcnow()
        if not self.next_scheduled_update:
            self.next_scheduled_update = datetime.datetime.utcnow()
        self.fix_google_alerts_urls()

        feed_address = self.feed_address or ""
        feed_link = self.feed_link or ""
        try:
            self.hash_address_and_link = hashlib.sha1(
                feed_address + feed_link).hexdigest()
        except:
            logging.debug(" ---> ~FRFeed save DECODE ERROR (%s)" % feed_address + feed_link)
            pass

        max_feed_title = Feed._meta.get_field('feed_title').max_length
        if len(self.feed_title) > max_feed_title:
            self.feed_title = self.feed_title[:max_feed_title]
        max_feed_address = Feed._meta.get_field('feed_address').max_length
        if len(feed_address) > max_feed_address:
            self.feed_address = feed_address[:max_feed_address]
        max_feed_link = Feed._meta.get_field('feed_link').max_length
        if len(feed_link) > max_feed_link:
            self.feed_link = feed_link[:max_feed_link]

        try:
            super(Feed, self).save(*args, **kwargs)
        except IntegrityError, e:
            logging.debug(
                " ---> ~FRFeed save collision (%s), checking dupe..." % e)
            duplicate_feeds = Feed.objects.filter(
                feed_address=self.feed_address,
                feed_link=self.feed_link)
            if not duplicate_feeds:
                feed_address = self.feed_address or ""
                feed_link = self.feed_link or ""
                hash_address_and_link = hashlib.sha1(
                    feed_address + feed_link).hexdigest()
                duplicate_feeds = Feed.objects.filter(
                    hash_address_and_link=hash_address_and_link)
            if not duplicate_feeds:
                # Feed has been deleted. Just ignore it.
                logging.debug(" ***> Changed to: %s - %s: %s" %
                              (self.feed_address, self.feed_link, duplicate_feeds))
                logging.debug(
                    ' ***> [%-30s] Feed deleted (%s).' % (unicode(self)[:30], self.pk))
                return

            if self.pk != duplicate_feeds[0].pk:
                logging.debug(
                    " ---> ~FRFound different feed (%s), merging..." % duplicate_feeds[0])
                feed = Feed.get_by_id(
                    merge_feeds(duplicate_feeds[0].pk, self.pk))
                return feed

        return self

    def index_for_search(self):
        if self.num_subscribers > 1 and not self.branch_from_feed:
            SearchFeed.index(feed_id=self.pk,
                             title=self.feed_title,
                             address=self.feed_address,
                             link=self.feed_link,
                             num_subscribers=self.num_subscribers)

    def sync_redis(self):
        return MStory.sync_feed_redis(self.pk)

    def expire_redis(self, r=None):
        # Disabled by Xinyan Lu: no read cutoff
        return
        if not r:
            r = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL)
        # if not r2:
            # r2 = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL2)

        r.expire('F:%s' % self.pk, settings.DAYS_OF_UNREAD_NEW * 24 * 60 * 60)
        # r2.expire('F:%s' % self.pk, settings.DAYS_OF_UNREAD_NEW*24*60*60)
        r.expire('zF:%s' % self.pk, settings.DAYS_OF_UNREAD_NEW * 24 * 60 * 60)
        # r2.expire('zF:%s' % self.pk, settings.DAYS_OF_UNREAD_NEW*24*60*60)

    @classmethod
    def autocomplete(self, prefix, limit=5):
        results = SearchQuerySet().autocomplete(
            address=prefix).order_by('-num_subscribers')[:limit]

        if len(results) < limit:
            results += SearchQuerySet().autocomplete(
                title=prefix).order_by('-num_subscribers')[:limit - len(results)]

        return list(set([int(f.pk) for f in results]))

    @classmethod
    def find_or_create(cls, feed_address, feed_link, *args, **kwargs):
        feeds = cls.objects.filter(
            feed_address=feed_address, feed_link=feed_link)
        if feeds:
            return feeds[0], False

        if feed_link and feed_link.endswith('/'):
            feeds = cls.objects.filter(
                feed_address=feed_address, feed_link=feed_link[:-1])
            if feeds:
                return feeds[0], False
        return cls.objects.get_or_create(feed_address=feed_address, feed_link=feed_link, *args, **kwargs)


    @classmethod
    def merge_feeds(cls, *args, **kwargs):
        return merge_feeds(*args, **kwargs)

    def fix_google_alerts_urls(self):
        if (self.feed_address.startswith('http://user/') and
            '/state/com.google/alerts/' in self.feed_address):
            match = re.match(
                r"http://user/(\d+)/state/com.google/alerts/(\d+)", self.feed_address)
            if match:
                user_id, alert_id = match.groups()
                self.feed_address = "http://www.google.com/alerts/feeds/%s/%s" % (
                    user_id, alert_id)

    @classmethod
    def schedule_feed_fetches_immediately(cls, feed_ids):
        if settings.DEBUG:
            logging.info(
                " ---> ~SN~FMSkipping the scheduling immediate fetch of ~SB%s~SN feeds (in DEBUG)..." %
                len(feed_ids))
            return
        logging.info(
            " ---> ~SN~FMScheduling immediate fetch of ~SB%s~SN feeds..." %
            len(feed_ids))

        feeds = Feed.objects.filter(pk__in=feed_ids)
        for feed in feeds:
            feed.count_subscribers()
            feed.schedule_feed_fetch_immediately(verbose=False)

    @property
    def favicon_fetching(self):
        return bool(not (self.favicon_not_found or self.favicon_color))

    @classmethod
    def get_feed_from_url(cls, url, create=True, aggressive=False, fetch=True, offset=0):
        feed = None

        def criteria(key, value):
            if aggressive:
                return {'%s__icontains' % key: value}
            else:
                return {'%s' % key: value}

        def by_url(address):
            feed = cls.objects.filter(
                branch_from_feed=None
            ).filter(**criteria('feed_address', address)).order_by('-num_subscribers')
            # Deleted by Xinyan Lu : No DuplicateFeed currently
            # if not feed:
            #     duplicate_feed = DuplicateFeed.objects.filter(
            #         **criteria('duplicate_address', address))
            #     if duplicate_feed and len(duplicate_feed) > offset:
            #         feed = [duplicate_feed[offset].feed]
            if not feed and aggressive:
                feed = cls.objects.filter(
                    branch_from_feed=None
                ).filter(**criteria('feed_link', address)).order_by('-num_subscribers')

            return feed

        # Normalize and check for feed_address, dupes, and feed_link
        url = urlnorm.normalize(url)
        feed = by_url(url)

        # Create if it looks good
        if feed and len(feed) > offset:
            feed = feed[offset]
        elif create:
            create_okay = False
            if feedfinder.isFeed(url):
                create_okay = True
            elif fetch:
                # Could still be a feed. Just check if there are entries
                fp = feedparser.parse(url)
                if len(fp.entries):
                    create_okay = True
            if create_okay:
                feed = cls.objects.create(feed_address=url)
                feed = feed.update()

        # Still nothing? Maybe the URL has some clues.
        if not feed and fetch:
            feed_finder_url = feedfinder.feed(url)
            if feed_finder_url and 'comments' not in feed_finder_url:
                feed = by_url(feed_finder_url)
                if not feed and create:
                    feed = cls.objects.create(feed_address=feed_finder_url)
                    feed = feed.update()
                elif feed and len(feed) > offset:
                    feed = feed[offset]

        # Not created and not within bounds, so toss results.
        if isinstance(feed, QuerySet):
            return

        return feed

    @classmethod
    def task_feeds(cls, feeds, queue_size=12, verbose=True):
        if not feeds:
            return
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)

        if isinstance(feeds, Feed):
            if verbose:
                logging.debug(" ---> ~SN~FBTasking feed: ~SB%s" % feeds)
            feeds = [feeds.pk]
        elif verbose:
            logging.debug(" ---> ~SN~FBTasking ~SB%s~SN feeds..." % len(feeds))

        if isinstance(feeds, QuerySet):
            feeds = [f.pk for f in feeds]

        r.srem('queued_feeds', *feeds)
        now = datetime.datetime.now().strftime("%s")
        p = r.pipeline()
        for feed_id in feeds:
            p.zadd('tasked_feeds', feed_id, now)
        p.execute()

        # for feed_ids in (feeds[pos:pos + queue_size] for pos in xrange(0,
        # len(feeds), queue_size)):
        for feed_id in feeds:
            UpdateFeeds.apply_async(args=(feed_id,), queue='update_feeds')

    @classmethod
    def drain_task_feeds(cls, empty=False):
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        if not empty:
            tasked_feeds = r.zrange('tasked_feeds', 0, -1)
            logging.debug(" ---> ~FRDraining %s feeds..." % len(tasked_feeds))
            r.sadd('queued_feeds', *tasked_feeds)
        r.zremrangebyrank('tasked_feeds', 0, -1)

    def update_all_statistics(self, full=True, force=False):
        self.count_subscribers()
        self.calculate_last_story_date()

        # Deleted by Xinyan Lu : No this table
        # count_extra = False
        # if random.random() > .99 or not self.data.popular_tags or not self.data.popular_authors:
        #     count_extra = True

        if force or full:
            self.save_feed_stories_last_month()

        # Deleted by Xinyan Lu : No this table
        # if force or (full and count_extra):
        #     self.save_popular_authors()
        #     self.save_popular_tags()
        #     self.save_feed_story_history_statistics()

    def calculate_last_story_date(self):
        last_story_date = None

        try:
            latest_story = MStory.objects(
                story_feed_id=self.pk
            ).limit(1).order_by('-story_date').only('story_date').first()
            if latest_story:
                last_story_date = latest_story.story_date
        except MStory.DoesNotExist:
            pass

        if not last_story_date or seconds_timesince(last_story_date) < 0:
            last_story_date = datetime.datetime.now()

        self.last_story_date = last_story_date
        self.save()

    @classmethod
    def setup_feeds_for_premium_subscribers(cls, feed_ids):
        logging.info(
            " ---> ~SN~FMScheduling immediate premium setup of ~SB%s~SN feeds..." %
            len(feed_ids))

        feeds = Feed.objects.filter(pk__in=feed_ids)
        for feed in feeds:
            feed.setup_feed_for_premium_subscribers()

    def setup_feed_for_premium_subscribers(self):
        self.count_subscribers()
        self.set_next_scheduled_update()

    def check_feed_link_for_feed_address(self):
        @timelimit(10)
        def _1():
            feed_address = None
            feed = self
            try:
                is_feed = feedfinder.isFeed(self.feed_address)
            except KeyError:
                is_feed = False
            if not is_feed:
                feed_address = feedfinder.feed(self.feed_address)
                if not feed_address and self.feed_link:
                    feed_address = feedfinder.feed(self.feed_link)
            else:
                feed_address_from_link = feedfinder.feed(self.feed_link)
                if feed_address_from_link != self.feed_address:
                    feed_address = feed_address_from_link

            if feed_address:
                if (feed_address.endswith('feedburner.com/atom.xml') or
                    feed_address.endswith('feedburner.com/feed/')):
                    logging.debug("  ---> Feed points to 'Wierdo', ignoring.")
                    return False, self
                try:
                    self.feed_address = feed_address
                    feed = self.save()
                    feed.schedule_feed_fetch_immediately()
                    feed.has_feed_exception = False
                    feed.active = True
                    feed = feed.save()
                except IntegrityError:
                    original_feed = Feed.objects.get(
                        feed_address=feed_address, feed_link=self.feed_link)
                    original_feed.has_feed_exception = False
                    original_feed.active = True
                    original_feed.save()
                    merge_feeds(original_feed.pk, self.pk)
            return feed_address, feed

        if self.feed_address_locked:
            return False, self

        try:
            feed_address, feed = _1()
        except TimeoutError, e:
            logging.debug(
                '   ---> [%-30s] Feed address check timed out...' % (unicode(self)[:30]))
            self.save_feed_history(505, 'Timeout', e)
            feed = self
            feed_address = None

        return bool(feed_address), feed

    def save_feed_history(self, status_code, message, exception=None):
        fetch_history = MFetchHistory.add(feed_id=self.pk,
                                          fetch_type='feed',
                                          code=int(status_code),
                                          message=message,
                                          exception=exception)

        if status_code not in (200, 304):
            self.errors_since_good += 1
            self.count_errors_in_history(
                'feed', status_code, fetch_history=fetch_history)
            self.set_next_scheduled_update()
        elif self.has_feed_exception or self.errors_since_good:
            self.errors_since_good = 0
            self.has_feed_exception = False
            self.active = True
            self.save()

    def save_page_history(self, status_code, message, exception=None):
        fetch_history = MFetchHistory.add(feed_id=self.pk,
                                          fetch_type='page',
                                          code=int(status_code),
                                          message=message,
                                          exception=exception)

        if status_code not in (200, 304):
            self.count_errors_in_history(
                'page', status_code, fetch_history=fetch_history)
        elif self.has_page_exception or not self.has_page:
            self.has_page_exception = False
            self.has_page = True
            self.active = True
            self.save()

    def count_errors_in_history(self, exception_type='feed', status_code=None, fetch_history=None):
        logging.debug(
            '   ---> [%-30s] Counting errors in history...' % (unicode(self)[:30]))
        if not fetch_history:
            fetch_history = MFetchHistory.feed(self.pk)
        fh = fetch_history[exception_type + '_fetch_history']
        non_errors = [h for h in fh if h['status_code']
                      and int(h['status_code']) in (200, 304)]
        errors = [h for h in fh if h['status_code']
                  and int(h['status_code']) not in (200, 304)]

        if len(non_errors) == 0 and len(errors) > 1:
            self.active = True
            if exception_type == 'feed':
                self.has_feed_exception = True
                # self.active = False # No longer, just geometrically fetch
            elif exception_type == 'page':
                self.has_page_exception = True
            self.exception_code = status_code or int(errors[0])
            self.save()
        elif self.exception_code > 0:
            self.active = True
            self.exception_code = 0
            if exception_type == 'feed':
                self.has_feed_exception = False
            elif exception_type == 'page':
                self.has_page_exception = False
            self.save()

        return errors, non_errors

    def count_subscribers(self, verbose=False):
        pass
    # Deleted By Xinyan Lu : number of subscribers no more updated
    #     SUBSCRIBER_EXPIRE = datetime.datetime.now() - datetime.timedelta(
    #         days=settings.SUBSCRIBER_EXPIRE)
    #     from apps.reader.models import UserSubscription

    #     if self.branch_from_feed:
    #         original_feed_id = self.branch_from_feed.pk
    #     else:
    #         original_feed_id = self.pk
    #     feed_ids = [f['id']
    #                 for f in Feed.objects.filter(branch_from_feed=original_feed_id).values('id')]
    #     feed_ids.append(original_feed_id)
    #     feed_ids = list(set(feed_ids))

    #     subs = UserSubscription.objects.filter(feed__in=feed_ids)
    #     self.num_subscribers = subs.count()

    #     active_subs = UserSubscription.objects.filter(
    #         feed__in=feed_ids,
    #         active=True,
    #         user__profile__last_seen_on__gte=SUBSCRIBER_EXPIRE
    #     )
    #     self.active_subscribers = active_subs.count()

    #     premium_subs = UserSubscription.objects.filter(
    #         feed__in=feed_ids,
    #         active=True,
    #         user__profile__is_premium=True
    #     )
    #     self.premium_subscribers = premium_subs.count()

    #     active_premium_subscribers = UserSubscription.objects.filter(
    #         feed__in=feed_ids,
    #         active=True,
    #         user__profile__is_premium=True,
    #         user__profile__last_seen_on__gte=SUBSCRIBER_EXPIRE
    #     )
    #     self.active_premium_subscribers = active_premium_subscribers.count()

    #     self.save()

    #     if verbose:
    #         if self.num_subscribers <= 1:
    #             print '.',
    #         else:
    #             print "\n %s> %s subscriber%s: %s" % (
    #                 '-' * min(self.num_subscribers, 20),
    #                 self.num_subscribers,
    #                 '' if self.num_subscribers == 1 else 's',
    #                 self.feed_title,
    #             ),

    def _split_favicon_color(self):
        color = self.favicon_color
        if color:
            splitter = lambda s, p: [s[i:i + p] for i in range(0, len(s), p)]
            red, green, blue = splitter(color[:6], 2)
            return red, green, blue
        return None, None, None

    def favicon_fade(self):
        red, green, blue = self._split_favicon_color()
        if red and green and blue:
            fade_red = hex(min(int(red, 16) + 35, 255))[2:].zfill(2)
            fade_green = hex(min(int(green, 16) + 35, 255))[2:].zfill(2)
            fade_blue = hex(min(int(blue, 16) + 35, 255))[2:].zfill(2)
            return "%s%s%s" % (fade_red, fade_green, fade_blue)

    def favicon_border(self):
        red, green, blue = self._split_favicon_color()
        if red and green and blue:
            fade_red = hex(min(int(int(red, 16) * .75), 255))[2:].zfill(2)
            fade_green = hex(min(int(int(green, 16) * .75), 255))[2:].zfill(2)
            fade_blue = hex(min(int(int(blue, 16) * .75), 255))[2:].zfill(2)
            return "%s%s%s" % (fade_red, fade_green, fade_blue)

    def favicon_text_color(self):
        # Color format: {r: 1, g: .5, b: 0}
        def contrast(color1, color2):
            lum1 = luminosity(color1)
            lum2 = luminosity(color2)
            if lum1 > lum2:
                return (lum1 + 0.05) / (lum2 + 0.05)
            else:
                return (lum2 + 0.05) / (lum1 + 0.05)

        def luminosity(color):
            r = color['red']
            g = color['green']
            b = color['blue']
            val = lambda c: c / \
                12.92 if c <= 0.02928 else math.pow(((c + 0.055) / 1.055), 2.4)
            red = val(r)
            green = val(g)
            blue = val(b)
            return 0.2126 * red + 0.7152 * green + 0.0722 * blue

        red, green, blue = self._split_favicon_color()
        if red and green and blue:
            color = {
                'red': int(red, 16) / 256.0,
                'green': int(green, 16) / 256.0,
                'blue': int(blue, 16) / 256.0,
            }
            white = {
                'red': 1,
                'green': 1,
                'blue': 1,
            }
            grey = {
                'red': 0.5,
                'green': 0.5,
                'blue': 0.5,
            }

            if contrast(color, white) > contrast(color, grey):
                return 'white'
            else:
                return 'black'

    def save_feed_stories_last_month(self, verbose=False):
        month_ago = datetime.datetime.utcnow() - datetime.timedelta(days=30)
        stories_last_month = MStory.objects(story_feed_id=self.pk,
                                            story_date__gte=month_ago).count()
        self.stories_last_month = stories_last_month

        self.save()

        if verbose:
            print "  ---> %s [%s]: %s stories last month" % (self.feed_title, self.pk,
                                                             self.stories_last_month)

    # Deleted by Xinyan Lu : No this table
    # def save_feed_story_history_statistics(self, current_counts=None):
    #     """
    #     Fills in missing months between earlier occurances and now.

    #     Save format: [('YYYY-MM, #), ...]
    #     Example output: [(2010-12, 123), (2011-01, 146)]
    #     """
    #     now = datetime.datetime.utcnow()
    #     min_year = now.year
    #     total = 0
    #     month_count = 0
    #     if not current_counts:
    #         current_counts = self.data.story_count_history and json.decode(
    #             self.data.story_count_history)

    #     if isinstance(current_counts, dict):
    #         current_counts = current_counts['months']

    #     if not current_counts:
    #         current_counts = []

    #     # Count stories, aggregate by year and month. Map Reduce!
    #     map_f = """
    #         function() {
    #             var date = (this.story_date.getFullYear()) + "-" + (this.story_date.getMonth()+1);
    #             emit(date, 1);
    #         }
    #     """
    #     reduce_f = """
    #         function(key, values) {
    #             var total = 0;
    #             for (var i=0; i < values.length; i++) {
    #                 total += values[i];
    #             }
    #             return total;
    #         }
    #     """
    #     dates = {}
    #     res = MStory.objects(story_feed_id=self.pk).map_reduce(
    #         map_f, reduce_f, output='inline')
    #     for r in res:
    #         dates[r.key] = r.value
    #         year = int(re.findall(r"(\d{4})-\d{1,2}", r.key)[0])
    #         if year < min_year and year > 2000:
    #             min_year = year

    #     # Add on to existing months, always amending up, never down. (Current month
    #     # is guaranteed to be accurate, since trim_feeds won't delete it until after
    #     # a month. Hacker News can have 1,000+ and still be counted.)
    #     for current_month, current_count in current_counts:
    #         year = int(re.findall(r"(\d{4})-\d{1,2}", current_month)[0])
    #         if current_month not in dates or dates[current_month] < current_count:
    #             dates[current_month] = current_count
    #         if year < min_year and year > 2000:
    #             min_year = year

    #     # Assemble a list with 0's filled in for missing months,
    #     # trimming left and right 0's.
    #     months = []
    #     start = False
    #     for year in range(min_year, now.year + 1):
    #         for month in range(1, 12 + 1):
    #             if datetime.datetime(year, month, 1) < now:
    #                 key = u'%s-%s' % (year, month)
    #                 if dates.get(key) or start:
    #                     start = True
    #                     months.append((key, dates.get(key, 0)))
    #                     total += dates.get(key, 0)
    #                     month_count += 1
    #     self.data.story_count_history = json.encode(months)
    #     self.data.save()
    #     if not total or not month_count:
    #         self.average_stories_per_month = 0
    #     else:
    #         self.average_stories_per_month = int(
    #             round(total / float(month_count)))
    #     self.save()

    # Deleted by Xinyan Lu : No this table
    # def save_classifier_counts(self):
    #     from apps.analyzer.models import MClassifierTitle, MClassifierAuthor, MClassifierFeed, MClassifierTag

    #     def calculate_scores(cls, facet):
    #         map_f = """
    #             function() {
    #                 emit(this["%s"], {
    #                     pos: this.score>0 ? this.score : 0,
    #                     neg: this.score<0 ? Math.abs(this.score) : 0
    #                 });
    #             }
    #         """ % (facet)
    #         reduce_f = """
    #             function(key, values) {
    #                 var result = {pos: 0, neg: 0};
    #                 values.forEach(function(value) {
    #                     result.pos += value.pos;
    #                     result.neg += value.neg;
    #                 });
    #                 return result;
    #             }
    #         """
    #         scores = []
    #         res = cls.objects(feed_id=self.pk).map_reduce(
    #             map_f, reduce_f, output='inline')
    #         for r in res:
    #             facet_values = dict([(k, int(v))
    #                                 for k, v in r.value.iteritems()])
    #             facet_values[facet] = r.key
    #             if facet_values['pos'] + facet_values['neg'] > 1:
    #                 scores.append(facet_values)
    #         scores = sorted(scores, key=lambda v: v['neg'] - v['pos'])

    #         return scores

    #     scores = {}
    #     for cls, facet in [(MClassifierTitle, 'title'),
    #                        (MClassifierAuthor, 'author'),
    #                        (MClassifierTag, 'tag'),
    #                        (MClassifierFeed, 'feed_id')]:
    #         scores[facet] = calculate_scores(cls, facet)
    #         if facet == 'feed_id' and scores[facet]:
    #             scores['feed'] = scores[facet]
    #             del scores['feed_id']
    #         elif not scores[facet]:
    #             del scores[facet]

    #     if scores:
    #         self.data.feed_classifier_counts = json.encode(scores)
    #         self.data.save()

    def update(self, **kwargs):
        from utils import feed_fetcher
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        original_feed_id = int(self.pk)

        if getattr(settings, 'TEST_DEBUG', False):
            self.feed_address = self.feed_address.replace(
                "%(NEWSBLUR_DIR)s", settings.NEWSBLUR_DIR)
            self.feed_link = self.feed_link.replace(
                "%(NEWSBLUR_DIR)s", settings.NEWSBLUR_DIR)
            self.save()

        options = {
            'verbose': kwargs.get('verbose'),
            'timeout': 10,
            'single_threaded': kwargs.get('single_threaded', True),
            'force': kwargs.get('force'),
            'compute_scores': kwargs.get('compute_scores', True),
            'mongodb_replication_lag': kwargs.get('mongodb_replication_lag', None),
            'fake': kwargs.get('fake'),
            'quick': kwargs.get('quick'),
            'debug': kwargs.get('debug'),
            'fpf': kwargs.get('fpf'),
            'feed_xml': kwargs.get('feed_xml'),
        }
        disp = feed_fetcher.Dispatcher(options, 1)
        disp.add_jobs([[self.pk]])
        feed = disp.run_jobs()

        if feed:
            feed = Feed.get_by_id(feed.pk)
        if feed:
            feed.last_update = datetime.datetime.utcnow()
            feed.set_next_scheduled_update()
            r.zadd('fetched_feeds_last_hour', feed.pk,
                   int(datetime.datetime.now().strftime('%s')))

        if not feed or original_feed_id != feed.pk:
            logging.info(
                " ---> ~FRFeed changed id, removing %s from tasked_feeds queue..." %
                original_feed_id)
            r.zrem('tasked_feeds', original_feed_id)
            r.zrem('error_feeds', original_feed_id)
        if feed:
            r.zrem('tasked_feeds', feed.pk)
            r.zrem('error_feeds', feed.pk)

        return feed

    @classmethod
    def get_by_id(cls, feed_id, feed_address=None):
        try:
            feed = Feed.objects.get(pk=feed_id)
            return feed
        except Feed.DoesNotExist:
            raise Feed.DoesNotExist
            # Feed has been merged after updating. Find the right feed.

            # Deleted by Xinyan Lu : No DuplicateFeed currently
            # duplicate_feeds = DuplicateFeed.objects.filter(
            #     duplicate_feed_id=feed_id)
            # if duplicate_feeds:
            #     return duplicate_feeds[0].feed
            # if feed_address:
            #     duplicate_feeds = DuplicateFeed.objects.filter(
            #         duplicate_address=feed_address)
            #     if duplicate_feeds:
            #         return duplicate_feeds[0].feed

    @classmethod
    def get_by_name(cls, query, limit=1):
        results = SearchFeed.query(query)
        feed_ids = [result.feed_id for result in results]

        if limit == 1:
            return Feed.get_by_id(feed_ids[0])
        else:
            return [Feed.get_by_id(f) for f in feed_ids][:limit]

    def add_update_stories(self, stories, existing_stories, verbose=False):
        ret_values = dict(new=0, updated=0, same=0, error=0)
        error_count = self.error_count

        if settings.DEBUG or verbose:
            logging.debug("   ---> [%-30s] ~FBChecking ~SB%s~SN new/updated against ~SB%s~SN stories" % (
                          self.title[:30],
                          len(stories),
                          len(existing_stories.keys())))

        @timelimit(2)
        def _1(story, story_content, existing_stories):
            existing_story, story_has_changed = self._exists_story(
                story, story_content, existing_stories)
            return existing_story, story_has_changed

        for story in stories:
            if not story.get('title'):
                continue

            story_content = story.get('story_content')
            if error_count:
                story_content = strip_comments__lxml(story_content)
            else:
                story_content = strip_comments(story_content)
            story_tags = self.get_tags(story)
            story_link = self.get_permalink(story)

            try:
                existing_story, story_has_changed = _1(
                    story, story_content, existing_stories)
            except TimeoutError, e:
                logging.debug(
                    '   ---> [%-30s] ~SB~FRExisting story check timed out...' % (unicode(self)[:30]))
                existing_story = None
                story_has_changed = False

            if existing_story is None:
                if settings.DEBUG and False:
                    logging.debug('   ---> New story in feed (%s - %s): %s' %
                                  (self.feed_title, story.get('title'), len(story_content)))

                s = MStory(story_feed_id=self.pk,
                           story_date=story.get('published'),
                           story_title=story.get('title'),
                           story_content=story_content,
                           story_author_name=story.get('author'),
                           story_permalink=story_link,
                           story_guid=story.get('guid'),
                           story_tags=story_tags
                           )
                s.extract_image_urls()

                try:
                    s.save()
                    ret_values['new'] += 1
                    #=========================
                    #=Added by SongJun:      =
                    #==fetch_original_text   =
                    #==fetch_reference_images=
                    #=========================
                    original_text = s.fetch_original_text()
                    soup = BeautifulSoup(str(original_text))
                    imgs = soup.findAll('img')
                    for img in imgs:
                        imgurl=img.get('src')
                        # Add by XY: imgurl may be None
                        if not imgurl:
                            continue
                        if imgurl and len(imgurl) >= 1024:
                            continue
                        if not(imgurl in s.image_urls):
                            s.image_urls.append(imgurl)
                    s.fetch_reference_images()
                    #=========================
                except (IntegrityError, OperationError), e:
                    ret_values['error'] += 1
                    # Commented By XY Lu: too many logs
                    # if settings.DEBUG:
                    #     logging.info('   ---> [%-30s] ~SN~FRIntegrityError on new story: %s - %s' % (
                    #         self.feed_title[:30], story.get('guid'), e))
                # =========================================
                # = Send the story id to D-Ocean  SongJun =
                # =========================================
                if not s.id==None:
                    try:
                        DOr = redis.Redis(connection_pool=settings.D_OCEAN_REDIS_POOL)
                        DOr.lpush('story_id_list',s.id)
                    except Exception, e:
                        logging.error(str(e)+\
                            traceback.format_exc()+'\n'+\
                            'error from:  add_update_stories\n')
                        if settings.SEND_ERROR_MAILS:
                            mail_admins("Error in add_update_stories",str(e)+'\n'+traceback.format_exc())

            elif existing_story and story_has_changed:
                # update story
                original_content = None
                try:
                    if existing_story and existing_story.id:
                        try:
                            existing_story = MStory.objects.get(
                                id=existing_story.id)
                        except ValidationError:
                            existing_story, _ = MStory.find_story(
                                existing_story.story_feed_id,
                                existing_story.id,
                                original_only=True)
                    elif existing_story and existing_story.story_guid:
                        existing_story, _ = MStory.find_story(
                            existing_story.story_feed_id,
                            existing_story.story_guid,
                            original_only=True)
                    else:
                        raise MStory.DoesNotExist
                except (MStory.DoesNotExist, OperationError), e:
                    ret_values['error'] += 1
                    if verbose:
                        logging.info('   ---> [%-30s] ~SN~FROperation on existing story: %s - %s' % (
                            self.feed_title[:30], story.get('guid'), e))
                    continue
                if existing_story.story_original_content_z:
                    original_content = zlib.decompress(existing_story.story_original_content_z)
                elif existing_story.story_content_z:
                    original_content = zlib.decompress(existing_story.story_content_z)
                # print 'Type: %s %s' % (type(original_content),
                # type(story_content))
                if story_content and len(story_content) > 10:
                    story_content_diff = htmldiff(
                        unicode(original_content), unicode(story_content))
                else:
                    story_content_diff = original_content
                # logging.debug("\t\tDiff: %s %s %s" % diff.getStats())
                # logging.debug("\t\tDiff content: %s" % diff.getDiff())
                # if existing_story.story_title != story.get('title'):
                #    logging.debug('\tExisting title / New: : \n\t\t- %s\n\t\t- %s' % (existing_story.story_title, story.get('title')))
                if existing_story.story_guid != story.get('guid'):
                    self.update_story_with_new_guid(
                        existing_story, story.get('guid'))

                if settings.DEBUG and False:
                    logging.debug(
                        '- Updated story in feed (%s - %s): %s / %s' %
                        (self.feed_title, story.get('title'), len(story_content_diff), len(story_content)))

                existing_story.story_feed = self.pk
                existing_story.story_title = story.get('title')
                existing_story.story_content = story_content_diff
                existing_story.story_latest_content = story_content
                existing_story.story_original_content = original_content
                existing_story.story_author_name = story.get('author')
                existing_story.story_permalink = story_link
                existing_story.story_guid = story.get('guid')
                existing_story.story_tags = story_tags
                # Do not allow publishers to change the story date once a story is published.
                # Leads to incorrect unread story counts.
                # existing_story.story_date = story.get('published') # No,
                # don't
                existing_story.extract_image_urls()

                try:
                    existing_story.save()
                    ret_values['updated'] += 1
                except (IntegrityError, OperationError):
                    ret_values['error'] += 1
                    if verbose:
                        logging.info('   ---> [%-30s] ~SN~FRIntegrityError on updated story: %s' % (
                            self.feed_title[:30], story.get('title')[:30]))
                except ValidationError:
                    ret_values['error'] += 1
                    if verbose:
                        logging.info('   ---> [%-30s] ~SN~FRValidationError on updated story: %s' % (
                            self.feed_title[:30], story.get('title')[:30]))
            else:
                ret_values['same'] += 1
                # logging.debug("Unchanged story: %s " % story.get('title'))
        return ret_values

    def update_story_with_new_guid(self, existing_story, new_story_guid):
        # Deleted By Xinyan Lu: no such models
        # from apps.reader.models import RUserStory
        # from apps.social.models import MSharedStory

        existing_story.remove_from_redis()

        old_hash = existing_story.story_hash
        new_hash = MStory.ensure_story_hash(new_story_guid, self.pk)
        # RUserStory.switch_hash(
            # feed_id=self.pk, old_hash=old_hash, new_hash=new_hash)

        # shared_stories = MSharedStory.objects.filter(story_feed_id=self.pk,
        #                                              story_hash=old_hash)
        # for story in shared_stories:
        #     story.story_guid = new_story_guid
        #     story.story_hash = new_hash
        #     try:
        #         story.save()
        #     except NotUniqueError:
        #         # Story is already shared, skip.
        #         pass

    # Deleted by Xinyan Lu : No this table
    # def save_popular_tags(self, feed_tags=None, verbose=False):
    #     if not feed_tags:
    #         all_tags = MStory.objects(story_feed_id=self.pk,
    #                                   story_tags__exists=True).item_frequencies('story_tags')
    #         feed_tags = sorted(
    #             [(k, v) for k, v in all_tags.items() if int(v) > 0],
    #             key=itemgetter(1),
    #             reverse=True)[:25]
    #     popular_tags = json.encode(feed_tags)
    #     if verbose:
    #         print "Found %s tags: %s" % (len(feed_tags), popular_tags)

    #     # TODO: This len() bullshit will be gone when feeds move to mongo
    #     #       On second thought, it might stay, because we don't want
    #     #       popular tags the size of a small planet. I'm looking at you
    #     #       Tumblr writers.
    #     if len(popular_tags) < 1024:
    #         self.data.popular_tags = popular_tags
    #         self.data.save()
    #         return

    #     tags_list = []
    #     if feed_tags and isinstance(feed_tags, unicode):
    #         tags_list = json.decode(feed_tags)
    #     if len(tags_list) >= 1:
    #         self.save_popular_tags(tags_list[:-1])

    # Deleted by Xinyan Lu : No this table
    # def save_popular_authors(self, feed_authors=None):
    #     if not feed_authors:
    #         authors = defaultdict(int)
    #         for story in MStory.objects(story_feed_id=self.pk).only('story_author_name'):
    #             authors[story.story_author_name] += 1
    #         feed_authors = sorted([(k, v) for k, v in authors.items() if k],
    #                               key=itemgetter(1),
    #                               reverse=True)[:20]

    #     popular_authors = json.encode(feed_authors)
    #     if len(popular_authors) < 1023:
    #         self.data.popular_authors = popular_authors
    #         self.data.save()
    #         return

    #     if len(feed_authors) > 1:
    #         self.save_popular_authors(feed_authors=feed_authors[:-1])

    #Deleted By Xinyan Lu : need not trim_old_stories currently
    # @classmethod
    # def trim_old_stories(cls, start=0, verbose=True, dryrun=False):
    #     now = datetime.datetime.now()
    #     month_ago = now - datetime.timedelta(days=settings.DAYS_OF_UNREAD_NEW)
    #     feed_count = Feed.objects.latest('pk').pk
    #     total = 0
    #     for feed_id in xrange(start, feed_count):
    #         if feed_id % 1000 == 0:
    #             print "\n\n -------------------------- %s --------------------------\n\n" % feed_id
    #         try:
    #             feed = Feed.objects.get(pk=feed_id)
    #         except Feed.DoesNotExist:
    #             continue
    #         if feed.active_subscribers > 0:
    #             continue
    #         if not feed.last_story_date or feed.last_story_date < month_ago:
    #             months_ago = 6
    #             if feed.last_story_date:
    #                 months_ago = int((now - feed.last_story_date).days / 30.0)
    #             cutoff = max(1, 6 - months_ago)
    #             if dryrun:
    #                 print " DRYRUN: %s cutoff - %s" % (cutoff, feed)
    #             else:
    #                 total += MStory.trim_feed(
    #                     feed=feed, cutoff=cutoff, verbose=verbose)

    #     print " ---> Deleted %s stories in total." % total

    @property
    def story_cutoff(self):
        cutoff = 500
        if self.active_subscribers <= 0:
            cutoff = 50
        elif self.active_premium_subscribers < 1:
            cutoff = 100
        elif self.active_premium_subscribers <= 2:
            cutoff = 200000
        elif self.active_premium_subscribers <= 5:
            cutoff = 200000
        elif self.active_premium_subscribers <= 10:
            cutoff = 200000
        elif self.active_premium_subscribers <= 15:
            cutoff = 200000
        elif self.active_premium_subscribers <= 20:
            cutoff = 200000

        if self.active_subscribers and self.average_stories_per_month < 5 and self.stories_last_month < 5:
            cutoff /= 2
        if self.active_premium_subscribers <= 1 and self.average_stories_per_month <= 1 and self.stories_last_month <= 1:
            cutoff /= 2

        return cutoff

    def trim_feed(self, verbose=False, cutoff=None):
        # Add by XY: No need to trim feed, we need all feed stories, so just do nothing
        return
        if not cutoff:
            cutoff = self.story_cutoff
        MStory.trim_feed(feed=self, cutoff=cutoff, verbose=verbose)

    def freeze_feed(self,verbose=True):
        MStory.freeze_feed(feed=self,verbose=verbose)

    # @staticmethod
    # def clean_invalid_ids():
    #     history = MFeedFetchHistory.objects(status_code=500, exception__contains='InvalidId:')
    #     urls = set()
    #     for h in history:
    #         u = re.split('InvalidId: (.*?) is not a valid ObjectId\\n$', h.exception)[1]
    #         urls.add((h.feed_id, u))
    #
    #     for f, u in urls:
    # print "db.stories.remove({\"story_feed_id\": %s, \"_id\": \"%s\"})" %
    # (f, u)

    def get_stories(self, offset=0, limit=25, force=False):
        stories_db = MStory.objects(
            story_feed_id=self.pk)[offset:offset + limit]
        stories = self.format_stories(stories_db, self.pk)

        return stories

    @classmethod
    def find_feed_stories(cls, feed_ids, query, offset=0, limit=25):
        stories_db = MStory.objects(
            Q(story_feed_id__in=feed_ids) &
            (Q(story_title__icontains=query) |
             Q(story_author_name__icontains=query) |
             Q(story_tags__icontains=query))
        ).order_by('-story_date')[offset:offset + limit]
        stories = cls.format_stories(stories_db)

        return stories

    def find_stories(self, query, offset=0, limit=25):
        stories_db = MStory.objects(
            Q(story_feed_id=self.pk) &
            (Q(story_title__icontains=query) |
             Q(story_author_name__icontains=query) |
             Q(story_tags__icontains=query))
        ).order_by('-story_date')[offset:offset + limit]
        stories = self.format_stories(stories_db, self.pk)

        return stories

    @classmethod
    def format_stories(cls, stories_db, feed_id=None, include_permalinks=False):
        stories = []

        for story_db in stories_db:
            story = cls.format_story(
                story_db, feed_id, include_permalinks=include_permalinks)
            stories.append(story)

        return stories

    @classmethod
    def format_story(cls, story_db, feed_id=None, text=False, include_permalinks=False):
        if isinstance(story_db.story_content_z, unicode):
            story_db.story_content_z = story_db.story_content_z.decode(
                'base64')

        story_content = story_db.story_content_z and zlib.decompress(
            story_db.story_content_z) or ''
        story = {}
        story['story_hash'] = getattr(story_db, 'story_hash', None)
        story['story_tags'] = story_db.story_tags or []
        story['story_date'] = story_db.story_date.replace(tzinfo=pytz.utc).astimezone(pytz.timezone(settings.TIME_ZONE))
        story['story_timestamp'] = story_db.story_date.strftime('%s')
        story['story_authors'] = story_db.story_author_name
        story['story_title'] = story_db.story_title
        story['story_content'] = story_content
        story['story_permalink'] = story_db.story_permalink
        story['image_urls'] = story_db.image_urls
        story['story_feed_id'] = feed_id or story_db.story_feed_id
        story['comment_count'] = story_db.comment_count if hasattr(
            story_db, 'comment_count') else 0
        story['comment_user_ids'] = story_db.comment_user_ids if hasattr(
            story_db, 'comment_user_ids') else []
        story['share_count'] = story_db.share_count if hasattr(
            story_db, 'share_count') else 0
        story['share_user_ids'] = story_db.share_user_ids if hasattr(
            story_db, 'share_user_ids') else []
        story['guid_hash'] = story_db.guid_hash if hasattr(
            story_db, 'guid_hash') else None
        if hasattr(story_db, 'source_user_id'):
            story['source_user_id'] = story_db.source_user_id
        story['id'] = story_db.story_guid or story_db.story_date
        if hasattr(story_db, 'starred_date'):
            story['starred_date'] = story_db.starred_date
        if hasattr(story_db, 'shared_date'):
            story['shared_date'] = story_db.shared_date
        if include_permalinks and hasattr(story_db, 'blurblog_permalink'):
            story['blurblog_permalink'] = story_db.blurblog_permalink()
        if text:
            soup = BeautifulSoup(story['story_content'])
            text = ''.join(soup.findAll(text=True))
            text = re.sub(r'\n+', '\n\n', text)
            text = re.sub(r'\t+', '\t', text)
            story['text'] = text
        if '<ins' in story['story_content'] or '<del' in story['story_content']:
            story['has_modifications'] = True

        return story

    def get_tags(self, entry):
        fcat = []
        if entry.has_key('tags'):
            for tcat in entry.tags:
                term = None
                if hasattr(tcat, 'label') and tcat.label:
                    term = tcat.label
                elif hasattr(tcat, 'term') and tcat.term:
                    term = tcat.term
                if not term:
                    continue
                qcat = term.strip()
                if ',' in qcat or '/' in qcat:
                    qcat = qcat.replace(',', '/').split('/')
                else:
                    qcat = [qcat]
                for zcat in qcat:
                    tagname = zcat.lower()
                    while '  ' in tagname:
                        tagname = tagname.replace('  ', ' ')
                    tagname = tagname.strip()
                    if not tagname or tagname == ' ':
                        continue
                    fcat.append(tagname)
        fcat = [strip_tags(t)[:250] for t in fcat[:12]]
        return fcat

    def get_permalink(self, entry):
        link = entry.get('link')
        if not link:
            links = entry.get('links')
            if links:
                link = links[0].get('href')
        if not link:
            link = entry.get('id')
        return link

    def _exists_story(self, story=None, story_content=None, existing_stories=None):
        story_in_system = None
        story_has_changed = False
        story_link = self.get_permalink(story)
        existing_stories_guids = existing_stories.keys()
        # story_pub_date = story.get('published')
        # story_published_now = story.get('published_now', False)
        # start_date = story_pub_date - datetime.timedelta(hours=8)
        # end_date = story_pub_date + datetime.timedelta(hours=8)

        for existing_story in existing_stories.values():
            content_ratio = 0
            # existing_story_pub_date = existing_story.story_date
            # print 'Story pub date: %s %s' % (story_published_now,
            # story_pub_date)

            if 'story_latest_content_z' in existing_story:
                existing_story_content = unicode(
                    zlib.decompress(existing_story.story_latest_content_z))
            elif 'story_latest_content' in existing_story:
                existing_story_content = existing_story.story_latest_content
            elif 'story_content_z' in existing_story:
                existing_story_content = unicode(
                    zlib.decompress(existing_story.story_content_z))
            elif 'story_content' in existing_story:
                existing_story_content = existing_story.story_content
            else:
                existing_story_content = u''

            if isinstance(existing_story.id, unicode):
                existing_story.story_guid = existing_story.id
            if (story.get('guid') in existing_stories_guids and
                story.get('guid') != existing_story.story_guid):
                continue
            elif story.get('guid') == existing_story.story_guid:
                story_in_system = existing_story

            # Title distance + content distance, checking if story changed
            story_title_difference = abs(
                levenshtein_distance(story.get('title'),
                                     existing_story.story_title))

            seq = difflib.SequenceMatcher(
                None, story_content, existing_story_content)

            if (seq
                and story_content
                and len(story_content) > 1000
                and existing_story_content
                and seq.real_quick_ratio() > .9
                and seq.quick_ratio() > .95):
                content_ratio = seq.ratio()

            if story_title_difference > 0 and content_ratio > .98:
                story_in_system = existing_story
                if story_title_difference > 0 or content_ratio < 1.0:
                    if settings.DEBUG and False:
                        logging.debug(
                            " ---> Title difference - %s/%s (%s): %s" %
                            (story.get('title'), existing_story.story_title, story_title_difference, content_ratio))
                    story_has_changed = True
                    break

            # More restrictive content distance, still no story match
            if not story_in_system and content_ratio > .98:
                if settings.DEBUG and False:
                    logging.debug(" ---> Content difference - %s/%s (%s): %s" %
                                  (story.get('title'), existing_story.story_title, story_title_difference, content_ratio))
                story_in_system = existing_story
                story_has_changed = True
                break

            if story_in_system and not story_has_changed:
                if story_content != existing_story_content:
                    if settings.DEBUG and False:
                        logging.debug(" ---> Content difference - %s/%s" %
                                      (story_content, existing_story_content))
                    story_has_changed = True
                if story_link != existing_story.story_permalink:
                    if settings.DEBUG and False:
                        logging.debug(" ---> Permalink difference - %s/%s" %
                                      (story_link, existing_story.story_permalink))
                    story_has_changed = True
                # if story_pub_date != existing_story.story_date:
                #     story_has_changed = True
                break

        # if story_has_changed or not story_in_system:
        #     print 'New/updated story: %s' % (story),
        return story_in_system, story_has_changed

    def get_next_scheduled_update(self, force=False, verbose=True):
        if self.min_to_decay and not force:
            return self.min_to_decay

        upd = self.stories_last_month / 30.0
        subs = (self.active_premium_subscribers +
                ((self.active_subscribers - self.active_premium_subscribers) / 10.0))
        # UPD = 1  Subs > 1:  t = 5         # 11625  * 1440/5 =       3348000
        # UPD = 1  Subs = 1:  t = 60        # 17231  * 1440/60 =      413544
        # UPD < 1  Subs > 1:  t = 60        # 37904  * 1440/60 =      909696
        # UPD < 1  Subs = 1:  t = 60 * 12   # 143012 * 1440/(60*12) = 286024
        # UPD = 0  Subs > 1:  t = 60 * 3    # 28351  * 1440/(60*3) =  226808
        # UPD = 0  Subs = 1:  t = 60 * 24   # 807690 * 1440/(60*24) = 807690
        if upd >= 1:
            if subs > 1:
                total = 10
            else:
                total = 60
        elif upd > 0:
            if subs > 1:
                total = 60 - (upd * 60)
            else:
                total = 60 * 12 - (upd * 60 * 12)
        elif upd == 0:
            if subs > 1:
                total = 60 * 6
            else:
                total = 60 * 24
            months_since_last_story = seconds_timesince(
                self.last_story_date) / (60 * 60 * 24 * 30)
            total *= max(1, months_since_last_story)
        # updates_per_day_delay = 3 * 60 / max(.25, ((max(0, self.active_subscribers)**.2)
        #                                             * (self.stories_last_month**0.25)))
        # if self.active_premium_subscribers > 0:
        #     updates_per_day_delay /= min(self.active_subscribers+self.active_premium_subscribers, 4)
        # updates_per_day_delay = int(updates_per_day_delay)

        # Lots of subscribers = lots of updates
        # 24 hours for 0 subscribers.
        # 4 hours for 1 subscriber.
        # .5 hours for 2 subscribers.
        # .25 hours for 3 subscribers.
        # 1 min for 10 subscribers.
        # subscriber_bonus = 6 * 60 / max(.167, max(0, self.active_subscribers)**3)
        # if self.premium_subscribers > 0:
        #     subscriber_bonus /= min(self.active_subscribers+self.premium_subscribers, 5)
        # subscriber_bonus = int(subscriber_bonus)

        if self.is_push:
            fetch_history = MFetchHistory.feed(self.pk)
            if len(fetch_history['push_history']):
                total = total * 12

        # 3 day max
        total = min(total, 60 * 24 * 2)

        if verbose:
            logging.debug("   ---> [%-30s] Fetched every %s min - Subs: %s/%s/%s Stories: %s" % (
                unicode(self)[:30], total,
                self.num_subscribers,
                self.active_subscribers,
                self.active_premium_subscribers,
                upd))
        return total

    def set_next_scheduled_update(self, verbose=False, skip_scheduling=False):
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        total = self.get_next_scheduled_update(force=True, verbose=verbose)
        error_count = self.error_count

        if error_count:
            total = total * error_count
            total = min(total, 60 * 24 * 7)
            if verbose:
                logging.debug('   ---> [%-30s] ~FBScheduling feed fetch geometrically: '
                              '~SB%s errors. Time: %s min' % (
                              unicode(self)[:30], self.errors_since_good, total))

        random_factor = random.randint(0, total) / 4 + 5
        next_scheduled_update = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=total + random_factor)

        self.min_to_decay = total
        delta = self.next_scheduled_update - datetime.datetime.now()
        #fix by Chen Yiyu
        #total_seconds() method only for Python2.7 or later, fix it for Python2.6
        #minutes_to_next_fetch = delta.total_seconds() / 60
        minutes_to_next_fetch = (delta.seconds + (delta.days * 24 * 3600)) / 60
        if minutes_to_next_fetch > self.min_to_decay or not skip_scheduling:
            self.next_scheduled_update = next_scheduled_update
            # Delete by Xinyan Lu: Ignore active_subscribers
            # if self.active_subscribers >= 1:
            r.zadd('scheduled_updates', self.pk,
                self.next_scheduled_update.strftime('%s'))
            r.zrem('tasked_feeds', self.pk)
            r.srem('queued_feeds', self.pk)

        self.save()

    @property
    def error_count(self):
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        fetch_errors = int(r.zscore('error_feeds', self.pk) or 0)

        return fetch_errors + self.errors_since_good

    def schedule_feed_fetch_immediately(self, verbose=True):
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        if verbose:
            logging.debug(
                '   ---> [%-30s] Scheduling feed fetch immediately...' % (unicode(self)[:30]))

        self.next_scheduled_update = datetime.datetime.utcnow()
        r.zadd('scheduled_updates', self.pk,
               self.next_scheduled_update.strftime('%s'))

        return self.save()

    def setup_push(self):
        from apps.push.models import PushSubscription
        try:
            push = self.push
        except PushSubscription.DoesNotExist:
            self.is_push = False
        else:
            self.is_push = push.verified
        self.save()

    def queue_pushed_feed_xml(self, xml):
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        queue_size = r.llen("push_feeds")

        if queue_size > 1000:
            self.schedule_feed_fetch_immediately()
        else:
            logging.debug('   ---> [%-30s] [%s] ~FBQueuing pushed stories...' %
                          (unicode(self)[:30], self.pk))
            self.set_next_scheduled_update()
            PushFeeds.apply_async(args=(self.pk, xml), queue='push_feeds')

    # def calculate_collocations_story_content(self,
    #                                          collocation_measures=TrigramAssocMeasures,
    #                                          collocation_finder=TrigramCollocationFinder):
    #     stories = MStory.objects.filter(story_feed_id=self.pk)
    #     story_content = ' '.join([s.story_content for s in stories if s.story_content])
    #     return self.calculate_collocations(story_content, collocation_measures, collocation_finder)
    #
    # def calculate_collocations_story_title(self,
    #                                        collocation_measures=BigramAssocMeasures,
    #                                        collocation_finder=BigramCollocationFinder):
    #     stories = MStory.objects.filter(story_feed_id=self.pk)
    #     story_titles = ' '.join([s.story_title for s in stories if s.story_title])
    #     return self.calculate_collocations(story_titles, collocation_measures, collocation_finder)
    #
    # def calculate_collocations(self, content,
    #                            collocation_measures=TrigramAssocMeasures,
    #                            collocation_finder=TrigramCollocationFinder):
    # content = re.sub(r'&#8217;', '\'', content)
    #     content = re.sub(r'&amp;', '&', content)
    #     try:
    #         content = unicode(BeautifulStoneSoup(content,
    #                           convertEntities=BeautifulStoneSoup.HTML_ENTITIES))
    #     except ValueError, e:
    #         print "ValueError, ignoring: %s" % e
    #     content = re.sub(r'</?\w+\s+[^>]*>', '', content)
    #     content = re.split(r"[^A-Za-z-'&]+", content)
    #
    #     finder = collocation_finder.from_words(content)
    #     finder.apply_freq_filter(3)
    #     best = finder.nbest(collocation_measures.pmi, 10)
    #     phrases = [' '.join(phrase) for phrase in best]
    #
    #     return phrases

# class FeedCollocations(models.Model):
#     feed = models.ForeignKey(Feed)
#     phrase = models.CharField(max_length=500)

# Deleted by Xinyan Lu : No this table
# class FeedData(models.Model):
#     feed = AutoOneToOneField(Feed, related_name='data')
#     feed_tagline = models.CharField(max_length=1024, blank=True, null=True)
#     story_count_history = models.TextField(blank=True, null=True)
#     feed_classifier_counts = models.TextField(blank=True, null=True)
#     popular_tags = models.CharField(max_length=1024, blank=True, null=True)
#     popular_authors = models.CharField(max_length=2048, blank=True, null=True)

#     def save(self, *args, **kwargs):
#         if self.feed_tagline and len(self.feed_tagline) >= 1000:
#             self.feed_tagline = self.feed_tagline[:1000]

#         try:
#             super(FeedData, self).save(*args, **kwargs)
#         except (IntegrityError, OperationError):
#             if hasattr(self, 'id') and self.id: self.delete()


class MFeedIcon(mongo.Document):
    feed_id = mongo.IntField(primary_key=True)
    color = mongo.StringField(max_length=6)
    data = mongo.StringField()
    icon_url = mongo.StringField()
    not_found = mongo.BooleanField(default=False)

    meta = {
        'collection': 'feed_icons',
        'allow_inheritance': False,
    }

    def save(self, *args, **kwargs):
        if self.icon_url:
            self.icon_url = unicode(self.icon_url)
        try:
            return super(MFeedIcon, self).save(*args, **kwargs)
        except (IntegrityError, OperationError):
            # print "Error on Icon: %s" % e
            if hasattr(self, '_id'):
                self.delete()


class MFeedPage(mongo.Document):
    feed_id = mongo.IntField(primary_key=True)
    page_data = mongo.BinaryField()

    meta = {
        'collection': 'feed_pages',
        'allow_inheritance': False,
    }

    def save(self, *args, **kwargs):
        if self.page_data:
            # Modified by Xinyan Lu: supress UnicodeWarning, known to be safe
            # self.page_data = zlib.compress(self.page_data)
            import warnings
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter('always',category=UnicodeWarning)
                self.page_data = zlib.compress(self.page_data)
        return super(MFeedPage, self).save(*args, **kwargs)

    @classmethod
    def get_data(cls, feed_id):
        data = None
        feed_page = cls.objects(feed_id=feed_id)
        if feed_page:
            page_data_z = feed_page[0].page_data
            if page_data_z:
                data = zlib.decompress(page_data_z)
        # Deleted By Xinyan Lu : No DuplicateFeed currently
        # if not data:
        #     dupe_feed = DuplicateFeed.objects.filter(duplicate_feed_id=feed_id)
        #     if dupe_feed:
        #         feed = dupe_feed[0].feed
        #         feed_page = MFeedPage.objects.filter(feed_id=feed.pk)
        #         if feed_page:
        #             page_data_z = feed_page[0].page_data
        #             if page_data_z:
        #                 data = zlib.decompress(feed_page[0].page_data)

        return data

class MStory(mongo.Document):

    '''A feed item'''
    story_feed_id = mongo.IntField()
    story_date = mongo.DateTimeField()
    story_title = mongo.StringField(max_length=1024)
    story_content = mongo.StringField()
    story_content_z = mongo.BinaryField()
    story_original_content = mongo.StringField()
    story_original_content_z = mongo.BinaryField()
    story_latest_content = mongo.StringField()
    story_latest_content_z = mongo.BinaryField()
    original_text_z = mongo.BinaryField()
    original_text = mongo.StringField()
    story_content_type = mongo.StringField(max_length=255)
    story_author_name = mongo.StringField()
    story_permalink = mongo.StringField()
    story_guid = mongo.StringField()
    story_hash = mongo.StringField()
    image_urls = mongo.ListField(
        mongo.StringField(max_length=1024))
    # Add by Xinyan Lu : support images storage
    image_ids = mongo.ListField(mongo.StringField())
    story_tags = mongo.ListField(
        mongo.StringField(max_length=250))
    comment_count = mongo.IntField()
    comment_user_ids = mongo.ListField(mongo.IntField())
    share_count = mongo.IntField()
    share_user_ids = mongo.ListField(mongo.IntField())

    meta = {
        'collection': 'stories',
        'indexes': [('story_feed_id', '-story_date'),
                    {'fields': ['story_hash'],
                     'unique': True,
                     'types': False, }],
        'index_drop_dups': True,
        'ordering': ['-story_date'],
        'allow_inheritance': False,
        'cascade': False,
    }

    RE_STORY_HASH = re.compile(r"^(\d{1,10}):(\w{6})$")
    RE_RS_KEY = re.compile(r"^RS:(\d+):(\d+)$")

    @property
    def story_tidy_content(self):
        content = self.story_original_content_uz
        if len(self.story_content_uz) > len(content):
            content = self.story_content_uz
        # replace images using local images
        bsoup = BeautifulSoup(str(content))
        for image in bsoup.findAll('img'):
            remote_url = image['src']
            stored_image = MImage.get_by_url(remote_url)
            if stored_image:
                image['src'] = settings.FDFS_HTTP_SERVER + stored_image.image_remote_id
        return str(bsoup)

    @property
    def story_content_uz(self):
        if self.story_content == None:
            self.story_content = zlib.decompress(self.story_content_z)
        return self.story_content

    @property
    def story_original_content_uz(self):
        if self.original_text_z:
            return zlib.decompress(self.original_text_z)
        else:
            return ''

    @property
    def guid_hash(self):
        return hashlib.sha1(self.story_guid).hexdigest()[:6]

    @property
    def feed_guid_hash(self):
        return "%s:%s" % (self.story_feed_id, self.guid_hash)

    def save(self, *args, **kwargs):
        story_title_max = MStory._fields['story_title'].max_length
        story_content_type_max = MStory._fields[
            'story_content_type'].max_length
        self.story_hash = self.feed_guid_hash

        # store original story_content, or it will be erased
        story_content = self.story_content

        if self.story_content:
            try:
                self.story_content_z = zlib.compress(self.story_content)
            except UnicodeEncodeError:
                pass 
            #self.story_content = None
        if self.story_original_content:
            try:
                self.story_original_content_z = zlib.compress(
                    self.story_original_content)
            except UnicodeEncodeError:
                pass
            #self.story_original_content = None
        if self.story_latest_content:
            try:
                self.story_latest_content_z = zlib.compress(
                    self.story_latest_content)
            except:
                pass
            #self.story_latest_content = None
        if self.story_title and len(self.story_title) > story_title_max:
            self.story_title = self.story_title[:story_title_max]
        if self.story_content_type and len(self.story_content_type) > story_content_type_max:
            self.story_content_type = self.story_content_type[
                :story_content_type_max]

        super(MStory, self).save(*args, **kwargs)

        #Add by Xinyan Lu : index on save
        if not story_content and self.story_content_z:
            story_content = zlib.decompress(self.story_content_z)
        SearchStory.index(story_id=self.story_guid,
                            story_title=self.story_title,
                            story_content=story_content,
                            story_author=self.story_author_name,
                            story_date=self.story_date,
                            db_id=str(self.id))

        #Add by Xinyan Lu : fetch image on save
        #self.fetch_reference_images()

        self.sync_redis()

        return self

    def delete(self, *args, **kwargs):
        self.remove_from_redis()

        super(MStory, self).delete(*args, **kwargs)

    #Commented By Xinyan Lu : be careful on parameter 'cutoff'
    # @classmethod
    # def trim_feed(cls, cutoff, feed_id=None, feed=None, verbose=True):    
    #Modified By Xinyan Lu : support for MFrozenStory
    @classmethod
    def freeze_feed(cls, feed_id=None, feed=None, verbose=True):
        extra_stories_count = 0
        if not feed_id and not feed:
            return extra_stories_count

        if not feed_id:
            feed_id = feed.pk
        if not feed:
            feed = feed_id

        cutoff = 100
        week_ago = datetime.datetime.utcnow() - datetime.timedelta(days=14)
        stories = cls.objects(story_feed_id=feed_id).order_by('-story_date')
        if stories.count() <= cutoff:
            return 0
        
        latest_week_stories = stories.filter(story_date__gte=week_ago)
        if latest_week_stories.count() > cutoff:
            extra_stories = stories.filter(story_date__lte=week_ago)
        else:
            extra_stories = stories[cutoff:]
        logging.debug(
                '   ---> [%-30s] ~FMFound %s stories. Frozen ~SB%s~SN...' %
                (unicode(feed)[:30], stories.count(), extra_stories.count()))

        frozen_num = 0
        for story in extra_stories:
            frozen_story = MFrozenStory(story)
            frozen_story.save()
            story.delete()
            frozen_num += 1
            if frozen_num % 10 == 0:
                print >>sys.stderr, '.',
        print >>sys.stderr, '.'
        logging.debug("   ---> Frozen %d stories." % (frozen_num,))
        # if verbose:
        #     existing_story_count = MStory.objects(
        #         story_feed_id=feed_id).count()
        #     logging.debug("   ---> Deleted %s stories, %s left." % (
        #         extra_stories_count,
        #         existing_story_count))

        return frozen_num

    @classmethod
    def find_story(cls, story_feed_id, story_id, original_only=False):
        from apps.social.models import MSharedStory
        original_found = False
        story_hash = cls.ensure_story_hash(story_id, story_feed_id)

        if isinstance(story_id, ObjectId):
            story = cls.objects(id=story_id).limit(1).first()
        else:
            story = cls.objects(story_hash=story_hash).limit(1).first()

        if story:
            original_found = True
        if not story and not original_only:
            story = MSharedStory.objects.filter(story_feed_id=story_feed_id,
                                                story_hash=story_hash).limit(1).first()
        if not story and not original_only:
            story = MStarredStory.objects.filter(story_feed_id=story_feed_id,
                                                 story_hash=story_hash).limit(1).first()

        return story, original_found

    @classmethod
    def find_by_id(cls, story_ids):
        from apps.social.models import MSharedStory
        count = len(story_ids)
        multiple = isinstance(story_ids, list) or isinstance(story_ids, tuple)

        stories = list(cls.objects(id__in=story_ids))
        if len(stories) < count:
            shared_stories = list(MSharedStory.objects(id__in=story_ids))
            stories.extend(shared_stories)

        if not multiple:
            stories = stories[0]

        return stories

    @classmethod
    def find_by_story_hashes(cls, story_hashes):
        from apps.social.models import MSharedStory
        count = len(story_hashes)
        multiple = isinstance(
            story_hashes, list) or isinstance(story_hashes, tuple)

        stories = list(cls.objects(story_hash__in=story_hashes))
        if len(stories) < count:
            hashes_found = [s.story_hash for s in stories]
            remaining_hashes = list(set(story_hashes) - set(hashes_found))
            story_feed_ids = [h.split(':')[0] for h in remaining_hashes]
            shared_stories = list(
                MSharedStory.objects(story_feed_id__in=story_feed_ids,
                                     story_hash__in=remaining_hashes))
            stories.extend(shared_stories)

        if not multiple:
            stories = stories[0]


        return stories

    @classmethod
    def ensure_story_hash(cls, story_id, story_feed_id):
        if not cls.RE_STORY_HASH.match(story_id):
            story_id = "%s:%s" % (
                story_feed_id, hashlib.sha1(story_id).hexdigest()[:6])

        return story_id

    @classmethod
    def split_story_hash(cls, story_hash):
        matches = cls.RE_STORY_HASH.match(story_hash)
        if matches:
            groups = matches.groups()
            return groups[0], groups[1]
        return None, None

    @classmethod
    def split_rs_key(cls, rs_key):
        matches = cls.RE_RS_KEY.match(rs_key)
        if matches:
            groups = matches.groups()
            return groups[0], groups[1]
        return None, None

    @classmethod
    def story_hashes(cls, story_ids):
        story_hashes = []
        for story_id in story_ids:
            story_hash = cls.ensure_story_hash(story_id)
            if not story_hash:
                continue
            story_hashes.append(story_hash)

        return story_hashes

    def sync_redis(self, r=None):
        # Disabled by Xinyan Lu: no unread cutoff
        return
        if not r:
            r = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL)
        # if not r2:
            # r2 = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL2)
        UNREAD_CUTOFF = datetime.datetime.now() - datetime.timedelta(
            days=settings.DAYS_OF_UNREAD_NEW)

        if self.id and self.story_date > UNREAD_CUTOFF:
            feed_key = 'F:%s' % self.story_feed_id
            r.sadd(feed_key, self.story_hash)
            r.expire(feed_key, settings.DAYS_OF_UNREAD_NEW * 24 * 60 * 60)
            # r2.sadd(feed_key, self.story_hash)
            # r2.expire(feed_key, settings.DAYS_OF_UNREAD_NEW*24*60*60)

            r.zadd('z' + feed_key, self.story_hash,
                   time.mktime(self.story_date.timetuple()))
            r.expire(
                'z' + feed_key, settings.DAYS_OF_UNREAD_NEW * 24 * 60 * 60)
            # r2.zadd('z' + feed_key, self.story_hash, time.mktime(self.story_date.timetuple()))
            # r2.expire('z' + feed_key, settings.DAYS_OF_UNREAD_NEW*24*60*60)

    def remove_from_redis(self, r=None):
        # Disabled by Xinyan Lu: no unread cutoff,see sync_redis above
        return
        if not r:
            r = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL)
        # if not r2:
        #     r2 = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL2)
        if self.id:
            r.srem('F:%s' % self.story_feed_id, self.story_hash)
            # r2.srem('F:%s' % self.story_feed_id, self.story_hash)
            r.zrem('zF:%s' % self.story_feed_id, self.story_hash)
            # r2.zrem('zF:%s' % self.story_feed_id, self.story_hash)

    @classmethod
    def sync_feed_redis(cls, story_feed_id):
        # Disabled by Xinyan Lu: no unread cutoff
        return
        r = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL)
        # r2 = redis.Redis(connection_pool=settings.REDIS_STORY_HASH_POOL2)
        UNREAD_CUTOFF = datetime.datetime.now() - datetime.timedelta(
            days=settings.DAYS_OF_UNREAD_NEW)
        feed = Feed.get_by_id(story_feed_id)
        stories = cls.objects.filter(
            story_feed_id=story_feed_id, story_date__gte=UNREAD_CUTOFF)
        r.delete('F:%s' % story_feed_id)
        # r2.delete('F:%s' % story_feed_id)
        r.delete('zF:%s' % story_feed_id)
        # r2.delete('zF:%s' % story_feed_id)

        logging.info("   ---> [%-30s] ~FMSyncing ~SB%s~SN stories to redis" %
                     (feed and feed.title[:30] or story_feed_id, stories.count()))
        p = r.pipeline()
        # p2 = r2.pipeline()
        for story in stories:
            story.sync_redis(r=p)
        p.execute()
        # p2.execute()

    def count_comments(self):
        from apps.social.models import MSharedStory
        params = {
            'story_guid': self.story_guid,
            'story_feed_id': self.story_feed_id,
        }
        comments = MSharedStory.objects.filter(
            has_comments=True, **params).only('user_id')
        shares = MSharedStory.objects.filter(**params).only('user_id')
        self.comment_count = comments.count()
        self.comment_user_ids = [c['user_id'] for c in comments]
        self.share_count = shares.count()
        self.share_user_ids = [s['user_id'] for s in shares]
        self.save()

    def extract_image_urls(self, force=False):
        if self.image_urls and not force:
            return self.image_urls

        story_content = self.story_content
        if not story_content and self.story_content_z:
            story_content = zlib.decompress(self.story_content_z)
        if not story_content:
            return

        try:
            soup = BeautifulSoup(story_content)
        except ValueError:
            return

        images = soup.findAll('img')
        if not images:
            return

        image_urls = []
        for image in images:
            image_url = image.get('src')
            if not image_url:
                continue
            if image_url and len(image_url) >= 1024:
                continue
            image_urls.append(image_url)

        if not image_urls:
            return

        self.image_urls = image_urls
        return self.image_urls

    def fetch_reference_images(self,force=False):
        if not self.id:
            raise IOError('Need a story id, save the story first')
        if not self.image_urls:
            return None

        if not force and len(self.image_ids)==len(self.image_urls):
            return self.image_ids

        
        
        def _1(image_url):
            if not image_url:
                return 'NE' # image_url == None

            # Filter images by URL patterns
            Filtered = False
            for c in IMAGE_BLACKLIST_FILTERS:
                if c.search(image_url):
                    Filtered = True
                    break
                
            if Filtered == True:
                # logging.debug('Image Filtered: %s'%image_url)
                return 'Filtered'

            existing_image = MImage.get_by_url(image_url)
            if existing_image:
                existing_image.save_append_story(self)
                # logging.debug('Image exists: %s'%image_url)
                return str(existing_image.id)

            imageid_or_code = 'NoneError'           
            try:
                image = MImage()
                image.process(image_url,self)
                image.save()
                imageid_or_code = str(image.id)
                # logging.user(None, ("~FYFetching ~FGreference~FY image from: %s" % str(image.id)))
            except (IOError,AssertionError),e:
                # record the error code
                imageid_or_code = str(e)
            except Exception,e:
                imageid_or_code = 'OtherError'
                logging.debug("Fetching image ~FY%s~FT with other error: ~FR%s~FT" % (image_url,str(e)))
            finally:
                return imageid_or_code

        # jobs = [gevent.spawn(_1,image_url) for image_url in self.image_urls]
        # gevent.joinall(jobs)
        # image_ids = [job.value for job in jobs]

        image_ids = [_1(image_url) for image_url in self.image_urls]
        
        self.image_ids = image_ids
        
        num_valid_images = len(filter(lambda x:len(x)>20,image_ids))
        if num_valid_images > 0:
            logging.debug("~FG%d~FT new images fetched." % num_valid_images)
        
        self.save()
        return image_ids


    def fetch_original_text(self, force=False, request=None):
        original_text_z = self.original_text_z
        feed = Feed.get_by_id(self.story_feed_id)

        if not original_text_z or force:
            try:
                ti = TextImporter(self, feed=feed, request=request)
                original_text = ti.fetch()
            except Exception,e:
                logging.debug("TypeErrorDebug(original_text): %s" %self.story_permalink)
                return ''
        else:
            logging.user(
                request, "~FYFetching ~FGoriginal~FY story text, ~SBfound.")
            original_text = zlib.decompress(original_text_z)

        return original_text


class MFrozenStory(mongo.Document):

    '''A feed item (Frozen)'''
    story_feed_id = mongo.IntField()
    story_date = mongo.DateTimeField()
    story_title = mongo.StringField(max_length=1024)
    story_content = mongo.StringField()
    story_content_z = mongo.BinaryField()
    story_original_content = mongo.StringField()
    story_original_content_z = mongo.BinaryField()
    story_latest_content = mongo.StringField()
    story_latest_content_z = mongo.BinaryField()
    original_text_z = mongo.BinaryField()
    story_content_type = mongo.StringField(max_length=255)
    story_author_name = mongo.StringField()
    story_permalink = mongo.StringField()
    story_guid = mongo.StringField()
    story_hash = mongo.StringField()
    image_urls = mongo.ListField(
        mongo.StringField(max_length=1024))
    # Add by Xinyan Lu : support images storage
    image_ids = mongo.ListField(mongo.StringField())
    story_tags = mongo.ListField(
        mongo.StringField(max_length=250))
    comment_count = mongo.IntField()
    comment_user_ids = mongo.ListField(mongo.IntField())
    share_count = mongo.IntField()
    share_user_ids = mongo.ListField(mongo.IntField())

    meta = {
        'collection': 'stories_frozen',
        'indexes': [('story_feed_id', '-story_date'),
                    {'fields': ['story_hash'],
                     'unique': True,
                     'types': False, }],
        'index_drop_dups': True,
        'ordering': ['-story_date'],
        'allow_inheritance': False,
        'cascade': False,
    }

    def __init__(self,mstory):
        super(MFrozenStory,self).__init__()
        if not isinstance(mstory,MStory):
            raise TypeError('Not a MStory object')
        if not mstory.id:
            raise AssertionError('To move to new collection, an ObjectID is needed.')
        self.story_feed_id = mstory.story_feed_id
        self.story_date = mstory.story_date
        self.story_title = mstory.story_title
        self.story_content = mstory.story_content
        self.story_content_z = mstory.story_content_z
        self.story_original_content = mstory.story_original_content
        self.story_original_content_z = mstory.story_original_content_z
        self.story_latest_content = mstory.story_latest_content
        self.story_latest_content_z = mstory.story_latest_content_z
        self.original_text_z = mstory.original_text_z
        self.story_content_type = mstory.story_content_type
        self.story_author_name = mstory.story_author_name
        self.story_permalink = mstory.story_permalink
        self.story_guid = mstory.story_guid
        self.story_hash = mstory.story_hash
        self.image_urls = mstory.image_urls
        self.image_ids = mstory.image_ids
        self.story_tags = mstory.story_tags
        self.comment_count = mstory.comment_count
        self.comment_user_ids = mstory.comment_user_ids
        self.share_count = mstory.share_count
        self.share_user_ids = mstory.share_user_ids
        # save with the same mongodb ObjectID
        self.id = mstory.id


    def save(self, *args, **kwargs):
        # store original story_content, or it will be erased
        story_content = self.story_content

        if self.story_content:
            self.story_content_z = zlib.compress(self.story_content)
            self.story_content = None
        if self.story_original_content:
            self.story_original_content_z = zlib.compress(
                self.story_original_content)
            self.story_original_content = None
        if self.story_latest_content:
            self.story_latest_content_z = zlib.compress(
                self.story_latest_content)
            self.story_latest_content = None
        # if self.story_title and len(self.story_title) > story_title_max:
        #     self.story_title = self.story_title[:story_title_max]
        # if self.story_content_type and len(self.story_content_type) > story_content_type_max:
        #     self.story_content_type = self.story_content_type[
        #         :story_content_type_max]
        super(MFrozenStory, self).save(*args, **kwargs)

        #Add by Xinyan Lu : index on save
        if not story_content and self.story_content_z:
            try:
                story_content = zlib.decompress(self.story_content_z)
            except Exception,e:
                story_content = ''
                pass
        index_content = story_content or ''
        if self.original_text_z:
            try:
                original_text = zlib.decompress(self.original_text_z)
            except Exception,e:
                original_text = ''
            if len(original_text) > 1.5 * len(index_content):
                index_content = original_text

        SearchStory.index(story_id=self.story_guid,
                            story_title=self.story_title,
                            story_content=index_content,
                            story_author=self.story_author_name,
                            story_date=self.story_date,
                            db_id=str(self.id),
                            frozen=True)

        return self




class MStarredStory(mongo.Document):

    """Like MStory, but not inherited due to large overhead of _cls and _type in
       mongoengine's inheritance model on every single row."""
    user_id = mongo.IntField(unique_with=('story_guid',))
    starred_date = mongo.DateTimeField()
    story_feed_id = mongo.IntField()
    story_date = mongo.DateTimeField()
    story_title = mongo.StringField(max_length=1024)
    story_content = mongo.StringField()
    story_content_z = mongo.BinaryField()
    story_original_content = mongo.StringField()
    story_original_content_z = mongo.BinaryField()
    original_text_z = mongo.BinaryField()
    story_content_type = mongo.StringField(max_length=255)
    story_author_name = mongo.StringField()
    story_permalink = mongo.StringField()
    story_guid = mongo.StringField()
    story_hash = mongo.StringField()
    story_tags = mongo.ListField(
        mongo.StringField(max_length=250))
    image_urls = mongo.ListField(
        mongo.StringField(max_length=1024))

    meta = {
        'collection': 'starred_stories',
        'indexes': [('user_id', '-starred_date'), ('user_id', 'story_feed_id'), 'story_feed_id'],
        'index_drop_dups': True,
        'ordering': ['-starred_date'],
        'allow_inheritance': False,
    }

    def save(self, *args, **kwargs):
        if self.story_content:
            self.story_content_z = zlib.compress(self.story_content)
            self.story_content = None
        if self.story_original_content:
            self.story_original_content_z = zlib.compress(
                self.story_original_content)
            self.story_original_content = None
        self.story_hash = self.feed_guid_hash

        return super(MStarredStory, self).save(*args, **kwargs)

        # self.index_for_search()

    def index_for_search(self):
        story_content = zlib.decompress(self.story_content_z)
        SearchStarredStory.index(user_id=self.user_id,
                                 story_id=self.story_guid,
                                 story_title=self.story_title,
                                 story_content=story_content,
                                 story_author=self.story_author_name,
                                 story_date=self.story_date,
                                 db_id=str(self.id))

    @classmethod
    def find_stories(cls, query, user_id, offset=0, limit=25):
        stories_db = cls.objects(
            Q(user_id=user_id) &
            (Q(story_title__icontains=query) |
             Q(story_author_name__icontains=query) |
             Q(story_tags__icontains=query))
        ).order_by('-starred_date')[offset:offset + limit]
        stories = Feed.format_stories(stories_db)

        return stories

    # Deleted by Xinyan Lu : No users
    # @classmethod
    # def trim_old_stories(cls, stories=10, days=30, dryrun=False):
    #     print " ---> Fetching starred story counts..."
    #     stats = settings.MONGODB.newsblur.starred_stories.aggregate([{
    #         "$group": {
    #             "_id":      "$user_id",
    #             "stories":  {"$sum": 1},
    #         },
    #     }, {
    #         "$match": {
    #             "stories": {"$gte": stories}
    #         },
    #     }])
    #     month_ago = datetime.datetime.now() - datetime.timedelta(days=days)
    #     user_ids = stats['result']
    #     user_ids = sorted(user_ids, key=lambda x: x['stories'], reverse=True)
    #     print " ---> Found %s users with more than %s starred stories" % (len(user_ids), stories)

    #     total = 0
    #     for stat in user_ids:
    #         try:
    #             user = User.objects.select_related(
    #                 'profile').get(pk=stat['_id'])
    #         except User.DoesNotExist:
    #             user = None

    #         if user and (user.profile.is_premium or user.profile.last_seen_on > month_ago):
    #             continue

    #         total += stat['stories']
    #         print " ---> %20.20s: %-20.20s %s stories" % (user and user.profile.last_seen_on or "Deleted",
    #                                                       user and user.username or " - ",
    #                                                       stat['stories'])
    #         if not dryrun and stat['_id']:
    #             cls.objects.filter(user_id=stat['_id']).delete()

    #     print " ---> Deleted %s stories in total." % total

    @property
    def guid_hash(self):
        return hashlib.sha1(self.story_guid).hexdigest()[:6]

    @property
    def feed_guid_hash(self):
        return "%s:%s" % (self.story_feed_id or "0", self.guid_hash)

    def fetch_original_text(self, force=False, request=None):
        original_text_z = self.original_text_z
        feed = Feed.get_by_id(self.story_feed_id)

        if not original_text_z or force:
            ti = TextImporter(self, feed, request=request)
            original_text = ti.fetch()
        else:
            logging.user(
                request, "~FYFetching ~FGoriginal~FY story text, ~SBfound.")
            original_text = zlib.decompress(original_text_z)

        return original_text


class MFetchHistory(mongo.Document):
    feed_id = mongo.IntField(unique=True)
    feed_fetch_history = mongo.DynamicField()
    page_fetch_history = mongo.DynamicField()
    push_history = mongo.DynamicField()

    meta = {
        'db_alias': 'nbanalytics',
        'collection': 'fetch_history',
        'allow_inheritance': False,
    }

    @classmethod
    def feed(cls, feed_id, timezone=None, fetch_history=None):
        if not fetch_history:
            try:
                fetch_history = cls.objects.read_preference(pymongo.ReadPreference.PRIMARY)\
                                           .get(feed_id=feed_id)
            except cls.DoesNotExist:
                fetch_history = cls.objects.create(feed_id=feed_id)
        history = {}

        for fetch_type in ['feed_fetch_history', 'page_fetch_history', 'push_history']:
            history[fetch_type] = getattr(fetch_history, fetch_type)
            if not history[fetch_type]:
                history[fetch_type] = []
            for f, fetch in enumerate(history[fetch_type]):
                date_key = 'push_date' if fetch_type == 'push_history' else 'fetch_date'
                history[fetch_type][f] = {
                    date_key: localtime_for_timezone(fetch[0],
                                                     timezone).strftime(
                                                         "%Y-%m-%d %H:%M:%S"),
                    'status_code': fetch[1],
                    'message': fetch[2]
                }
        return history

    @classmethod
    def add(cls, feed_id, fetch_type, date=None, message=None, code=None, exception=None):
        if not date:
            date = datetime.datetime.now()
        try:
            fetch_history = cls.objects.read_preference(pymongo.ReadPreference.PRIMARY)\
                                       .get(feed_id=feed_id)
        except cls.DoesNotExist:
            fetch_history = cls.objects.create(feed_id=feed_id)

        if fetch_type == 'feed':
            history = fetch_history.feed_fetch_history or []
        elif fetch_type == 'page':
            history = fetch_history.page_fetch_history or []
        elif fetch_type == 'push':
            history = fetch_history.push_history or []

        history = [[date, code, message]] + history
        if code and code >= 400:
            history = history[:50]
        else:
            history = history[:5]

        if fetch_type == 'feed':
            fetch_history.feed_fetch_history = history
        elif fetch_type == 'page':
            fetch_history.page_fetch_history = history
        elif fetch_type == 'push':
            fetch_history.push_history = history

        fetch_history.save()

        # Deleted by Xinyan Lu: This function is for feed fetch statistics shown in the page.
        # !!! Should be added back later
        # if fetch_type == 'feed':
            # RStats.add('feed_fetch')

        return cls.feed(feed_id, fetch_history=fetch_history)

# Deleted By Xinyan Lu : No DuplicateFeed currently.
# !!!should be added back
# class DuplicateFeed(models.Model):
#     duplicate_address = models.CharField(max_length=764, db_index=True)
#     duplicate_link = models.CharField(max_length=764, null=True, db_index=True)
#     duplicate_feed_id = models.CharField(
#         max_length=255, null=True, db_index=True)
#     feed = models.ForeignKey(Feed, related_name='duplicate_addresses')

#     def __unicode__(self):
#         return "%s: %s / %s" % (self.feed, self.duplicate_address, self.duplicate_link)

#     def canonical(self):
#         return {
#             'duplicate_address': self.duplicate_address,
#             'duplicate_link': self.duplicate_link,
#             'duplicate_feed_id': self.duplicate_feed_id,
#             'feed_id': self.feed_id
#         }

#     def save(self, *args, **kwargs):
#         max_address = DuplicateFeed._meta.get_field(
#             'duplicate_address').max_length
#         if len(self.duplicate_address) > max_address:
#             self.duplicate_address = self.duplicate_address[:max_address]
#         max_link = DuplicateFeed._meta.get_field('duplicate_link').max_length
#         if self.duplicate_link and len(self.duplicate_link) > max_link:
#             self.duplicate_link = self.duplicate_link[:max_link]

#         super(DuplicateFeed, self).save(*args, **kwargs)


# def merge_feeds(original_feed_id, duplicate_feed_id, force=False):
#     from apps.reader.models import UserSubscription
#     from apps.social.models import MSharedStory

#     if original_feed_id == duplicate_feed_id:
#         logging.info(" ***> Merging the same feed. Ignoring...")
#         return original_feed_id
#     try:
#         original_feed = Feed.objects.get(pk=original_feed_id)
#         duplicate_feed = Feed.objects.get(pk=duplicate_feed_id)
#     except Feed.DoesNotExist:
#         logging.info(" ***> Already deleted feed: %s" % duplicate_feed_id)
#         return original_feed_id

#     heavier_dupe = original_feed.num_subscribers < duplicate_feed.num_subscribers
#     branched_original = original_feed.branch_from_feed
#     if (heavier_dupe or branched_original) and not force:
#         original_feed, duplicate_feed = duplicate_feed, original_feed
#         original_feed_id, duplicate_feed_id = duplicate_feed_id, original_feed_id
#         if branched_original:
#             original_feed.feed_address = duplicate_feed.feed_address

#     logging.info(
#         " ---> Feed: [%s - %s] %s - %s" % (original_feed_id, duplicate_feed_id,
#                                            original_feed, original_feed.feed_link))
#     logging.info(
#         "            Orig ++> %s: (%s subs) %s / %s %s" % (original_feed.pk,
#                                                            original_feed.num_subscribers,
#                                                            original_feed.feed_address,
#                                                            original_feed.feed_link,
#                                                            " [B: %s]" % original_feed.branch_from_feed.pk if original_feed.branch_from_feed else ""))
#     logging.info(
#         "            Dupe --> %s: (%s subs) %s / %s %s" % (duplicate_feed.pk,
#                                                            duplicate_feed.num_subscribers,
#                                                            duplicate_feed.feed_address,
#                                                            duplicate_feed.feed_link,
#                                                            " [B: %s]" % duplicate_feed.branch_from_feed.pk if duplicate_feed.branch_from_feed else ""))

#     original_feed.branch_from_feed = None

#     user_subs = UserSubscription.objects.filter(
#         feed=duplicate_feed).order_by('-pk')
#     for user_sub in user_subs:
#         user_sub.switch_feed(original_feed, duplicate_feed)

#     def delete_story_feed(model, feed_field='feed_id'):
#         duplicate_stories = model.objects(**{feed_field: duplicate_feed.pk})
#         # if duplicate_stories.count():
#         #     logging.info(" ---> Deleting %s %s" % (duplicate_stories.count(), model))
#         duplicate_stories.delete()

#     delete_story_feed(MStory, 'story_feed_id')
#     delete_story_feed(MFeedPage, 'feed_id')

#     try:
#         DuplicateFeed.objects.create(
#             duplicate_address=duplicate_feed.feed_address,
#             duplicate_link=duplicate_feed.feed_link,
#             duplicate_feed_id=duplicate_feed.pk,
#             feed=original_feed
#         )
#     except (IntegrityError, OperationError), e:
#         logging.info(" ***> Could not save DuplicateFeed: %s" % e)

#     # Switch this dupe feed's dupe feeds over to the new original.
#     duplicate_feeds_duplicate_feeds = DuplicateFeed.objects.filter(
#         feed=duplicate_feed)
#     for dupe_feed in duplicate_feeds_duplicate_feeds:
#         dupe_feed.feed = original_feed
#         dupe_feed.duplicate_feed_id = duplicate_feed.pk
#         dupe_feed.save()

#     logging.debug(
#         ' ---> Dupe subscribers (%s): %s, Original subscribers (%s): %s' %
#         (duplicate_feed.pk, duplicate_feed.num_subscribers,
#          original_feed.pk, original_feed.num_subscribers))
#     if duplicate_feed.pk != original_feed.pk:
#         duplicate_feed.delete()
#     else:
#         logging.debug(
#             " ***> Duplicate feed is the same as original feed. Panic!")
#     logging.debug(' ---> Deleted duplicate feed: %s/%s' %
#                   (duplicate_feed, duplicate_feed_id))
#     original_feed.branch_from_feed = None
#     original_feed.count_subscribers()
#     original_feed.save()
#     logging.debug(' ---> Now original subscribers: %s' %
#                   (original_feed.num_subscribers))

#     MSharedStory.switch_feed(original_feed_id, duplicate_feed_id)

#     return original_feed_id


def rewrite_folders(folders, original_feed, duplicate_feed):
    new_folders = []

    for k, folder in enumerate(folders):
        if isinstance(folder, int):
            if folder == duplicate_feed.pk:
                # logging.info("              ===> Rewrote %s'th item: %s" % (k+1, folders))
                new_folders.append(original_feed.pk)
            else:
                new_folders.append(folder)
        elif isinstance(folder, dict):
            for f_k, f_v in folder.items():
                new_folders.append(
                    {f_k: rewrite_folders(f_v, original_feed, duplicate_feed)})

    return new_folders

class MImage(mongo.Document):

    '''An Image item'''
    image_guid = mongo.StringField(required=True) #the URL
    image_hash = mongo.StringField(required=True)
    image_size = mongo.IntField()
    image_type = mongo.StringField()
    image_width = mongo.IntField()
    image_height = mongo.IntField()
    image_remote_id = mongo.StringField()
    story_ids = mongo.ListField(mongo.StringField(),required=True)
    image_has_error = mongo.BooleanField(required=True,default=False)
    image_error_code = mongo.StringField()

    last_reference_date = mongo.DateTimeField()
    # store the image buffer
    image_buffer = None


    meta = {
        'collection': 'images',
        'indexes': ['image_hash','last_reference_date'],
        'index_drop_dups': False,
        'allow_inheritance': False,
        'cascade': False,
    }

    def process(self,url,story,client=None,verbose=False):
        if self.exists_image(url) == True:
            raise IntegrityError('Image has been in the datatabase')

        self.image_guid = url
        self.image_hash = self.guid_hash
        self.story_ids = [str(story.id)]
        self.image_has_error = False
        try:
            self.image_buffer = self._fetch_image(story_url=story.story_guid).read()
        except IOError:
            self.image_has_error = True
            self.image_error_code = 'FETCH ERROR'
            logging.debug('   ---> [%s] ~SN~FRFetch Error on image: %s' % (
                            story.story_guid, self.image_guid))
            raise IOError('Fetch Error')

        # Now we have the buffer, test if it's an image
        num_trial = 0
        while num_trial < 3:
            num_trial +=1
            try:
                image = Image.open(cStringIO.StringIO(self.image_buffer))
                image.load()
                break
            except (IOError,IndexError),e:
                # file download corrupted, retry
                if 'truncated' in str(e) or 'index' in str(e):
                    self.image_buffer = self._fetch_image(story_url=story.story_guid).read()
                    logging.debug('  ---> [%s] ~FYRetry with image: %s' % (
                        story.story_guid, self.image_guid))
                    continue
                self.image_has_error = True
                self.image_error_code = 'DECODE ERROR'
                if verbose:
                    logging.debug('   ---> [%s] ~SN~FRDecode Error on image: %s' % (
                                story.story_guid, self.image_guid))
                raise IOError('Decode Error')

        self.image_type = image.format
        self.image_size = len(self.image_buffer)
        self.image_width, self.image_height = image.size
        # discard images with small width or height
        if self.image_width < 150 or self.image_height < 150:
            # I think to raise an Exception is better..
            # since there are many images with only 1 pixel and different url, see CNN
            # should add some regrex patterns to filter the indifferent images to save bandwidth
            if verbose:
                logging.debug('   ---> [%s] ~SN~FRLow definition~FW on image:~FR %s' % (
                            story.story_guid, self.image_guid))
            raise AssertionError('Low definition')
            self.image_has_error = True
            self.image_error_code = 'LOW DEFINITION'
            return

        # now upload the image to FastDFS
        ret = self._upload_by_buffer(client=client) # much better if a client is given
        if ret['Status'] == 'Upload successed.':
            self.image_remote_id = ret['Remote file_id']
        else:
            self.image_has_error = True
            self.image_error_code = 'UPLOAD ERROR'
            logging.debug('   ---> [%s] ~SN~FRUpload Error on image: %s' % (
                            story.story_guid, self.image_guid))
            return
        if verbose:
            logging.debug(' -Successfully create image: %s' % self.image_guid)

    @property
    def guid_hash(self):
        return hashlib.sha1(self.image_guid).hexdigest()[:8]

    @classmethod
    def get_by_url(cls,url):
        url_hash = hashlib.sha1(url).hexdigest()[:8]
        images = cls.objects(image_hash=url_hash)
        if len(images) == 0:
            return None
        for image in images:
            if image.image_guid == url:
                return image
        return None

    @classmethod
    def exists_image(cls,url):
        if cls.get_by_url(url) == None:
            return False
        else:
            return True


    def _fetch_image(self,story_url=None,cow=False):
        handlers = []
        if cow:
            handlers.append(urllib2.ProxyHandler({'http':settings.COW_PROXY_HANDLER,\
                'https':settings.COW_PROXY_HANDLER}))
        opener = urllib2.build_opener(*tuple(handlers))
        request = urllib2.Request(self.image_guid)
        request.add_header('User-Agent','Mozilla/5.0')
        # some sites may limit image access
        if story_url:
            request.add_header('Referer',story_url)
        opener.addheaders = [] # RMK - must clear so we only send our custom User-Agent

        try:
            return opener.open(request)
        finally:
            opener.close() # JohnD

    def _upload_by_buffer(self,client=None):
        if not client:
            client = Fdfs_client(settings.FDFS_CLIENT_CONF_PATH)
        file_ext_name = self.image_type.lower()
        meta_dict = {
            'ext_name' : file_ext_name,
            'file_size' : self.image_size,
            'width' : self.image_width,
            'height' : self.image_height
        }
        return client.upload_by_buffer(self.image_buffer,file_ext_name=file_ext_name,meta_dict=meta_dict)

    def save_append_story(self,story):
        story_id = str(story.id)
        if story_id not in self.story_ids:
            self.story_ids.append(story_id)
            self.save()

    def save(self,*args,**kwargs):
        try:
            self.last_reference_date = datetime.datetime.utcnow()
            super(MImage,self).save(*args,**kwargs)
        except Exception,e:
            logging.error('Saving MImage with: ~FR%s~FW',str(e))

    def delete(self,*args,**kwargs):
        client = Fdfs_client(settings.FDFS_CLIENT_CONF_PATH)
        if self.image_remote_id:
            try:
                client.delete_file(str(self.image_remote_id))
            except DataError:
                logging.debug('File Not Exists:',self.image_remote_id)
                pass
        # deal with reference id?
        super(MImage, self).delete(*args, **kwargs)

    @classmethod
    def drop(cls,*args,**kwargs):
        images = cls.objects.all()
        for image in images:
            image.delete()


