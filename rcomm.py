#!/usr/bin/python3

"""
Copyright (C) 2019 fusionRobotics,inc

    auth: marco.ma@waven.com
"""

import os
import sys
import time
import socket
import fcntl
import serial
import select
import termios
import logging
import threading
from queue import Queue
import platform
import conf
from serial import Serial
from crc import custom_crc32
import json
import crcmod
class Singleton(type):
    _instances = {},

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(
                Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class DictObj( object ):

    def __init__(self, p_dict):

        for i in p_dict:
            setattr(self, i, p_dict[i])

def _search_device(trace):
    while 1:
        try:
            rev = os.listdir('/dev/serial/by-id/')
            for d in rev:
                if d.find('FTDI') > 0:
                    y_usb_state=0
                    conf.DEV_LIST[0]['dev_name']='/dev/serial/by-id/'+d
                    trace.info('found FTDI device:%s' %conf.DEV_LIST[0]['dev_name'])
                    return rev
        except Exception as ex:
            trace.error('no serial port found?!')

class Rcomm( threading.Thread ):
    __metaclass__ = Singleton

    def __init__(self, trace):
        super(Rcomm, self).__init__()
        self.trace = trace
        self._stop_event = threading.Event()
        curDir = os.path.abspath(os.path.dirname(__file__))
        self.jsonPath = os.path.join(curDir,  "d2.json")
        
        assert len(conf.DEV_LIST) == 1
        self.rlink_usb_cnt=0
        self.fkc_usb_cnt=0
        self.spring_select_mode_flag=0
        #pcname=socket.getfqdn(socket.gethostname())
        pcname=platform.node()
        self.trace.info('%s'%pcname)
        if pcname.find('rui') is 0:
            #self.trace.info('hello m3')
            #_Y_search_device(self.trace )
            #self.xmodem_crc_func = crcmod.mkCrcFun(0x11021, rev=False,
            #                                        initCrc=0xffff, xorOut=0x0000)
            pass
        elif pcname.find('rui') is 0:
            #self.trace.info('hello m3')
            #self.trace.info('hello test Y')
            #_Y_search_device(self.trace )
            #self.xmodem_crc_func = crcmod.mkCrcFun(0x11021, rev=False,
            #                                        initCrc=0xffff, xorOut=0x0000)
            pass
        _search_device(self.trace)
        dev_dict = {}
        for d in conf.DEV_LIST:
            dev_dict[d['name']] = DictObj(d)

        self.dev_comb = DictObj(dev_dict)
        self.open_dev()
 
    def join(self, timeout=1):
        self._stop_event.set()
        super(Rcomm, self).join(timeout)
        
    def close_dev(self):   
        self.dev_comb.dev_list = []
        for d in conf.DEV_LIST:
            dev = getattr(self.dev_comb, d['name'])
            if hasattr(dev, 'ser'):
                try:
                    dev.ser.close()
                except:
                    pass 
    def open_dev(self):
        self.dev_comb.dev_list = []
        for d in conf.DEV_LIST:
            dev = getattr(self.dev_comb, d['name'])
            if hasattr(dev, 'ser'):
                try:
                    dev.ser.close()
                except:
                    pass
            try:
                dev.ser = serial.Serial(dev.dev_name, baudrate=dev.baud, timeout=dev.timeout)
                dev._lock = threading.RLock()
                dev.q = Queue()
                self.trace.debug('dev: %s opened' %dev.name)
                dev.fileno = dev.ser.fileno
                self.dev_comb.dev_list.append(dev)
            except Exception as ex:
                self.trace.error('failed to open device: %s as %s' %(dev.name, ex))
                dev.ser = None
                dev.fileno = -1
    def process_drop_json(self,cabinet,r='r',state='open'):
        drop_list=['drop_1','drop_2','drop_3']
        if r=='r':
            f=open(self.jsonPath,encoding='utf-8')
            content=f.read()
            user_dict = json.loads(content)
            if user_dict[drop_list[cabinet-1]]=='BLOCK' or user_dict[drop_list[cabinet-1]]=='OPEN':
                return user_dict[drop_list[cabinet-1]]
            else:
                trace.error('json error-->%s'%user_dict[drop_list[cabinet-1]])
                return 'BLOCK'
        else: 
            with open(self.jsonPath, "r",encoding='utf-8') as jsonFile:
                data=json.load(jsonFile)
                data[drop_list[cabinet-1]]=state
            with open(self.jsonPath, "w") as jsonFile:
                json.dump(data, jsonFile,ensure_ascii=False)
            return True
    def process_rx(self, r_list):
        # self.trace.info(r_list)
        for d in r_list:
            self.trace.info('read: %s' %(d.name))
            try:
                time.sleep(0.0525)
                data = d.ser.read(d.ser.in_waiting)
                self.trace.info('data -> %s' %data)
                d.q.put(data)
            except Exception as ex:
                self.trace.error('failed to read dev: %s as %s' %(d.name, ex))
                try:
                    self.open_dev()
                except:
                    self.trace("failed to open dev")
    
    def run(self):
        for name in self.dev_comb.dev_list:
            self.dev_flush(name)

        while not self._stop_event.is_set():
            r,_,_ = select.select(self.dev_comb.dev_list, [], [], 0.5)
            if not r:
                continue
            else:
                self.process_rx(r)
    
    def dev_send(self, dev, data):
        try:
            self.dev_flush(dev)
            dev.ser.write(data)
            return True
        except Exception as ex:
            self.trace.error('failed to write dev: %s' %ex)
            return False
    
    def gen_frame(self, addr,cmd, para=''):
        frame = '%c%c%s' %(addr, cmd, para)
        crc =self.xmodem_crc_func(frame.encode('latin-1'))
        frame += (chr(crc >> 8)) + chr(crc & 0xff)
        return frame
    def send(self,addr, dev, cmd, para='', timeout=0.5):
        self.trace.info('send data-->%s'%self.gen_frame(addr,cmd,para).encode('latin-1'))
        return self.dev_send(dev,self.gen_frame(addr,cmd,para).encode('latin-1'))
    
    def dev_flush(self, dev):
        try:
            self.trace.debug('flush %s' % dev.name)
            dev.ser.flush()
            dev.ser.flushInput()
            dev.ser.flushOutput()
            dev.q.queue.clear()
            self.rlink_usb_cnt=0
            self.fkc_usb_cnt=0
        except Exception as ex:
            self.trace.error('failed to flush %s -> %s' % (dev.name, ex))
            self.rlink_usb_cnt=self.rlink_usb_cnt+1
            if self.rlink_usb_cnt==5 and self.fkc_usb_cnt<10:
                if self.fkc_usb_cnt==9:
                    self.trace.error('fkcusb stop')    
                self.fkc_usb_cnt=self.fkc_usb_cnt+1
                self.rlink_usb_cnt=0
                self.trace.error('failed to link usb five times')
                os.system('sudo /home/fusion/kiosk/sbin/fuckusb /dev/bus/usb/001/002')
                time.sleep(3)
                os.system('/home/fusion/kiosk/bin/rotate.sh')
            self.open_dev()


##########
if __name__ == "__main__":

    trace = logging.getLogger()
    trace.setLevel(logging.INFO)

    formatter = logging.Formatter(fmt="%(asctime)s %(filename)s[line:%(lineno)d]%(levelname)s - %(message)s",
                                    datefmt="%m/%d/%Y %I:%M:%S %p")

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(formatter)
    trace.addHandler(console)

    trace.info('rcomm module')

    rcomm = Rcomm(trace)
    rcomm.start()

    while 1:
        time.sleep(1)
    
    rcomm.join()
