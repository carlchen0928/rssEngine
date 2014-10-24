#!/bin/bash
cd ..
# screen -X -S rss_beat quit
kill $(ps h --ppid $(screen -ls | grep rss_beat | cut -d. -f1) -o pid)
echo stop rss_beat OK!

#i=0
#while ((i<8))
#do
#        screen -X -S worker_${i} quit
#        echo stop worker_${i} OK!
#        ((i++))
#done
