#!/usr/bin/python
import StringIO
import pickle
import redis
import psutil
import datetime
import time
import urllib2

from django.conf import settings
#settings.configure()
#import settings

class NetworkMonitor():
  Common_urls = ['http://www.baidu.com','http://twitter.com']
  #Ipv6_urls = ['http://ipv6.google.com']
  #Common_urls = ['http://www.baidu.com']
  Ipv6_urls = ['http://www.sina.com.cn']
  Opener = urllib2.build_opener(urllib2.ProxyHandler({'http':settings.COW_PROXY_HANDLER,'https':settings.COW_PROXY_HANDLER}))
  #Opener = urllib2.build_opener(urllib2.ProxyHandler({'http':'http://10.214.34.221:7777','https':'http://10.214.34.221:7777'}))
  #Opener = urllib2.build_opener()

  @staticmethod
  def test():

    log_info = {}
    total_start = time.time()
    interfaces = ['eth0']
    bytes_recv_start = 0
    bytes_sent_start = 0
    for interface in interfaces:
      bytes_recv_start += psutil.net_io_counters(pernic=True)[interface].bytes_recv
      bytes_sent_start += psutil.net_io_counters(pernic=True)[interface].bytes_sent
    # test common urls
    print bytes_recv_start
    print bytes_sent_start
    for m in NetworkMonitor.Common_urls:
      log_info[m] = {}
      try:
        start = time.time()
        httpcode = 0
        httpcode = NetworkMonitor.Opener.open(m).getcode()
      except urllib2.URLError,e:
        print 'here'
        print 'Exception:'
        print e #urlopen error timed out
        pass
      finally:
        stop = time.time()
        log_info[m]['httpcode'] = httpcode
        # response_time is in ms
        log_info[m]['response_time'] = int((stop -  start) * 1000)

    # test ipv6
    for m in NetworkMonitor.Ipv6_urls:
      log_info[m] = {}
      try:
        start = time.time()
        httpcode = 0
        httpcode = urllib2.urlopen(m).getcode()
      except urllib2.URLError,e:
        print 'there'
        print 'Exception:'
        print e
        pass
      finally:
        stop = time.time()
        log_info[m]['httpcode'] = httpcode
        # response_time is in ms
        log_info[m]['response_time'] = int((stop -  start) * 1000)

    # io counter
    bytes_recv_end = 0
    bytes_sent_end = 0
    for interface in interfaces:
      bytes_recv_end = psutil.net_io_counters(pernic=True)[interface].bytes_recv
      bytes_sent_end += psutil.net_io_counters(pernic=True)[interface].bytes_sent

    print bytes_recv_end
    print bytes_sent_end
    time_cost = int(time.time() - total_start)
    if time_cost == 0:
        time_cost = 1
    log_info['network_io'] = {
        'bytes_recv' : (bytes_recv_end - bytes_recv_start)/time_cost,
        'bytes_sent' : (bytes_sent_end - bytes_sent_start)/time_cost,
        }
    #print log_info
    if log_info["network_io"]["bytes_recv"] < 0:
      return

    # store log_info to redis
    r = redis.Redis(connection_pool=settings.REDIS_NETWORK_POOL)
    #r = redis.Redis(connection_pool=redis.ConnectionPool(host="172.21.1.155", port=6379, db=6))
    logdb = settings.REDIS_NETWORK_LOG_NAME
    #logdb = 'network_log'
    log_info['time'] = int(time.time())
    log_s = pickle.dumps(log_info)
    print log_info
    #print log_s
    r.rpush(logdb,log_s)
    if r.llen(logdb) > settings.REDIS_NETWORK_LOG_MAX:
      r.lpop(logdb)

if __name__ == '__main__':
  NetworkMonitor.test()
