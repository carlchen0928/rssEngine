#!/usr/bin/python
import unittest
import urllib2
import time
import logging
from logging.handlers import RotatingFileHandler

class TestUrlHttpcode():
	def setUp(self):
		urlinfo = ['http://www.baidu.com','http://twitter.com']
		#urlinfo = ['http://www.baidu.com', 'http://www.163.com', 'http://www.csdn.net/']  
		self.checkurl = urlinfo
		self.opener = urllib2.build_opener(urllib2.ProxyHandler({'http':'http://127.0.0.1:7777','https':'http://127.0.0.1:7777'}))
		# urllib2.install_opener(opener)

	def test_ipv6_google(self):
		ipv6_addr = 'http://ipv6.google.com'
		try:
			print ipv6_addr
			httpcode = 0
			httpcode = urllib2.urlopen(ipv6_addr).getcode()
			print httpcode
		except urllib2.URLError,e:
			print e
			pass
		finally:
			logger.debug('%s status:[%d]'%(ipv6_addr,httpcode))

	def test_other(self):
		for m in self.checkurl:
			try:
				print m
				httpcode = 0
				httpcode = self.opener.open(m).getcode()	
				print httpcode
							
			except urllib2.URLError,e:
				print e #urlopen error timed out
				pass
			finally:
				logger.debug('%s status:[%d]'%(m,httpcode))
				# self.assertEqual(httpcode,200)
			

if __name__ == '__main__':
	logger = logging.getLogger()
	logger.level = logging.DEBUG
	formatter = logging.Formatter('[%(asctime)-12s] %(message)s')
	log_handler = RotatingFileHandler(filename='cow.log' , mode="a" , maxBytes=16777216)
	log_handler.setFormatter(formatter)
	logger.addHandler(log_handler)
	testUrlHttpcode = TestUrlHttpcode()
	testUrlHttpcode.setUp()
	while True:
		testUrlHttpcode.test_ipv6_google()
		testUrlHttpcode.test_other()
		time.sleep(60)