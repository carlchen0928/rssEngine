#!/bin/bash
cd ..
screen -d -m -S rss_beat python manage.py celery worker -B -Q beat_feeds_task,beat_tasks --loglevel=info --autoreload
echo start rss_beat OK!
#i=0
#while ((i<8))
#do	
#	screen -d -m -S worker_${i} python manage.py celery worker -Q update_feeds,beat_feeds_task --loglevel=info --autoreload
#	echo restart worker_${i} OK!
#	((i++))
#done
