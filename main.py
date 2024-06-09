# NTP Timer

# Imports
import time 
import utime
import network # for Wifi
from machine import Pin, PWM # for output

# using https://mpython.readthedocs.io/en/master/library/micropython/ntptime.html
import ntptime

# to not show Wifi credentials in this code
from secrets import secrets

FS_ct = 65535 #set max scale for meters to 2.7V
FS_v = 3.3 #Vsupply

# gpio pins for meters
out_pins = {'hours':0,'minutes':1,'seconds':2}
out_handles = {'hours':machine.Pin(out_pins['hours'], machine.Pin.OUT),'minutes':machine.Pin(out_pins['minutes'], machine.Pin.OUT),'seconds':machine.Pin(out_pins['seconds'], machine.Pin.OUT)}
out_pwms = {'hours':PWM(out_handles['hours']),'minutes':PWM(out_handles['minutes']),'seconds':PWM(out_handles['seconds'])}
out_FS = {'hours':int(FS_ct*3.3/FS_v),'minutes':int(FS_ct*3.3/FS_v),'seconds':int(FS_ct*3.3/FS_v)}
frequency = 20000
for key in out_pwms.keys():
    out_pwms[key].freq (frequency)

#GPIO Pins for Time_Zone
TZ_pins = {'sign':21,'h10_8':8,'h10_4':9,'h10_2':10,'h10_1':11,'h1_8':12,'h1_4':13,'h1_2':14,'h1_1':15,'m5_8':19,'m5_4':18,'m5_2':17,'m5_1':16}
TZ_handles = {}

TZ_offset = 0

for key, value in TZ_pins.items():
    TZ_handles[key] = Pin(value, Pin.IN, Pin.PULL_UP)

def print_TZ(TZ):
    for key, value in TZ.items():
        print(f'{key} : {value.value()}', end=' ')
    print(' ')
    
def compute_offset(TZ):
    if TZ['sign'].value():
        sign = -1
    else:
        sign = 1
        
    hr10 = 8 * (not TZ['h10_8'].value()) + 4 * (not TZ['h10_4'].value()) + 2 * (not TZ['h10_2'].value()) + 1 * (not TZ['h10_1'].value())
    hr1 = 8 * (not TZ['h1_8'].value()) + 4 * (not TZ['h1_4'].value()) + 2 * (not TZ['h1_2'].value()) + 1 * (not TZ['h1_1'].value())
    m5 = 8 * (not TZ['m5_8'].value()) + 4 * (not TZ['m5_4'].value()) + 2 * (not TZ['m5_2'].value()) + 1 * (not TZ['m5_1'].value())
    offset = sign * ((hr10*10+hr1)*60+5*m5)
    return offset
      
def update_time_buttons(offset):
    global TZ_offset
    global time_is_set
    old_time = time.time()
    new_time = old_time+offset*60
    print(f'TZ Changed, updating. Old time:{old_time}, New time:{new_time}');
    t = time.gmtime(time.time()+offset*60)
    print(t)
    machine.RTC().datetime((t[tm_year], t[tm_mon], t[tm_mday], t[tm_wday] + 1, t[tm_hour], t[tm_min], t[tm_sec], 0))
    TZ_offset = offset
    time_is_set = time.time()

# Constants
UTC_OFFSET = 2 * 60 * 60 # in seconds
#UTC_OFFSET = 0 # in seconds

# Make naming more convenient
# See: https://docs.python.org/3/library/time.html#time.struct_time
tm_year = 0
tm_mon = 1 # range [1, 12]
tm_mday = 2 # range [1, 31]
tm_hour = 3 # range [0, 23]
tm_min = 4 # range [0, 59]
tm_sec = 5 # range [0, 61] in strftime() description
tm_wday = 6 # range 8[0, 6] Monday = 0
tm_yday = 7 # range [0, 366]
tm_isdst = 8 # 0, 1 or -1 

# Global to check if time is set
time_is_set = None
wifi_is_connected = False

# Logging
import os
logfile = open('log.txt', 'a')
# duplicate stdout and stderr to the log file
os.dupterm(logfile)

"""
   wifi_connect() function. Called by set_time()
   Parameters: None
   Return: None
"""
def wifi_connect():
    # Load login data from different file for safety reasons
    ssid = secrets['ssid']
    password = secrets['pw']
    print(ssid)
    print(password)

    # Connect to WiFi
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    max_wait = 10
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('waiting for connection...')
        time.sleep(5)

        if wlan.status() != 3:
            raise RuntimeError('network connection failed')
        else:
            print('connected')
            wifi_is_connected = True
            status = wlan.ifconfig()
            print( 'ip = ' + status[0] )
    
"""
   cet_time() function. Called by set_time()
   Parameters: None
   Return: cet
"""
# DST calculations
# This code returns the Central European Time (CET) including daylight saving
# Winter (CET) is UTC+1H Summer (CEST) is UTC+2H
# Changes happen last Sundays of March (CEST) and October (CET) at 01:00 UTC
# Ref. formulas : http://www.webexhibits.org/daylightsaving/i.html
#                 Since 1996, valid through 2099


def us_time(timezone=-8):
    year = time.localtime()[0]       #get current year
    DSTStart = time.mktime((year,3,14-int(1 + year*5/4)%7,1,0,0,0,0,0)) #Time of March change to CEST
    DSTEnd = time.mktime((year,11,7-int(1 + year*5/4)%7,1,0,0,0,0,0)) #Time of October change to CET
    now=time.time()
    if now < DSTStart :               # we are before last sunday of march
        lt=time.localtime(now+3600*timezone) # CET:  UTC+1H
        print("Standard time, before DST")
    elif now < DSTEnd :           # we are before last sunday of october
        lt=time.localtime(now+3600*(timezone+1)) # CEST: UTC+2H
        print("DST Active")
    else:                            # we are after last sunday of october
        lt=time.localtime(now+3600*timezone) # CET:  UTC+1H
        print("Standard time, after DST")
    return(lt)

"""
   set_time() function. Called by main()
   Parameters: None
   Return: None
"""
def set_time():
    global time_is_set
    # ntp_host = ["0.europe.pool.ntp.org", "1.europe.pool.ntp.org", "2.europe.pool.ntp.org", "3.europe.pool.ntp.org"] # Not used
    
    if not wifi_is_connected:
        print("Wifi is not connected, connecting")
        wifi_connect()
    print("UTC time before synchronization：%s" %str(time.localtime()))
    
    # if needed, we'll cycle over ntp-servers here using:
    # ntptime.host = "1.europe.pool.ntp.org"
    
    try:
        ntptime.settime()
    except OSError as exc:
        if exc.args[0] == 110: # ETIMEDOUT
            print("ETIMEDOUT. Returning False")
            time.sleep(5)
    print("UTC time after synchronization：%s" %str(time.localtime()))
    
    offset = compute_offset(TZ_handles)
    print(f'Offset = {offset}')
    update_time_buttons(offset)
    
    #t = time.localtime(time.time() + UTC_OFFSET) # Apply UTC offset
#     t = us_time()
#     print("US time after synchronization : %s" %str(t))
    
    # Set local clock to adjusted time
    # commented out to use front panel instead
#     machine.RTC().datetime((t[tm_year], t[tm_mon], t[tm_mday], t[tm_wday] + 1, t[tm_hour], t[tm_min], t[tm_sec], 0))
#     print("Local time after synchronization：%s" %str(time.localtime()))    
#     time_is_set = time.time()
#     print("Set Time!")
#     print(time_is_set)
    
    #WLAN.disconnect()
    #print("Disconnected WiFi")

"""
    schedule() function
    Parameters: t
    Return: none
"""
# import door_operations # script that you want to execute on a certain moment

# Todo: create crontab like structure with: minute / hour / day of month / month / day of week / command
# Todo: check what happens when scheduled tasks overlap (uasyncio)

def schedule(t):
    global TZ_offset
    #update displays
    
    out_pwms['seconds'].duty_u16(int(t[5]/60*out_FS['seconds']))
    out_pwms['minutes'].duty_u16(int(t[4]/60*out_FS['minutes']))
    out_pwms['hours'].duty_u16(int((t[3]%12)/12*out_FS['hours']))
    
    
    offset = compute_offset(TZ_handles)
    if offset != TZ_offset:
        ntptime.settime()
        print(f'Offset = {offset}')
        update_time_buttons(offset)
#     if t[tm_hour] == 17 and t[tm_min] == 45 and t[tm_sec] == 00: # Define seconds, or it will run every second...
#         print("Executing doorOperations")
#         door_operations.closeDoor()
#     
#     if t[tm_hour] == 07 and t[tm_min] == 45 and t[tm_sec] == 00: # Define seconds, or it will run every second...
#         print("Executing doorOperations")
#         door_operations.openDoor()
#     
#     # Sync clock every day
#     if t[tm_hour] == 08 and t[tm_min] == 15 and t[tm_sec] == 0:
#         time_is_set = False
#         print("Synchronizing time")
#         set_time()
    return True

"""
   main() function.
   Parameters: None
   Return: None
"""

resynch_interval = 1 #days

def main():
    if not time_is_set:
        set_time()
        
    t = time.localtime()
    o_sec = time.localtime()[5]

    while True:
        t = time.localtime()
        if  o_sec != t[5]:
            o_sec = t[5]
            schedule(t)
        if not time_is_set is None:
            if time.time() > (time_is_set + resynch_interval * 86400): #seconds/day
                set_time()
        else:
            print('time_is_set is None!');



if __name__ == '__main__':
    main()