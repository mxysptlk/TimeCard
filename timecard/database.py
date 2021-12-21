# import datetime
import os
import sqlite3
import datetime


# Files and Folders
HOME = os.path.expanduser('~')
WORK = os.path.join(HOME, 'Dropbox', 'Work')
DB_FILE = 'time_cards.db'


class TimeCardEntry(dict):
    """
    An ordered dict like object for time card data.
    Prevents setting invalid keys.
    """
    FIELDS = ('work_date', 'line_item', 'workorder', 'phase',
              'hours', 'description', 'action', 'time_code')

    def __init__(self, work_date='', line_item='',
                 workorder='', phase='', hours='',
                 description='', action='', time_code='R'):
        super().__init__(work_date=work_date, line_item=line_item,
                         workorder=workorder, phase=phase, hours=hours,
                         description=description,
                         action=action, time_code=time_code)

    def __setitem__(self, key, value):
        if key in self.FIELDS:
            super().__setitem__(key, value)

    def values(self):
        return (self['work_date'],
                self['line_item'],
                self['workorder'],
                self['phase'],
                str(self['hours']),
                self['description'],
                self['action'],
                self['time_code'])


class TimeCard:
    def __init__(self, date=None, entries=[]):
        self.date = date
        self.entries = entries

    def __bool__(self):
        return bool(self.entries) and bool(self.date)

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)

    @property
    def hours(self):
        return sum([entry['hours'] for entry in self.entries])


class TimeCardDatabase:
    """
    A database object for storing Time Card information, built
    around sqlite3.
    Data fields are:
        work_date = datetime.date object
        line_item = int
        workorder = str (6 digit number with zro padding, ie. '000001')
        phase = str (3 digit number with zero padding, ie '001')
        hours = float
        description = str
        action = str (one of [WORK COMPLETE, ACTIVE/ONGOING, INITIAL RESPOND, OVERHEAD])
        time_code = str (one of [R, CP, OT, A, S, PH, HOLIDAY])
    """

    def __init__(self, filename=os.path.join(WORK, DB_FILE)):
        self.dbfilename = filename
        self.current_view = TimeCard()
        self.active_record = None
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS records
                ( work_date DATE,
                line_item INTEGER,
                workorder TEXT,
                phase TEXT,
                hours REAL,
                description TEXT,
                action TEXT,
                time_code TEXT )
                """
            )

    def get_record(self, date, item):
        sql = 'SELECT * FROM records WHERE work_date=? AND line_item=?'
        with self._connect() as db:
            c = db.execute(sql, (date, item))
            record = c.fetchone()
            if record:
                return TimeCardEntry(*record)
            else:
                return None

    def update_record(self, record):
        if not isinstance(record, (TimeCardEntry, dict)):
            record = TimeCardEntry(*record)
        sql = """
                UPDATE records SET workorder=?, phase=?, hours=?, description=?, action=?, time_code=?
                WHERE work_date=? AND line_item=?
                """
        values = (record['workorder'], record['phase'], record['hours'],
                  record['description'], record['action'], record['time_code'],
                  record['work_date'], record['line_item'])
        with self._connect() as db:
            db.execute(sql, values)

    def add_record(self, record):
        if not isinstance(record, (TimeCardEntry, dict)):
            record = TimeCardEntry(*record)
        sql = """
                INSERT INTO records(work_date, line_item, workorder, phase, hours, description, action, time_code)
                VALUES(?,?,?,?,?,?,?,?)
                """
        values = (record['work_date'], record['line_item'], record['workorder'],
                  record['phase'], record['hours'], record['description'],
                  record['action'], record['time_code'])
        if not self.get_record(record['work_date'], record['line_item']):
            with self._connect() as db:
                db.execute(sql, values)

    def _delete_record(self, date, item):
        sql = 'DELETE FROM records WHERE work_date=? AND line_item=?'
        with self._connect() as db:
            db.execute(sql, (date, item))

    def delete_record(self, date, item):
        """
        Remove record from database
        Line item numbers will be adjusted
        """
        self._delete_record(date, item)
        tc = self.get_timecard(date)
        for e in tc:
            self._delete_record(e['work_date'], e['line_item'])
        for i, e in enumerate(tc):
            e['line_item'] = i
            self.add_record(e)

    def get_timecard(self, date):
        """
        Reruns a TimeCard object for the given date and
        sets current_view
        """
        sql = 'SELECT * FROM records WHERE work_date=?'
        with self._connect() as db:
            c = db.execute(sql, [date])
            tc = [TimeCardEntry(*record) for record in c.fetchall()]
            c.close()
            self.current_view = TimeCard(date, tc)
            return self.current_view

    def find_records(self, text, date1=datetime.date(2019, 1, 1), date2=datetime.date.today()):
        """
        Returns a list of TimeEntry objects who's description
        matches 'text' and work_dates are betewwn 'date1' and 'date2'
        """
        sql = """
        SELECT * FROM records WHERE description LIKE ?
        AND (work_date BETWEEN ? AND ?)
        """
        text = f'%{text}%'
        with self._connect() as db:
            c = db.execute(sql, [text, date1, date2])
            r = [TimeCardEntry(*record) for record in c.fetchall()]
            c.close()
            return r

    def _connect(self):
        return sqlite3.connect(self.dbfilename, detect_types=(sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES))


if __name__ == '__main__':
    today = datetime.date.today()
    db = TimeCardDatabase()
    tc = TimeCardEntry(today, 0, '000020', '039', 8,
                       'LEAD WORK', 'OVERHEAD', 'R')
