#!/usr/bin/python

import os
import sys
import datetime as dt
import time
import sqlite3

import RPi.GPIO as GPIO
import gpio_pigarage_sql as pidb
import gpio_pigarage_sms_handler as pisms


CHANNEL_GARAGE_DOOR_STATE = 38

# door uses a normally open switch (LOW / open switch when door is closed and switch engaged; HIGH when door is open)
GARAGE_DOOR_STATE_GPIO_MAP = {'DOOROPEN':1, 'DOORCLOSED':0}


class smsAlarmHandler():
    def __init__(self, alarm_name, sms_butler, phone_to_sms_on_alarm, garage_door_state_alarm_event, alarm_event_duration_minutes=0, time_of_day_bounds=(0,0), min_minutes_between_sms = 30, debug_mode=False, verbose=True):
    # example use: send sms if door is open (alarm_event) more than 5 min (duration) and time is after 8:00PM (time_bounds)
        self.alarm_name = alarm_name
        self.sms_butler = sms_butler
        self.phone_to_sms_on_alarm = phone_to_sms_on_alarm
        self.garage_door_state_alarm_event = garage_door_state_alarm_event
        self.alarm_event_duration_seconds = alarm_event_duration_minutes * 60
        self.min_seconds_between_sms = min_minutes_between_sms * 60
        self.time_of_day_bounds = time_of_day_bounds
        self.datetime_last_alarm_outright_start = None
        self.datetime_last_alarm_counter_start = None
        self.datetime_last_alarm_sms_triggered = None
        self.debug_mode = debug_mode
        self.verbose = verbose

    def check_alarm_bounds_on_same_date(self, time_now):
        time_start_of_current_day = dt.datetime.combine(time_now.date(), dt.datetime.min.time())
        if ( time_now >= (time_start_of_current_day + dt.timedelta(hours=self.time_of_day_bounds[0])) and #<< AND
             time_now < (time_start_of_current_day + dt.timedelta(hours=self.time_of_day_bounds[1])) ):
            return True
        return False

    def check_alarm_bounds_on_different_dates(self, time_now):
        time_start_of_current_day = dt.datetime.combine(time_now.date(), dt.datetime.min.time())
        if ( time_now >= (time_start_of_current_day + dt.timedelta(hours=self.time_of_day_bounds[0])) or #<< OR
             time_now < (time_start_of_current_day + dt.timedelta(hours=self.time_of_day_bounds[1])) ):
            return True
        return False

    def is_alarm_live(self, time_current, garage_door_state_current):
        if self.garage_door_state_alarm_event == garage_door_state_current:
            if self.time_of_day_bounds[1] <= self.time_of_day_bounds[0]:
                # alarm range crosses midnight boundary
                # refactor this ugly, redundant code!
                # http://codereview.stackexchange.com/questions/153304/handling-date-rollover-in-same-function
                return self.check_alarm_bounds_on_different_dates(time_current)
            else:
                return self.check_alarm_bounds_on_same_date(time_current)

    def reset_alarm(self):
        if self.verbose:
            log('reset %s' % self.alarm_name)
        self.datetime_last_alarm_outright_start = None
        self.datetime_last_alarm_counter_start = None
        self.datetime_last_alarm_sms_triggered = None

    def check_alarm(self, time_current, garage_door_state_current):
        if self.is_alarm_live(time_current, garage_door_state_current):
            if not self.datetime_last_alarm_outright_start:
                self.datetime_last_alarm_outright_start = time_current
                if self.verbose:
                    log('start %s cycle' % self.alarm_name)
            if not self.datetime_last_alarm_counter_start:
                self.datetime_last_alarm_counter_start = time_current
                if self.verbose:
                    log('start %s counter' % self.alarm_name)
            tdelta_seconds = (time_current - self.datetime_last_alarm_counter_start).total_seconds()
            minutes_since_start_alarm_cycle = int( (time_current - self.datetime_last_alarm_outright_start).total_seconds() / 60 )
            if self.verbose:
                log( '%s counter at: %i seconds (total time in alarm state: %i minutes)' % ( self.alarm_name, tdelta_seconds, minutes_since_start_alarm_cycle) )
            if tdelta_seconds >= self.alarm_event_duration_seconds and ( tdelta_seconds >= self.min_seconds_between_sms or not self.datetime_last_alarm_sms_triggered ):
                alarm_msg = 'ALARM - %s - open for %i minutes (total %i minutes as of %s)' % ( self.alarm_name, int(tdelta_seconds/60), minutes_since_start_alarm_cycle, dt.datetime.now().replace(microsecond=0) )
                self.trigger_alarm(alarm_msg)
                self.datetime_last_alarm_sms_triggered = time_current
                self.datetime_last_alarm_counter_start = None
                return alarm_msg
        else:
            self.reset_alarm()
        return

    def trigger_alarm(self, alarm_msg):
        if self.debug_mode:
            log('if not debug_mode, would send alarm sms now. alarm_msg = "%s"' % alarm_msg)
        else:
            log(alarm_msg)
            log('now sending sms to report alarm')
            self.sms_butler.send_sms(alarm_msg, self.phone_to_sms_on_alarm)


class GPIOEventHandler():
    def __init__(self, polling_interval_seconds = 3, debounce_num_consecutive_readings_for_state_change = 3, debug_mode=False, verbose=True):
        log("GPIO pigarage starting")
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(CHANNEL_GARAGE_DOOR_STATE, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

        self.polling_interval_seconds = polling_interval_seconds
        self.debounce_num_consecutive_readings_for_state_change = debounce_num_consecutive_readings_for_state_change
        self.debug_mode = debug_mode
        self.verbose = verbose

        self.time_current = dt.datetime.now()
        self.time_last_reading = self.time_current
        self.garage_door_state_current = GPIO.input(CHANNEL_GARAGE_DOOR_STATE)

        # initialize to current state, otherwise will not process first state change
        init_state = {'timestamp':self.time_current,'door_state':self.garage_door_state_current}
        new_state_container = [init_state]*self.debounce_num_consecutive_readings_for_state_change
        old_state_container = [init_state]*self.debounce_num_consecutive_readings_for_state_change
        self.garage_door_state_history = new_state_container + old_state_container

    def take_a_state_reading(self):
        # bump out the last entry, and insert current entry at beginning
        self.time_last_reading = dt.datetime.now()
        self.garage_door_state_current = GPIO.input(CHANNEL_GARAGE_DOOR_STATE)
        self.garage_door_state_history.pop()
        self.garage_door_state_history.insert(0, {'timestamp':self.time_current,'door_state':self.garage_door_state_current})

    def is_it_a_new_day(self):
        if dt.datetime.date(self.time_current) != dt.datetime.date(self.time_last_reading):
            return True
        else:
            return False

    def is_it_time_for_a_new_reading(self):
        self.time_current = dt.datetime.now()
        if (self.time_current - self.time_last_reading).total_seconds() > self.polling_interval_seconds:
            return True
        else:
            return False

    def has_garage_door_state_changed(self):
        # checking that it changed, and persisted for debounce_num_consecutive_readings_for_state_change (avoid "flipped" states due to noisy signal)

        # first half is new readings; second half old ones
        new_state_container = self.garage_door_state_history[0:self.debounce_num_consecutive_readings_for_state_change]
        old_state_container = self.garage_door_state_history[self.debounce_num_consecutive_readings_for_state_change: ]
        if self.verbose:
            log( '%s|%s' % ([x['door_state'] for x in new_state_container],[x['door_state'] for x in old_state_container]) )

        # check that:
        # 1) reading has changed (oldest reading not same as newest)
        # 2) state reading were persistent (i.e. same readings in debound period)
        if (self.garage_door_state_history[0]['door_state'] != self.garage_door_state_history[-1]['door_state']
            and all(new_state_container[0]['door_state'] == reading['door_state'] for reading in new_state_container)
            and all(old_state_container[0]['door_state'] == reading['door_state'] for reading in old_state_container)
            ):
            if self.verbose:
                log('CHANGE: from %i to %i' % (old_state_container[0]['door_state'],new_state_container[0]['door_state']))
            return True
        else:
            if self.verbose:
                log('NO CHANGE: %i' % (old_state_container[0]['door_state']))
            return False

    def process_garage_door_state(self):
        garage_door_event = None
        self.take_a_state_reading()
        if self.has_garage_door_state_changed():
            # door state has changed - report the event
            if self.garage_door_state_current == GARAGE_DOOR_STATE_GPIO_MAP['DOOROPEN']:
                garage_door_event = (self.time_current.replace(microsecond=0), self.garage_door_state_current, 'OPEN')
                log('door was opened at %s' % self.time_current.replace(microsecond=0))
            else:
                garage_door_event = (self.time_current.replace(microsecond=0), self.garage_door_state_current, 'CLOSE')
                log('door was closed at %s' % self.time_current.replace(microsecond=0))
        else:
            if self.verbose:
                log('nothing to log at %s and state %s' % (self.time_current.replace(microsecond=0), self.garage_door_state_current))

        return garage_door_event


def log(message):
    print('%s | %s' % ( dt.datetime.now().replace(microsecond=0), message ))


def main(debug_mode=False):
    verbose = False

    if debug_mode:
        log('debug_mode enabled. Will not log to database.')
    else:
        dbName = 'pigarage.db'
        mgr = pidb.sqlManager(dbName)
        table_name_garage_door = 'GarageDoorState'
        table_name_system_event = 'SystemEventLog'
        log('connection to %s database established' % dbName)
        mgr.log_system_event_to_database('request PiGarage')

    user_phone_number = '+15551234567'
    if debug_mode:
        log('debug_mode enabled. Will not send SMS.')
        sms_butler = None
    else:
        sms_butler = pisms.SMS_Butler(database_sms_log_mgr=mgr)
        min_seconds_between_sms = 60
        log('connection to sms handler established')

    gpiomonitor = GPIOEventHandler(debug_mode=debug_mode,verbose=verbose)
    log('GPIO pigarage initialized... running')

    # define alarms
#TODO - not flexible; basically hardcoding time range and event states
    after_hours_door_alarm = smsAlarmHandler( 'night alarm', sms_butler, user_phone_number, GARAGE_DOOR_STATE_GPIO_MAP['DOOROPEN'], 2, (20,10), 30, debug_mode=debug_mode, verbose=verbose )
    if not debug_mode:
        mgr.log_system_event_to_database('alarm set', system_event_value='night alarm')

    daytime_door_alarm = smsAlarmHandler( 'day alarm', sms_butler, user_phone_number, GARAGE_DOOR_STATE_GPIO_MAP['DOOROPEN'], 30, (10,20), 120, debug_mode=debug_mode, verbose=verbose )
    if not debug_mode:
        mgr.log_system_event_to_database('alarm set', system_event_value='day alarm')

    # specify which alarms to actually monitor (enable)
    active_alarms = [after_hours_door_alarm, daytime_door_alarm]

    if not debug_mode:
        response_text = 'PiGarage is online: %s' % dt.datetime.now().replace(microsecond=0)
        sms_butler.send_sms(response_text, user_phone_number)
        mgr.log_system_event_to_database('start PiGarage', system_event_value='success')

    while True:
        if gpiomonitor.is_it_time_for_a_new_reading():
            if gpiomonitor.is_it_a_new_day():
                if debug_mode:
                    log('if not in debug_mode, would trigger daily sms log now')
                else:
                    log('triggering sms daily log')
                    daily_log_text = mgr.generate_daily_system_status_log()
                    sms_butler.send_sms(daily_log_text, user_phone_number)

            for alarm in active_alarms:
                alarm_msg = alarm.check_alarm(gpiomonitor.time_current, gpiomonitor.garage_door_state_current)
                if alarm_msg:
                    if debug_mode:
                        log('alarm_msg: %s' % str(alarm_msg))
                    else:
                        mgr.log_system_event_to_database('alarm triggered', system_event_value=alarm_msg)

            garage_door_event = gpiomonitor.process_garage_door_state()
            if garage_door_event is not None:
                if debug_mode:
                    log('garage_door_event: "%s"' % str(garage_door_event))
                else:
                    if not mgr.bulk_insert_records(table_name_garage_door, [garage_door_event]):
                        # failed to insert the records
                        err_msg = 'ERROR: failed to insert %i records to %s (%s)' % ( len([garage_door_event]), table_name_garage_door, dt.datetime.now().replace(microsecond=0) )
                        log(err_msg)
                        mgr.log_system_event_to_database('fail db', system_event_value=err_msg)
                        smsdelta = gpiomonitor.time_current - sms_butler.datetime_last_sms_attempt
                        if smsdelta.total_seconds() > min_seconds_between_sms:
                            log('sending sms to report error')
                            sms_butler.send_sms(err_msg, user_phone_number)

        # small delay to limit CPU tax
        time.sleep(0.1)


if __name__ == '__main__':
    debug_mode=False
    #debug_mode=True # no database logging; no sms texts
    main(debug_mode)
