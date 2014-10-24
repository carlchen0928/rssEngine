from django.conf.urls import patterns, include, url
import settings
# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    url(r'^(?P<page_num>\d*)$', 'apps.rss_feeds.views.index', name='index'),
    url(r'^feed_(?P<feed_id>\d*)/$', 'apps.rss_feeds.views.feedParsedItems'),
    url(r'^Stories_(?P<page_num>\d*)/$', 'apps.rss_feeds.views.showStories'),

    # Modified By Xinyan Lu : I got a 'feed_id not defined' error
    # url(r'^feed_(?P<feed_id>\d*)$', 'apps.rss_feeds.views.showFeedItems',{'feed_id':feed_id}),
    url(r'^feed/(?P<feed_id>\d*)$', 'apps.rss_feeds.views.showFeedItems',name='showFeedItems'),
    url(r'^search/(?P<page_num>\d*)$', 'apps.search.views.index', name='search'),
    url(r'^imagesearch/(?P<page_num>\d*)$', 'apps.search.views.imagesearch', name='imagesearch'),
    url(r'^stat/+$','apps.statistics.views.stat',name='stat'),
    url(r'^stat/get$','apps.statistics.views.get_stat'),

    #added by lourenjie
    url(r'^speed/+$','apps.statistics.views.speed',name='speed'),
 # Modified by Dapeng Jiang : add network monitor view
    url(r'^monitor/+$','apps.statistics.views.monitor'),
    url(r'^monitor/get$','apps.statistics.views.get_logs'),

    #Modified By Songjun : 1. add showOriginalStory
    url(r'^Story_(?P<story_id_or_hash>\S*)_(?P<force>\d)$', 'apps.rss_feeds.views.showOriginalStory'),

    # url(r'^django_rss/', include('django_rss.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    # url(r'^admin/', include(admin.site.urls)),
)
