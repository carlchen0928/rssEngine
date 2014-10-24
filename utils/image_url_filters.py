import re
from django.conf import settings

IMAGE_BLACKLIST_FILTERS = []

def read_from_file(filepath=settings.IMAGE_URL_BLACKLIST):
	global IMAGE_BLACKLIST_FILTERS

	fp = open(filepath)
	IMAGE_BLACKLIST_FILTERS = []
	for line in fp.readlines():
		line = line.strip()
		if len(line)==0 or line.startswith('#'):
			continue

		#treat as domain filter
		if line.startswith('^') == False: 
			line = line.replace('.','\.')
			line = line.replace('-','\-')
			c = re.compile('^(http|https|ftp)\://[^/]*'+line+'.*$')
		else:
			c = re.compile(line)
			
		IMAGE_BLACKLIST_FILTERS.append(c)

