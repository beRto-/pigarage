# PiGarage
More than once, I accidentally left my garage open over night. I decided to address this problem by building an automated solution to let me know whenever the door was open for an extended period of time. I put a switch on the garage door, and connected it to a Raspberry Pi. The Pi monitors the door state and compares against alarms I have defined.

During the day, it is expected that the door might be open for say 30 minutes - so an alarm is not triggered unless the door has been open longer than that. But at night, I don't expect the door to me open for longer than maybe 2 minutes (just coming or going) - so an alarm is triggered sooner. The alarm consists of an SMS text message (sent using the Twilio service).

Each garage door open / close event is logged in an SQLite database. This allows for historical tracking, which is used to send a daily summary text message letting me know the number of times the door was opened and closed that day. 


# Hardware
The hardware for this project is simple, consisting of a single switch connected to a Raspberry Pi. The switch is a ![magnetic Reed switch](https://www.sparkfun.com/products/13247) connected on the main garage door. One side of this switch is connected to 5V on the Raspberry Pi, and the other side to an input pin (the software is currently configured for pin 38).

Pin 38 is normally pulled down / LOW signal:
```
GPIO.setmode(GPIO.BOARD)
GPIO.setup(CHANNEL_GARAGE_DOOR_STATE, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
```

When the door is opened, the magnetic reed switch connects pin 38 to HIGH, which triggers the Pi to recognize a door open event.


# Software and Database
Door open / close events get logged to an SQLite database (example database schema provided).

In practice, detecting a door open / close event is not as straightforward as looking for the magnetic switch to open / close. The reason is that garage doors tend to have some "slop" and so they can move around (changing the switch state) just from blowing wind, etc. Debouncing is needed to differentiate between a real door opening event, and a false alarm from a momentary door shake.

Debouncing is handled by the "has_garage_door_state_changed" function. It simply checks that X consecutive readings are the same (set to 3 in the code) before recognizing that as a "real" state. For example, the switch needs to report "door open" 3 times in a row before the software considers the door to actually be open.
```
# check that:
# 1) reading has changed (oldest reading not same as newest)
# 2) state reading were persistent (i.e. same readings in debound period)
if (self.garage_door_state_history[0]['door_state'] != self.garage_door_state_history[-1]['door_state']
    and all(new_state_container[0]['door_state'] == reading['door_state'] for reading in new_state_container)
    and all(old_state_container[0]['door_state'] == reading['door_state'] for reading in old_state_container)
```


# Alarms and SMS Text Messaging
Alarms are specified according to a schedule (daytime vs after_hours). For example:

An after hours alarm ("night alarm") is defined as triggering on 'DOOROPEN' event longer than 2 minutes, between 10PM (20:00) and 10AM (10:00). If an alarm is triggered, wait at least 30 minutes before sending another text message alarm:
```
    after_hours_door_alarm = smsAlarmHandler( 'night alarm', sms_butler, user_phone_number, GARAGE_DOOR_STATE_GPIO_MAP['DOOROPEN'], 2, (20,10), 30, debug_mode=debug_mode, verbose=verbose )
```

Similarly, a daytime alarm ("day_alarm") is sent for DOOROPEN longer than 30 minutes between 10AM and 10PM. Wait 2h between consecutive alarms sent:
```
    daytime_door_alarm = smsAlarmHandler( 'day alarm', sms_butler, user_phone_number, GARAGE_DOOR_STATE_GPIO_MAP['DOOROPEN'], 30, (10,20), 120, debug_mode=debug_mode, verbose=verbose )
```


In order to send text messages, you will need a ![Twilio](www.twilio.com) account and Auth token (the details should be saved in a local file "twilio.txt"). There is some account setup needed, which is not covered here because Twilio has some good tutorials for getting started. To begin, you can use a free trial account that works the exact same way as a full account but runs out of credit after several months.
