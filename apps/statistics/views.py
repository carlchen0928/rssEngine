from django.http import HttpResponse
from BeautifulSoup import BeautifulSoup
from django.conf import settings
from django.shortcuts import render, render_to_response
from utils import json_functions as mjson
from apps.rss_feeds.models import MStory,MImage,MFrozenStory
from mongoengine.queryset import Q
import psutil
import redis
import pickle
from django.conf import settings
import datetime
import json
def stat(request):
	return render(request,'stat.html',)

def speed(request):
	day = json.load(open('/home/udms/rssengine/rssengine/static/daily.json', 'r'))
        hour = json.load(open('/home/udms/rssengine/rssengine/static/hourly.json','r'))

        s_oneh=hour['story'][0]
        s_sixh=0
        for i in range(0,6):
		if i==len(hour['story']):
			break
                s_sixh+=hour['story'][i]
        s_oned=day['story'][0]
        s_onew=0
        for i in range(0,7):
		if i==len(day['story']):
                        break
                s_onew+=day['story'][i]
        s_onem=0
        for i in range(0,30):
		if i==len(day['story']):
                        break
                s_onem+=day['story'][i]
        s_sixm=0
        for i in range(0,180):
		if i==len(day['story']):
                        break
                s_sixm+=day['story'][i]
        s_oney=0
        for i in range(0,360):
		if i==len(day['story']):
                        break
                s_oney+=day['story'][i]

        i_oneh=hour['image'][0]
        i_sixh=0
        for i in range(0,6):
		if i==len(hour['image']):
                        break
                i_sixh+=hour['image'][i]
        i_oned=day['image'][0]
        i_onew=0
        for i in range(0,7):
		if i==len(day['image']):
                        break
                i_onew+=day['image'][i]
        i_onem=0
        for i in range(0,30):
		if i==len(day['image']):
                        break
                i_onem+=day['image'][i]
        i_sixm=0
	for i in range(0,180):
		if i==len(day['image']):
                        break
                i_sixm+=day['image'][i]
        i_oney=0
        for i in range(0,360):
		if i==len(day['image']):
                        break
                i_oney+=day['image'][i]

        context = {'speed_story':[s_oneh,s_sixh,s_oned,s_onew,s_onem,s_sixm,s_oney],
                   'speed_image':[i_oneh,i_sixh,i_oned,i_onew,i_onem,i_sixm,i_oney]}
	return render(request,'speed.html',context)

@mjson.json_view
def get_stat(request):
    num_stories = MStory.objects.count()
    num_images = MImage.objects.count()
    num_frozen_stories = MFrozenStory.objects.count()
    t=psutil.disk_usage('/home/')
    free_disk_space = t.free/1024/1024
    response = dict(num_stories=num_stories, 
                    num_frozen_stories=num_frozen_stories,
                    num_images=num_images,
                    free_disk_space=free_disk_space)
    
    return response

def monitor(request):
  logs = get_logs(request)
  return render(request,'monitor.html', logs)

@mjson.json_view
def get_logs(request):
  r = redis.Redis(connection_pool=settings.REDIS_NETWORK_POOL)
  name = settings.REDIS_NETWORK_LOG_NAME
  logs = r.lrange(name,- settings.REDIS_NETWORK_LOG_MAX,-1)
  logs_dict = [pickle.loads(log) for log in logs]
  return logs_dict
