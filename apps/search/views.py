from django.shortcuts import render, render_to_response
from django.core.paginator import Paginator
from django.db.models import Q
from django.conf import settings
from models import SearchStory
from apps.rss_feeds.models import MImage,MStory


def index(request,page_num):
	if page_num == '':
		page_num = '1'
	page_num = int(page_num)
	num_per_page = 15
	q = request.GET.get('q',None)
	
	if q:
		stories = SearchStory.query(q)[:30]
	return render(request,'search.html',locals())

def imagesearch(request,page_num):
	if page_num == '':
		page_num = '1'
	page_num = int(page_num)
	num_per_page = 15

	q = request.GET.get('q',None)
	if q:
		image_server = settings.FDFS_HTTP_SERVER
		index_stories = SearchStory.query(q)[:500]
		response_images = []
		for index_story in index_stories:
			story = MStory.objects(id=index_story['db_id']).first()	
			if story and story.image_ids:
				for image_id in story.image_ids:
					if len(image_id) > 20:
						# print image_id
						image = MImage.objects(id=image_id).first()
						imagedict = dict(
							image_url=image_server+image.image_remote_id,
							story_url=story.story_guid,
							story_title = story.story_title,
							)
						response_images.append(imagedict)
						if len(response_images)>=50:
							return render(request,'imagesearch.html',locals())
	return render(request,'imagesearch.html',locals())
