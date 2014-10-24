#!/bin/bash
cd ..
screen -d -m -S celery_beat python manage.py celery worker -B -Q beat_feeds_task,beat_tasks
echo restart celery_beat OK!
