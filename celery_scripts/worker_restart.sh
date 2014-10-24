#!/bin/bash
cd ..
screen -d -m -S rss_worker python manage.py celery worker -c 50 -Q update_feeds,beat_feeds_task,beat_tasks --loglevel=info --autoreload
echo restart rss_worker OK!
#i=0
#while ((i<8))
#do	
#	screen -d -m -S worker_${i} python manage.py celery worker -Q update_feeds,beat_feeds_task --loglevel=info --autoreload
#	echo restart worker_${i} OK!
	# ((i++))
#done
