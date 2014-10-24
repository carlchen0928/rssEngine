from django.core.management.base import BaseCommand
from django.conf import settings
from apps.rss_feeds.models import Feed,MStory,MImage
from apps.rss_feeds.tasks import UpdateFeedImages
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
        # Added by Xinyan Lu: domain and id based image refresh
        make_option('','--domain',type='str',dest='domain'),
        make_option('','--id',type='int',dest='id'),
        make_option('','--deleteall',action='store_true',dest='deleteall',default=False)
    )

    def handle(self, *args, **options):
        if options['deleteall']:
            MImage.drop()
            return

        if options['daemonize']:
            daemonize()
        
        settings.LOG_TO_STREAM = True        
            
        # Added by Xinyan Lu: domain based feed refresh
        if options['domain']:
            feeds = Feed.objects.filter(feed_address__contains=options['domain'])
        elif options['id']:
            feeds = Feed.objects.filter(id=options['id'])
        else:
            feeds = Feed.objects.filter(num_subscribers__gte=1)
        
        # feeds = feeds.order_by('?')

        num_feeds = len(feeds)
        print 'num feeds',num_feeds
        for feed in feeds:
            UpdateFeedImages.apply_async(args=(feed.pk,), queue='update_feed_images')
        print 'dispatch done'

        
