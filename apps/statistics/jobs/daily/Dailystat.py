from django_extensions.management.jobs import DailyJob
class Job(DailyJob):
	help = "statistics of Rssengine Daily"	
	def execute(self):
	    from utils import json_functions as json
	    from apps.rss_feeds.models import MStory,MImage,MFrozenStory
	    from django.conf import settings
	    from datetime import datetime
	    import json
	    import os
	    
	    num_stories = MStory.objects.count()
            num_frozen_stories = MFrozenStory.objects.count()
            num_images = MImage.objects.count()

	    if os.path.exists('static/daily.json') :
		 stat = json.load(open('static/daily.json', 'r'))
                 stat['image'].insert(0,num_images-stat['image_size'])
                 if(len(stat['image'])>500):
                         stat['image'].pop(-1)
                 stat['story'].insert(0,num_stories+num_frozen_stories-stat['story_size'])
                 if(len(stat['story'])>500):
                         stat['story'].pop(-1)
                 stat['story_size'] = num_stories+num_frozen_stories
                 stat['image_size'] = num_images
                 json.dump(stat, open('static/daily.json', 'w'))
                 return
	    else:
		 stat={'image':[num_images],
                      'story':[num_stories+num_frozen_stories],
                      'image_size':num_images,
                      'story_size':num_stories+num_frozen_stories
                 }
                 json.dump(stat, open('static/daily.json', 'w'))
                 return
