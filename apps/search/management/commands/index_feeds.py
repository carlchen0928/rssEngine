from django.core.management.base import BaseCommand
from django.conf import settings
from apps.rss_feeds.models import Feed,MStory
from apps.search.models import SearchStory
from optparse import make_option
from utils.management_functions import daemonize
import django
import socket
import datetime
import time
import zlib
from utils import log as logging


class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option("-d", "--daemon", dest="daemonize", action="store_true"),
        make_option("-F", "--force", dest="force", action="store_true"),
        make_option('-t', '--timeout', type='int', default=10,
            help='Wait timeout in seconds when connecting to feeds.'),
        make_option('-V', '--verbose', action='store_true',
            dest='verbose', default=False, help='Verbose output.'),
        # Added by Xinyan Lu: domain and id based feed refresh
        make_option('','--domain',type='str',dest='domain'),
        make_option('','--id',type='int',dest='id'),
    )

    def handle(self, *args, **options):
        if options['daemonize']:
            daemonize()
        
        settings.LOG_TO_STREAM = True        
            
        # Added by Xinyan Lu: domain based feed refresh
        if options['domain']:
            feeds = Feed.objects.filter(feed_address__contains=options['domain'])
        elif options['id']:
            feeds = Feed.objects.filter(id=options['id'])
        elif options['force']:
            # feeds = Feed.objects.all()
            feeds = Feed.objects.filter(num_subscribers__gt=2)
        else:
            feeds = Feed.objects.filter(next_scheduled_update__lte=now, active=True)
        
        feeds = feeds.order_by('?')

        num_feeds = len(feeds)
        i=0
        for feed in feeds:
            start = time.time()
            i += 1
            stories = MStory.objects(story_feed_id=feed.pk)
            for story in stories:
                if story.story_content_z:
                    story_content = zlib.decompress(story.story_content_z)
                else:
                    story_content = ''
                SearchStory.index(story_id=story.story_guid,
                                 story_title=story.story_title,
                                 story_content=story_content,
                                 story_author=story.story_author_name,
                                 story_date=story.story_date,
                                 db_id=str(story.id))
            delta = time.time() - start
            done_msg = (u'---> [%-30s] ~FYProcessed in ~FM~SB%.4ss~FY~SN ~FB%d~FY[%d]' % (
                feed.feed_title[:30],delta, num_feeds,i,))
            logging.debug(done_msg)
        print 'Index fetch done!'

        
