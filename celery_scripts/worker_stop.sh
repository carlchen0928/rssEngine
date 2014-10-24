#!/bin/bash
cd ..
# screen -X -S rss_worker quit
kill $(ps h --ppid $(screen -ls | grep rss_worker | cut -d. -f1) -o pid)
echo stop rss_worker OK!

#i=0
#while ((i<8))
#do
#        screen -X -S worker_${i} quit
#        echo stop worker_${i} OK!
#        ((i++))
#done
