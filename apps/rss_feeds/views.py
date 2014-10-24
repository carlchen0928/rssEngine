import datetime
from django.shortcuts import render, render_to_response
from django.core.paginator import Paginator
from django.db.models import Q
from models import Feed, MStory, MImage
from django.http import HttpResponse
from utils import feedparser
from apps.rss_feeds.text_importer import TextImporter
from BeautifulSoup import BeautifulSoup

from django.conf import settings
import redis

import urllib2

def index(request,page_num):
	if page_num == '':
		page_num = '1'
	page_num = int(page_num)
	num_per_page = 15
	keyword = request.GET.get('q','')
	sortby = request.GET.get('sortby','numsubscribers')
	
	if keyword:
		collec = Feed.objects.filter(Q(feed_link__contains=keyword) | Q(feed_title__contains=keyword))
	else:
		collec = Feed.objects.filter(num_subscribers__gte=2)

	if sortby == 'numsubscribers':
		collec = collec.order_by('-num_subscribers')
	elif sortby == 'hasexception':
		collec = collec.order_by('-has_feed_exception','-num_subscribers')
	elif sortby == 'nextupdate':
		collec = collec.order_by('next_scheduled_update')
	elif sortby == 'lastupdate':
		collec = collec.order_by('-last_update')
	
	feeds = Paginator(collec,num_per_page)
	now = datetime.datetime.utcnow()
	context = {'feeds':feeds.page(page_num),'num_pages':feeds.num_pages,'q':keyword,'now':now,'sortby':sortby}
	return render(request,'feed.html',context)

def showFeedItems(request, feed_id):
	feed = Feed.objects.get(id=feed_id)
	#items = feedparser.parse(feed.feed_address).entries
	items = feed.get_stories()
	return render_to_response('feed_items.html',locals())

def showStories(request, page_num):
	page_num = int(page_num)
	num_per_page=20
	#stories = MStory.objects[(page_num-1)*10:(page_num)*10-1]
	collec = MStory.objects.order_by("-story_date")
	collec = Paginator(collec, num_per_page)
	stories = collec.page(page_num)
	# print stories[0]['id']
	# print stories[0]['story_hash']
	return render_to_response( 'stories.html', locals())

def showOriginalStory(request, story_id_or_hash, force):
	force = bool(int(force))
	# r = redis.Redis(connection_pool=settings.REDIS_FEED_POOL)
	# ind = r.zscore('scheduled_updates',104525)
	# print "the score of 104525 is : %s" %ind
	if ':' in story_id_or_hash:
		story = MStory.objects.get(story_hash = story_id_or_hash)
	else:
		story = MStory.objects.get(id = story_id_or_hash)
	# original_text = story.fetch_original_text(force=bool(force))
	if force:
		original_text = story.fetch_original_text(force=force)
	else:
		original_text = story.story_tidy_content
	#print "1" + '~'*100
	#print story.story_permalink
	#print type(story.story_permalink)
	soup = BeautifulSoup(str(original_text))
	# text = soup.text
	imgs = soup.findAll('img')
	img_urls=[]
	for img in imgs:
		img_urls.append(img.get('src'))
	return render_to_response('showOriginalStory.html',locals())

def feedParsedItems(request, feed_id):
    feed = Feed.objects.get(id=feed_id)
    items = feedparser.parse(feed.feed_address).entries
    #print feed.feed_address
    #print items
    return render_to_response('feed_parsed_items.html',locals())
