#!/usr/bin/python

import sqlite3
import datetime as dt

class sqlManager():

    def __init__(self, dbName):
        self.conn = sqlite3.connect(dbName)
        self.conn.text_factory = str  #non UTF-8 (remove "u" character in front)
        self.cursor = self.conn.cursor()
        self.table_name_system_event = 'SystemEventLog'

    def bulk_insert_records(self, tableName, data):
        # data should be list of tuples
#***TODO - this query assumes table has 3 columns - generalize it ***
        sql = 'INSERT INTO %s VALUES (?, ?, ?);' % tableName
        try:
            self.cursor.executemany(sql, data)
            self.conn.commit()
            #print 'inserted %i records to %s (%s)' % ( len(data), tableName, dt.datetime.now().replace(microsecond=0) )
            return True
        except:
            #print 'ERROR: failed to insert %i records to %s (%s)' % ( len(data), tableName, dt.datetime.now().replace(microsecond=0) )
            return False

    def log_system_event_to_database(self, system_event_name, system_event_datetime=None, system_event_value=None, table_name_system_event='SystemEventLog'):
        if not system_event_datetime:
            system_event_datetime = dt.datetime.now().replace(microsecond=0)
        system_event_for_db = (system_event_datetime, system_event_name, system_event_value)
        return self.bulk_insert_records(table_name_system_event, [system_event_for_db])

    def run_query(self, sql):
        self.cursor.execute(sql)
        result = self.cursor.fetchall()
        return result

    def generate_daily_system_status_log(self, log_period_hours = 24):
        current_time = dt.datetime.now()
        daily_log_text = 'Daily Log - generated at: %s\n' % current_time.replace(microsecond=0)

        # open / close events
        sql  = "select s.statedescription, count(g.datetime) as count"
        sql += " from (select distinct statedescription from GarageDoorState) s"
        sql += " left join GarageDoorState g"
        sql += " on g.statedescription = s.statedescription"
        sql += " and datetime(g.datetime) > '"
        sql += ( current_time - dt.timedelta(hours=log_period_hours) ).strftime("%Y-%m-%d %H:%M:%S")
        sql += "'"
        sql += " group by s.statedescription"
        result = self.run_query(sql)
        for r in result:
            daily_log_text += '%s: %i\n' % (r[0], r[1])

        # system uptime
        sql  = "select max(datetime(datetime)) as 'start PiGarage'"
        sql += " from SystemEventLog"
        sql += " where event = 'start PiGarage'"
        result = self.run_query(sql)
        uptime = str(current_time - dt.datetime.strptime(str(result[0][0]),"%Y-%m-%d %H:%M:%S")).split(".")[0] # remove microseconds
        daily_log_text += 'uptime: %s\n' % uptime

        return daily_log_text

    def __del__(self):
        self.conn.close()


if __name__ == '__main__':
    print('nothing going on here')
