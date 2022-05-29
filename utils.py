#!/usr/bin/python

"""
Copyright (C) 2015  Waven,inc
Written by Marco <marco.ma@waven.com>
"""

import os
import re
import sys
import time
import atexit
import threading
import signal

import socket
import fcntl
import struct


class Daemon( object ):
    """
    a generic daemon class.
    
    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdin='/dev/stdin', stdout='/dev/stdout', stderr='/dev/stderr'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
    
    def daemonize(self):
        old_evn = os.environ
        
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit first parent
                sys.exit(0) 
        except OSError as e: 
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)
    
        os.environ = old_evn
        
        # decouple from parent environment
        #os.chdir("/")
        os.setsid() 
        os.umask(0) 
    
        # do second fork
        try: 
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0) 
        except OSError as e: 
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1) 
        
        os.environ = old_evn
        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        try:
            si = open(self.stdin, 'r')
            so = open(self.stdout, 'a+')
            se = open(self.stderr, 'a+')
            
            os.dup2(si.fileno(), sys.stdin.fileno())
            os.dup2(so.fileno(), sys.stdout.fileno())
            os.dup2(se.fileno(), sys.stderr.fileno())
        except Exception as ex:
            with open('/tmp/alive', 'a+') as fd:
                fd.write('----> error' + str(ex) + '\n')
        
        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        
        fd = open(self.pidfile,'w+')
        fd.write("%s\n" % pid)
        fd.close()
    
    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = open(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
        except Exception as ex:
            print(ex)
            pid = False
    
        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        
        # Start the daemon
        sys.stderr.write('launching....\n')
        self.daemonize()
        with open('/tmp/alive', 'a+') as fd:
            fd.write('----> ' + 'ready to run' + '\n')
        self.run()

    def stop(self):
        """
        Stop the daemon
        """
        # Get the pid from the pidfile
        try:
            pf = open(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
        except Exception as ce:
            print(ce)
            pid = False
    
        if not pid:
            message = "pidfile %s does not exit. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            return # not an error in a restart

        # Try killing the daemon process    
        try:
            print('kill..')
            time.sleep(0.5)
            os.kill(pid, signal.SIGTERM)
            
            count = 0
            while 1:
                count += 1
                time.sleep(1.5)
                if count > 5:
                    count = 0
                    print('KILL FORCE!')
                    try:
                        os.remove(self.pidfile)
                    except:
                        pass
                    os.kill(pid, signal.SIGKILL)
                else:
                    os.kill(pid, signal.SIGTERM)
                print('kill..')
        except OSError as err:
            err = str(err)
            if err.find("No such process") > 0 or err.find("Operation not permitted") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print((str(err)))
                sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        with open('/tmp/alive', 'a+') as fd:
            fd.write('----> ' + 'restart' + '\n')
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """


class Timer( threading.Thread ):

    def __init__(self, callback, interval):

        self.callback = callback
        self.interval = interval
        super(Timer, self).__init__()
        self._stop_event = threading.Event()
        
    def join(self):
        self._stop_event.set()
        super(Timer, self).join()
        
    def run(self):
        while True:
            
            for _ in range(int(self.interval*1000)):
                if self._stop_event.isSet():
                    return
                time.sleep(0.001)
                
            if self.callback() is False:
                self._stop_event.set()
                    
    def set_interval(self, interval):
        self.interval = interval

def extern_if(fn):
    setattr(fn, '__extern_if__', True)
    return fn

def get_extern_if(obj, cmd):
    func = getattr(obj, cmd, False)
    if func:
        if getattr(func, '__extern_if__', False):
            return func
        else:
            return False # has the function but no flag
    else:
        return None # no such function

def search_all_extern_if(obj):
    rev = list()
    try:
        for i in dir(obj):
            if get_extern_if(obj, i):
                rev.append(i)
        return rev
    except Exception as ex:
        print(ex)
        return [None,None]

def gen_parameters(func, *args):
    para = '( '
    for i in args:
        if i.find('=') >= 0:
            pass
        elif not re.match('^[0-9]+.[0-9]+|[0-9]+$', i):
            i = '"' + i + '"'
        para += i + ','
    para = para[:-1] + ' )'
    return para

def get_if_addr(ifname):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rev = socket.inet_ntoa(fcntl.ioctl(
            s.fileno(),
            0x8915,  # SIOCGIFADDR
            struct.pack('256s', ifname[:15]))[20:24])
    except:
        rev = ''
    
    return rev
def str2int(sdata):
    if len(sdata)==1:
        idata=ord(sdata)
        if idata<58:
            idata=idata-48
            return idata
        elif idata>96 and idata<103:
            idata=idata-87
            return idata
        else:
            return False
    elif len(sdata)==2:
        idata_h=ord(sdata[0])
        if idata_h<58:
            idata_h=idata_h-48
        elif idata_h>96 and idata_h<103:
            idata_h=idata_h-87
        idata_l=ord(sdata[1])
        if idata_l<58:
            idata_l=idata_h-48
        elif idata_l>96 and idata_l<103:
            idata_l=idata_l-87
        idata=idata_h*16+idata_l
        return idata
    else:
        return False
        
def bstr2int(sdata):
    if len(sdata)==1:
        idata=sdata[0]
        if idata<58:
            idata=idata-48
            return idata
        elif idata>96 and idata<103:
            idata=idata-87
            return idata
        else:
            return False
    elif len(sdata)==2:
        idata_h=sdata[0]
        if idata_h<58:
            idata_h=idata_h-48
        elif idata_h>96 and idata_h<103:
            idata_h=idata_h-87
            
        idata_l=sdata[1]
        if idata_l<58:
            idata_l=idata_l-48
        elif idata_l>96 and idata_l<103:
            idata_l=idata_l-87
        idata=idata_h*16+idata_l
        return idata
    else:
        return False



