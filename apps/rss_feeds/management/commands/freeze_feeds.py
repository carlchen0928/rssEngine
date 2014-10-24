from django.core.management.base import BaseCommand
from django.conf import settings
from apps.rss_feeds.models import Feed,MStory,MImage
from apps.rss_feeds.tasks import FreezeFeeds
from apps.search.models import SearchStory
from optparse import make_option
from utils.management_functions import daemonize
import django
import socket
import datetime
import time
import zlib
import redis
import sys
import traceback
from utils import log as logging




class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option("-d", "--daemon", dest="daemonize", action="store_true"),
        make_option("-F", "--force", dest="force", action="store_true"),
        make_option('-t', '--timeout', type='int', default=10,
            help='Wait timeout in seconds when connecting to feeds.'),
        make_option('-V', '--verbose', action='store_true',
            dest='verbose', default=False, help='Verbose output.'),
        # Added by Xinyan Lu: domain and id based image refresh
        make_option('','--init',action='store_true',dest='initialize',
            default=False,help='Initialize freeze feed queue'),
        # make_option('','--id',type='int',dest='id'),
        # make_option('','--deleteall',action='store_true',dest='deleteall',default=False)
    )

    def handle(self, *args, **options):
        
        if options['daemonize']:
            daemonize()
        
        settings.LOG_TO_STREAM = True        
            
        r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
        
        if options['initialize']:
            feeds = Feed.objects.filter(num_subscribers__gte=1).order_by('?')
            print 'Query feeds done with num of feeds',len(feeds)
            r.ltrim('freeze_feeds',1,0)

            pipeline = r.pipeline()
            for feed in feeds:
                pipeline.rpush('freeze_feeds',feed.pk)
            pipeline.execute()
            print 'Initialize freeze_feeds done'

        feed_id = r.lpop('freeze_feeds')
        while feed_id:
            try:
                frozen_num = MStory.freeze_feed(int(feed_id))
                if frozen_num > 0:
                    r.rpush('freeze_feeds',feed_id)
            except Exception, e:
                logging.error(str(e)+\
                            traceback.format_exc()+'\n'+\
                            'Error from:  freeze_feeds\n')
            feed_id = r.lpop('freeze_feeds')
        print 'Done!'

        
