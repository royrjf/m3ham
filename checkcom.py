#!/usr/bin/python3

import os
import sys
import time
import fcntl
import serial
import select
import termios
import logging
import threading
import json
from queue import Queue
import conf
import platform

class Checkusb( threading.Thread ):
    def __init__(self, trace):
        super(Checkusb, self).__init__()
        self.trace = trace
        self._stop_event = threading.Event()
        self.do_have_aux_machine=0
        self.cabinet_cnt=1
        self.err_cnt=0
        self.reset_cnt=0
        
        self.usb_poll_state=[1,1,1]
        
        self.usb_link_time=0
        self.last_link_time=0
        self.usb_err_cnt=0
    def join(self, timeout=1):
        self._stop_event.set()
        super(Checkusb, self).join(timeout)
        
    def fkcusb(self,data):
        self.trace.info('reset usb %s times' %data)
        os.system('sudo /home/fusion/kiosk/sbin/fuckusb /dev/bus/usb/001/002')
        time.sleep(3)
        os.system('/home/fusion/kiosk/bin/rotate.sh')    
    def check_usb(self,usb):
        usb1=0
        usb2=0
        if usb.count('usb-fusionRobotics_D1_b0001-if00-port0'):
            if usb.count('usb-fusionRobotics_D1_b0001-if00-port0'):
                if usb.count('usb-fusionRobotics_D1_b0001-if00-port0'):
                    if usb.count('usb-fusionRobotics_D1_b0001-if00-port0'):
                        usb1=1
        if usb.count('usb-fusionRobotics_D2_b0001-if00-port0'):
            if usb.count('usb-fusionRobotics_D2_b0001-if00-port0'):
                if usb.count('usb-fusionRobotics_D2_b0001-if00-port0'):
                    if usb.count('usb-fusionRobotics_D2_b0001-if00-port0'):
                        usb2=1
        return usb1,usb2
    def run(self):
        usb1=0
        usb2=0
        self.trace.info('hello checkcom')
        pcname=platform.node()
        #if pcname.find('rui'):
        #    pass
        #else:
        #    self.trace.info('hello checkcom rui')
         #   while not self._stop_event.is_set():
          #      time.sleep(0.1)
        if pcname.find('rui') and pcname.find('Y') :
            pass
        else:
            self.trace.info('hello checkcom Y')
            while not self._stop_event.is_set():
                time.sleep(0.1)
        while not self._stop_event.is_set():
            time.sleep(0.1)
            if self.cabinet_cnt==1:
                try:
                    usb_dir=os.listdir('/dev/serial/by-id/')
                    if len(usb_dir)>=4:
                        self.usb_link_time=time.time()
                        if self.err_cnt>0:
                            self.trace.info('----->%s'%(self.usb_link_time-self.last_link_time))
                            if self.usb_link_time-self.last_link_time>1:
                                self.usb_poll_state[0]=1
                                self.err_cnt=0
                    else:
                        self.usb_err_cnt+=1
                        self.last_link_time=time.time()
                        self.trace.warn("cabinet 1 usb err")
                        self.err_cnt+=1
                        self.usb_poll_state[0]=0
                        if self.err_cnt==10:
                            self.err_cnt=1
                            self.reset_cnt+=1
                            if self.reset_cnt>3:
                                time.sleep(2)
                            else:
                                self.fkcusb(self.reset_cnt)
                except:
                    self.usb_err_cnt+=1
                    self.last_link_time=time.time()
                    self.trace.warn("cabinet 1 usb error")
                    self.err_cnt+=1
                    self.usb_poll_state[0]=0
                    if self.err_cnt==30:
                        self.err_cnt=1
                        self.reset_cnt+=1
                        if self.reset_cnt>3:
                            time.sleep(2)
                        else:
                            #self.fkcusb(self.reset_cnt)
                            pass
            else:
                try:
                    usb_dir=os.listdir('/dev/serial/by-id/')
 
                    if len(usb_dir)>=8:
                        self.usb_link_time=time.time()
                        if self.err_cnt>0:
                            self.trace.info('----->%s'%(self.usb_link_time-self.last_link_time))
                            if self.usb_link_time-self.last_link_time>1:
                                self.usb_poll_state[0]=1
                                self.usb_poll_state[1]=1
                                self.usb_poll_state[2]=1
                                self.err_cnt=0
                    else:
                        self.usb_err_cnt+=1
                        self.trace.warn("cabinet 1 usb err")
                        self.err_cnt+=1
                        usb1,usb2=self.check_usb(usb_dir)
                        if usb1==0:
                            self.usb_poll_state[0]=0
                        if usb2==0:
                            self.usb_poll_state[1]=0
                            self.usb_poll_state[2]=0
                        if self.err_cnt==10:
                            self.err_cnt=1
                            self.reset_cnt+=1
                            if self.reset_cnt>3:
                                time.sleep(2)
                            else:
                                self.fkcusb(self.reset_cnt)
                except:
                    self.usb_err_cnt+=1
                    self.last_link_time=time.time()
                    self.trace.warn("cabinet 1 usb error")
                    self.err_cnt+=1
                    self.usb_poll_state[0]=0
                    self.usb_poll_state[1]=0
                    self.usb_poll_state[2]=0
                    if self.err_cnt==30:
                        self.err_cnt=1
                        self.reset_cnt+=1
                        if self.reset_cnt>3:
                            time.sleep(2)
                        else:
                            self.fkcusb(self.reset_cnt)
            
