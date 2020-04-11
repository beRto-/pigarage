#!/usr/bin/env python

import os
import sys
import time
import datetime as dt

from twilio.rest import TwilioRestClient


class SMS_Butler():
    def __init__(self, database_sms_log_mgr=None):
        self.twilio_account_sid, self.twilio_auth_token, self.sTwilioNumber = loadTwilioCredentials('twilio.txt')
        self.TwilioClient = TwilioRestClient(self.twilio_account_sid, self.twilio_auth_token)
        self.database_sms_log_mgr = database_sms_log_mgr
        self.datetime_last_sms_attempt = None

    def send_sms(self, sMsg, sToPhoneNumber):
        self.datetime_last_sms_attempt = dt.datetime.now()
        try:
            # enforce Twilio character limit
            max_msg_length = 160
            mandatory_preamble = 'Sent from your Twilio trial account - '
            max_available_length = max_msg_length - len(mandatory_preamble)
            if len(sMsg) > max_available_length:
                sMsg = sMsg[-max_available_length:]
            sms = self.TwilioClient.sms.messages.create(body="{0}".format(sMsg),to="{0}".format(sToPhoneNumber),from_="{0}".format(self.sTwilioNumber))
            if self.database_sms_log_mgr:
                self.database_sms_log_mgr.log_system_event_to_database('send sms', system_event_value=sMsg)
            return sms
        except Exception as e:
            print("Error inside function SendSMS: %s" % e)
            return

# http://stackoverflow.com/questions/713794/catching-an-exception-while-using-a-python-with-statement
def loadTwilioCredentials(source_file):
    try:
        with open(source_file) as f:
            twilio_account_sid = f.readline().rstrip()
            twilio_auth_token  = f.readline().rstrip()
            sTwilioNumber = f.readline().rstrip()
            return twilio_account_sid, twilio_auth_token, sTwilioNumber
    except EnvironmentError: # parent of IOError, OSError *and* WindowsError where available
        print('Error - could not open file %s' % source_file)
        return

def main():
    sms_butler = SMS_Butler()
    print('setup new butler')

    user_phone_number = '+15551234567'
    response_text = 'this is a test message'
    sms_butler.send_sms(response_text, user_phone_number)
    print('message sent')


if __name__ == '__main__':
    main()
