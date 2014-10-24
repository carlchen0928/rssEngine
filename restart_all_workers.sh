#!/bin/bash
cd celery_scripts/
./beat_stop.sh
./beat_start.sh
./worker_stop.sh
./worker_restart.sh
#./celery_beat_stop.sh
#./celery_beat_restart.sh


