# import datetime
import os
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Any, Tuple, Optional, List, Union

# Files and Folders
HOME = os.path.expanduser('~')
WORK = os.path.join(HOME, 'OneDrive - UW', 'Work')
DB_FILE = 'time_cards.db'


@dataclass(slots=True)
class TimeCardEntry:
    work_date: date = date.today()
    line_item: int = 0
    workorder: str = ''
    phase: str = ''
    hours: float = 0
    description: str = ''
    action: str = ''
    time_code: str = 'R'

    def __getitem__(self, key: str) -> Any:
        return self.__getattribute__(key)

    def __setitem__(self, key: str, value: Any) -> None:
        self.__setattr__(key, value)

    def values(self) -> Tuple[Union[date, int, str]]:
        return (self.work_date,
                self.line_item,
                self.workorder,
                self.phase,
                str(self.hours),
                self.description,
                self.action,
                self.time_code)


class TimeCard:
    def __init__(self, date: Optional[date] = None, entries: List[TimeCardEntry] = []) -> None:
        self.date = date
        self.entries = entries

    def __bool__(self):
        return bool(self.entries) and bool(self.date)

    def __iter__(self):
        return iter(self.entries)

    def __len__(self):
        return len(self.entries)

    @property
    def hours(self) -> float:
        return sum(entry['hours'] for entry in self.entries)


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

    def __init__(self, filename: str = os.path.join(WORK, DB_FILE)) -> None:
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

    def get_record(self, work_date: date, item: int) -> Optional[TimeCardEntry]:
        sql = 'SELECT * FROM records WHERE work_date=? AND line_item=?'
        with self._connect() as db:
            c = db.execute(sql, (work_date, item))
            record = c.fetchone()
            if record:
                return TimeCardEntry(*record)
            else:
                return None

    def update_record(self, record: Union[TimeCardEntry, dict]) -> None:
        if isinstance(record, (dict)):
            record = TimeCardEntry(**record)
        sql = """
                UPDATE records SET workorder=?, phase=?, hours=?, description=?, action=?, time_code=?
                WHERE work_date=? AND line_item=?
                """
        values = (record.workorder, record.phase, record.hours,
                  record.description, record.action, record.time_code,
                  record.work_date, record.line_item)
        with self._connect() as db:
            db.execute(sql, values)

    def add_record(self, record: Union[TimeCardEntry, dict]) -> None:
        if isinstance(record, (dict)):
            record = TimeCardEntry(**record)
        if not self.get_record(record.work_date, record.line_item):
            with self._connect() as db:
                sql = """
                INSERT INTO records(work_date, line_item, workorder, phase, hours, description, action, time_code)
                VALUES(?,?,?,?,?,?,?,?)
                """
                values = (record.work_date, record.line_item, record.workorder,
                          record.phase, record.hours, record.description,
                          record.action, record.time_code)
                db.execute(sql, values)

    def _delete_record(self, work_date: date, item: int) -> None:
        sql = 'DELETE FROM records WHERE work_date=? AND line_item=?'
        with self._connect() as db:
            db.execute(sql, (work_date, item))

    def delete_record(self, work_date: date, item: int) -> None:
        """
        Remove record from database
        Line item numbers will be adjusted
        """
        self._delete_record(work_date, item)
        tc = self.get_timecard(work_date)
        for e in tc:
            self._delete_record(e['work_date'], e['line_item'])
        for i, e in enumerate(tc):
            e['line_item'] = i
            self.add_record(e)

    def get_timecard(self, work_date: date) -> TimeCard:
        """
        Reruns a TimeCard object for the given date and
        sets current_view
        """
        sql = 'SELECT * FROM records WHERE work_date=?'
        with self._connect() as db:
            c = db.execute(sql, [work_date])
            tc = [TimeCardEntry(*record) for record in c.fetchall()]
            c.close()
            self.current_view = TimeCard(work_date, tc)
            return self.current_view

    def find_records(self, text: str, date1: date = date(2019, 1, 1), date2: date = date.today()) -> List[TimeCardEntry]:
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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.dbfilename, detect_types=(sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES))


if __name__ == '__main__':
    today = date.today()
    db = TimeCardDatabase()
    tc = TimeCardEntry(today, 0, '000020', '039', 8,
                       'LEAD WORK', 'OVERHEAD', 'R')
