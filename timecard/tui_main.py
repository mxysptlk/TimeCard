#!/usr/bin/env python3
import datetime
# import json
import os
import sys
from collections import defaultdict
from configparser import ConfigParser
from typing import Callable, NoReturn
from threading import Thread

import keyring
from asciimatics.event import KeyboardEvent
from asciimatics.exceptions import (NextScene, ResizeScreenError,
                                    StopApplication)
from asciimatics.scene import Scene
from asciimatics.widgets import (THEMES, Button, DatePicker, Divider,
                                 DropdownList, FileBrowser, Frame, Label,
                                 Layout, MultiColumnListBox, PopUpDialog,
                                 Screen, Text, TextBox, Widget, _enforce_width,
                                 )

from .aim import AimSession
from .database import TimeCardDatabase


# Monkey patch to make None support term default
def __refresh(self):
    """
    Refresh the screen.
    """
    # Scroll the screen now - we've already sorted the double-buffer to reflect this change.
    if self._last_start_line != self._start_line:
        self._scroll(self._start_line - self._last_start_line)
        self._last_start_line = self._start_line

    # Now draw any deltas to the scrolled screen.  Note that CJK character sets sometimes
    # use double-width characters, so don't try to draw the next 2nd char (of 0 width).
    for y, x in self._buffer.deltas(0, self.height):
        new_cell = self._buffer.get(x, y)
        # --- begin patch: If bg is None force terminal reset
        if new_cell[3] is None or new_cell[1] is None:
            self._attr = None
        # --- end patch
        if new_cell[4] > 0:
            self._change_colours(new_cell[1], new_cell[2], new_cell[3])
            self._print_at(new_cell[0], x, y, new_cell[4])

    # Resynch for next refresh.
    self._buffer.sync()


Screen.refresh = __refresh
# End Monkey patch
PASTE_BUFFER = {}
CONFIG = ConfigParser()
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.timetrack')
# Build custom theme with transparency support
MY_THEME = defaultdict(lambda: (None, 1, None))
MY_THEME['invalid'] = (None, 1, 1)
MY_THEME['label'] = (2, 1, None)
MY_THEME['control'] = (3, 1, None)
MY_THEME['focus_control'] = (3, 1, None)
MY_THEME['selected_focus_control'] = (3, 1, None)
MY_THEME['selected_focus_field'] = (3, 1, None)
MY_THEME['focus_button'] = (3, 1, None)
MY_THEME['focus_edit_text'] = (3, 1, None)
MY_THEME['disabled'] = (8, 1, None)

THEMES['fancy'] = MY_THEME
THEMES['bright']['invalid'] = (0, 1, 1)

THEME_DICT = {k: v + 1 for v, k in enumerate(THEMES.keys())}

ACTIONS = {'WORK COMPLETE': 1,
           'ACTIVE/ONGOING': 2,
           'INITIAL RESPOND': 3,
           'OVERHEAD': 4}
TIME_CODES = {'R': 1, 'CP': 2, 'OT': 3, 'A': 4, 'S': 5,
              'PH': 6, 'CT': 7, 'ASG': 8, 'HOLIDAY': 9, 'HOMEWORK': 10}
# DEFAULT_ENTRIES = [dict(workorder='000051',
#                         phase='039',
#                         hours=0.5,
#                         action='OVERHEAD',
#                         description='MORNING HUDDLE/STRETCH AND FLEX',
#                         time_code='R'),
DEFAULT_ENTRIES = [dict(workorder='000032',
                        phase='039',
                        hours=0.5,
                        action='OVERHEAD',
                        description='BREAK',
                        time_code='R'),
                   dict(workorder='000020',
                        phase='039',
                        hours=3.5,
                        action='OVERHEAD',
                        description='LEAD WORK',
                        time_code='R')]

# TUI Widgets


class StatusLine(Text):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled = True

    def update(self, frame_no):
        super().update(frame_no)

        # Render visible portion of the text.
        (colour, attr, bg) = self._pick_colours("edit_text")
        text = self._value[self._start_column:]
        text = _enforce_width(
            text, self.width, self._frame.canvas.unicode_aware)
        text += " " * (self.width - self.string_len(text))

        self._frame.screen.print_at(
            text,
            self._x + self._offset,
            self._y,
            colour, attr, bg)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._set_and_check_value(new_value, reset=True)
        if self._frame:
            self.update(self._frame)
            self._frame.screen.refresh()


class EntryList(MultiColumnListBox):
    def process_event(self, event):

        if isinstance(event, KeyboardEvent):
            if event.key_code in (Screen.KEY_DELETE, ord('d'), ord('D')):
                self._frame.on_remove()
                event = None
            elif event.key_code in (ord('+'), ord('a'), ord('A')):
                self._frame.on_add()
                event = None
        return super().process_event(event)


class BoxedButton(Button):
    def __init__(self, text, on_click, min_width=10):
        super().__init__(text, on_click, add_box=False)
        self._min_width = min_width

    def required_height(self, offset, width):
        if self._frame.canvas.unicode_aware:
            return 3
        else:
            return 1

    def set_layout(self, x, y, offset, w, h):
        super().set_layout(x, y, offset, w, h)
        if self._frame.canvas.unicode_aware:
            self._text = self._text.strip()
            if len(self._text) < self._min_width:
                self._text = self._text.center(self._min_width)

    def update(self, frame_no):
        if self._frame.canvas.unicode_aware:
            tl = u"┌"
            tr = u"┐"
            bl = u"└"
            br = u"┘"
            horiz = u"─"
            vert = u"│"

            (colour, attr, bg) = self._pick_colours("button")
            text_width = len(self._text)

            top = tl + (horiz * text_width) + tr
            mid = vert + self._text + vert
            bottom = bl + (horiz * text_width) + br

            self._frame.canvas.print_at(
                top.center(self._w),
                self._x + self._offset,
                self._y,
                colour, attr, bg)

            self._frame.canvas.print_at(
                mid.center(self._w),
                self._x + self._offset,
                self._y + 1,
                colour, attr, bg)

            self._frame.canvas.print_at(
                bottom.center(self._w),
                self._x + self._offset,
                self._y + 2,
                colour, attr, bg)
        else:
            self._add_box = True
            super().update(frame_no)


class TimeCardView(Frame):
    def __init__(self, screen: Screen, db: TimeCardDatabase) -> None:
        super().__init__(screen, screen.height, screen.width,
                         title="Time Card",
                         can_scroll=False,
                         hover_focus=True,
                         reduce_cpu=True,
                         on_load=self._reload_list)
        self.set_theme(CONFIG['DEFAULT']['theme'])
        self._db = db

        self._entries = EntryList(Widget.FILL_FRAME,
                                  ['>10', '>6', '>6', 0, 10],
                                  [],
                                  name='time_entries',
                                  titles=['WORKORDER', 'PHASE',
                                          'HRS', 'DESCRIPTION', 'ACTION'],
                                  on_select=self.on_edit)
        self._cache = None
        self._total = Text('Total: ', 'total')
        self._total.disabled = True

        self._status_line = StatusLine()

        self.data['work_date'] = datetime.date.today()

        head = Layout([100])
        main = Layout([100], fill_frame=True)
        foot = Layout([100])
        buttons = Layout([1, 1, 1, 1, 1, 1])
        status = Layout([100])

        self.add_layout(head)
        self.add_layout(main)
        self.add_layout(foot)
        self.add_layout(buttons)
        self.add_layout(status)

        head.add_widget(Divider(draw_line=False))
        head.add_widget(DatePicker(
            'Work Date: ', name='work_date', on_change=self._reload_list))
        self.data['work_date'] = datetime.date.today()

        main.add_widget(Divider())
        main.add_widget(self._entries)

        foot.add_widget(self._total)
        foot.add_widget(Divider())

        buttons.add_widget(BoxedButton('+Overhead', self.on_add_overhead), 0)
        buttons.add_widget(BoxedButton('Submit', self.on_submit), 1)
        # buttons.add_widget(BoxedButton('Vacation', self.on_vacation), 2)
        buttons.add_widget(BoxedButton('Settings', self.on_settings), 3)
        buttons.add_widget(BoxedButton('Search', self.on_search), 4)
        buttons.add_widget(BoxedButton('Quit', self.on_quit), 5)

        status.add_widget(self._status_line)

        self.fix()

    # new_value param is required by asciimatics API
    def _reload_list(self, new_value=None):
        self.set_theme(CONFIG['DEFAULT']['theme'])
        self.save()
        self._cache = self._db.get_timecard(self.data['work_date'])
        options = [(entry.values()[2:], i)
                   for i, entry in enumerate(self._cache)]
        options.append((['+ Add'], 100))
        self._entries.options = options
        self._total.value = str(self._cache.hours)
        if self._cache.hours != 8.0:
            self._total.custom_colour = 'invalid'
        else:
            self._total.custom_colour = 'edit_text'
        self._status_line.value = ''
        self._status_line.custom_colour = 'edit_text'

    def on_add(self):
        self._db.active_record = None
        self.save()
        self.scene.add_effect(TimeEntryEdit(self.screen, self._db))

    def on_copy(self):
        global PASTE_BUFFER
        self.save()
        PASTE_BUFFER = self._db.get_record(
            self.data['work_date'], self.data['time_entries'])

    def on_paste(self):
        global PASTE_BUFFER
        self.save()
        if PASTE_BUFFER:
            r = PASTE_BUFFER
            r['work_date'] = self.data['work_date']
            r['line_item'] = len(self._cache)
            self._db.add_record(r)
            self._reload_list()

    def on_add_overhead(self):
        "Add the default entries"
        count = len(self._cache)
        for i, template in enumerate(DEFAULT_ENTRIES):
            entry = defaultdict(lambda: '',
                                work_date=self.data['work_date'],
                                line_item=(count + i),
                                **template)
            self._db.add_record(entry)
        self._db.get_timecard(self.data['work_date'])
        self._reload_list()

    def on_help(self):
        pass

    def on_edit(self):
        self.save()
        self._db.active_record = self._db.get_record(
            self.data['work_date'], self.data['time_entries'])
        self.scene.add_effect(TimeEntryEdit(self.screen, self._db))

    def on_remove(self):
        "remove selected entry from time card"
        self.save()
        self._db.delete_record(
            self.data['work_date'], self.data['time_entries'])
        self._reload_list()

    def on_search(self):
        self.save()
        raise NextScene('Search')

    def on_settings(self):
        self.scene.add_effect(SettingsView(self.screen, self._db))

    def _on_submit(self):
        "Submit time card in AiM"
        entries = [entry.values()[2:] for entry in self._cache]
        # we want to submit the overhead entries last
        entries.sort(key=lambda e: e[0], reverse=True)
        workdate = self._cache.date.strftime('%b %d, %Y')
        CONFIG.read(CONFIG_FILE)
        self._status_line.value = 'Creating webdriver...'
        with AimSession(netid=CONFIG['AIM']['NETID']) as aim:
            self._status_line.value = 'logging in...'
            aim.login()
            for msg in aim.new_timecard(CONFIG['AIM']['EMPLOYEE_ID'], workdate, entries):
                if 'error' in msg.lower():
                    self._status_line.custom_colour = 'invalid'
                self._status_line.value = msg

    def on_submit(self):
        Thread(target=self._on_submit).start()

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            # self._status_line.value = str(event.key_code)
            if event.key_code == 121 or event.key_code == 89:
                self.on_copy()
                event = None
            elif event.key_code == 112 or event.key_code == 80:
                self.on_paste()
                event = None
            elif event.key_code == 63:
                self.on_help()
                import time
                time.sleep(5)
                event = None
        super().process_event(event)

    @staticmethod
    def on_quit():
        raise StopApplication('User entered Quit')


class TimeEntryEdit(Frame):

    def __init__(self, screen, db):
        super().__init__(screen,
                         int(screen.height * 3 // 4),
                         int(screen.width * 3 // 4),
                         title='Time Entry',
                         can_scroll=False,
                         has_shadow=True,
                         is_modal=True,
                         reduce_cpu=True)
        self.set_theme(CONFIG['DEFAULT']['theme'])
        self._db = db

        self._action = DropdownList(
            [(k, v) for k, v in ACTIONS.items()],
            'Action:', 'action')
        self._time_code = DropdownList([(k, v) for k, v in TIME_CODES.items()],
                                       'Time Code:', 'time_code')
        self._id = Text()
        self._id.disabled = True
        self._id.custom_colour = 'edit_text'
        self._date = Text()
        self._date.disabled = True
        self._date.custom_colour = 'edit_text'
        self._cache = self._db.current_view

        head = Layout([1, 1, 1])
        form = Layout([100], fill_frame=True)
        buttons = Layout([1, 2, 1])

        self.add_layout(head)
        self.add_layout(form)
        self.add_layout(buttons)

        head.add_widget(self._id, 0)
        head.add_widget(self._date, 2)

        form.add_widget(Divider())
        form.add_widget(Text('Workorder:', 'workorder', validator='[0-9]{6}'))
        form.add_widget(Text('Phase:', 'phase', validator='[0-9]{3}'))
        form.add_widget(Text('Hours:', 'hours', validator=r'(\d+)|(\.\d)'))
        form.add_widget(self._action)
        form.add_widget(TextBox(Widget.FILL_FRAME,
                                'Description:', 'description',
                                as_string=True, line_wrap=True))
        form.add_widget(self._time_code)
        buttons.add_widget(BoxedButton('Done', self.on_done), 0)
        buttons.add_widget(BoxedButton('Cancel', self.on_cancel), 2)

        self.fix()

    def on_done(self):
        self.save()
        actions = {v: k for k, v in ACTIONS.items()}
        codes = {v: k for k, v in TIME_CODES.items()}
        self.data['time_code'] = codes[self.data['time_code']]
        self.data['action'] = actions[self.data['action']]
        self.data['hours'] = float(self.data['hours'])
        self.data['workorder'] = self.data['workorder'].zfill(6)
        self.data['phase'] = self.data['phase'].zfill(3)

        if not self._db.active_record:
            self._db.add_record(self.data)
        else:
            self._db.update_record(self.data)
        self.data = {}
        self.save()
        self.scene.remove_effect(self)
        raise NextScene('Main')

    def reset(self):
        super().reset()
        if self._db.active_record:
            data = self._db.active_record
            data['hours'] = str(data['hours'])
            # Dirty Hack --
            # This is neede to prevent a crash on resize
            if isinstance(data['action'], str):
                data['action'] = ACTIONS[data['action']]
            if isinstance(data['time_code'], str):
                data['time_code'] = TIME_CODES[data['time_code']]
            # End hack
            self.data = data
        else:
            self.data = dict(work_date=self._cache.date,
                             line_item=len(self._cache),
                             workorder='',
                             phase='',
                             hours='',
                             description='',
                             action=1,
                             time_code=1)
        self._id.value = f'Item: {str(self.data["line_item"])}'
        self._date.value = f'Date: {self.data["work_date"].strftime("%d/%b/%Y")}'

    def on_cancel(self):
        self.scene.remove_effect(self)
        raise NextScene('Main')

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == Screen.KEY_ESCAPE:
                self.on_cancel()
                event = None
        super().process_event(event)


class FileBrowsePopup(Frame):
    def __init__(self, screen, target):
        super().__init__(screen,
                         int(screen.height * 2 // 3),
                         int(screen.width * 2 // 3),
                         title='Browse File',
                         can_scroll=False,
                         has_shadow=True,
                         reduce_cpu=True)
        self._target = target
        self.set_theme(CONFIG['DEFAULT']['theme'])
        browser = Layout([100], fill_frame=True)
        buttons = Layout([1, 2, 1])

        self.add_layout(browser)
        self.add_layout(buttons)

        if self._target.value:
            root = os.path.split(self._target.value)[0]
        else:
            root = os.path.expanduser('~')
        browser.add_widget(FileBrowser(Widget.FILL_FRAME, root, 'db_file'))
        buttons.add_widget(BoxedButton('Cancel', self.on_cancel), 0)
        buttons.add_widget(BoxedButton('Select', self.on_select), 2)

        self.fix()

    def on_select(self):
        self.save()
        self._target.value = self.data['db_file']
        self.scene.remove_effect(self)

    def on_cancel(self):
        self.scene.remove_effect(self)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == Screen.KEY_ESCAPE:
                self.on_cancel()
                event = None
        super().process_event(event)

    def clone(self, screen, scene):
        self.scene.remove_effect(self)
        scene.add_effect(FileBrowsePopup(screen, self._target))


class SearchView(Frame):
    def __init__(self, screen, db):
        super().__init__(screen, screen.height, screen.width,
                         title="Search",
                         can_scroll=True,
                         reduce_cpu=True,
                         on_load=self._reload_list)
        self._db = db
        self._records_cache = []
        self.set_theme(CONFIG['DEFAULT']['theme'])
        self._results = MultiColumnListBox(Widget.FILL_FRAME,
                                           ['>5', 10, '>10', '>6', 0],
                                           [],
                                           ['', 'WORK DATE', 'WORKORDER',
                                               'PHASE', 'DESCRIPTION'],
                                           name='result')

        self._filter = Text('Filter:', 'filter', self._reload_list)
        self._total = Text('Total')
        self._total.disabled = True
        self._total.custom_colour = 'edit_text'

        dates = Layout([1, 1, 1, 1])
        search = Layout([100])
        results = Layout([100], fill_frame=True)
        total = Layout([100])
        buttons = Layout([100])

        self.data['date1'] = datetime.date(2019, 1, 1)
        self.data['date2'] = datetime.date.today()
        self.data['filter'] = ''

        self.add_layout(dates)
        self.add_layout(search)
        self.add_layout(results)
        self.add_layout(total)
        self.add_layout(buttons)

        dates.add_widget(Label('Date range:'), 0)
        dates.add_widget(DatePicker(
            name='date1', on_change=self._reload_list), 1)
        dates.add_widget(Label('to:'), 2)
        dates.add_widget(DatePicker(
            name='date2', on_change=self._reload_list), 3)
        search.add_widget(Text('Filter:', 'filter', self._reload_list))
        results.add_widget(self._results)
        total.add_widget(self._total)
        total.add_widget(Divider())
        buttons.add_widget(BoxedButton('Done', self.on_done))

        self.fix()

    def _reload_list(self):
        self.save()
        records = self._db.find_records(
            self.data['filter'], self.data['date1'], self.data['date2'])
        options = []
        for i, entry in enumerate(records):
            e = [str(i + 1), str(entry['work_date']),
                 entry['workorder'], entry['phase'], entry['description']]
            options.append((e, i + 1))
        self._results.options = options
        self._total.value = str(len(options))
        self._records_cache = records

    def on_copy(self):
        global PASTE_BUFFER
        self.save()
        PASTE_BUFFER = self._records_cache[self.data['result'] - 1]

    def on_done(self):
        raise NextScene('Main')

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == 121:
                self.on_copy()
                event = None
        super().process_event(event)


class SettingsView(Frame):
    def __init__(self, screen, db):
        super().__init__(screen,
                         int(screen.height * 3 // 4),
                         int(screen.width * 3 // 4),
                         title='Settings',
                         on_load=self._load_cfg,
                         can_scroll=False,
                         has_shadow=True,
                         is_modal=True,
                         reduce_cpu=True)
        self.set_theme(CONFIG['DEFAULT']['theme'])
        self._db = db
        form = Layout([75, 25], fill_frame=True)
        buttons = Layout([1, 2, 1])
        self._eid = Text('Employee ID:', 'id')
        self._netid = Text('NetID:', 'netid')
        self._pwd = Text('Password:', 'pwd1', hide_char='*')
        self._pwd.disabled = True
        self._pwd2 = Text('Confirm:', 'pwd2',
                          hide_char='*',
                          validator=lambda _: self._pwd.value == self._pwd2.value)
        self._pwd2.disabled = True
        self._edit_pwd = False
        self._dbfile = Text('Database:', 'db_file')
        self._dbfile.disabled = True
        self._chpass = BoxedButton('Change', self.on_chpass)
        self._theme_select = DropdownList(
            [(k, v) for k, v in THEME_DICT.items()], 'Theme:', 'theme', self._ch_theme)

        self.add_layout(form)
        self.add_layout(buttons)

        form.add_widget(self._eid)
        form.add_widget(self._netid)
        form.add_widget(self._pwd)
        form.add_widget(self._pwd2)
        form.add_widget(Divider(draw_line=False))
        form.add_widget(Divider(draw_line=False))
        form.add_widget(self._dbfile)
        form.add_widget(Divider(draw_line=False), 1)
        form.add_widget(self._chpass, 1)
        form.add_widget(Divider(draw_line=False), 1)
        form.add_widget(BoxedButton('Change', self.on_chdb), 1)
        form.add_widget(Divider(draw_line=False))
        form.add_widget(self._theme_select)

        buttons.add_widget(BoxedButton('Cancel', self.on_cancel), 0)
        buttons.add_widget(BoxedButton('Save', self.on_save), 2)

        self.fix()

    def _load_cfg(self):
        CONFIG.read(CONFIG_FILE)
        self._netid.value = CONFIG['AIM']['NETID']
        self._eid.value = CONFIG['AIM']['EMPLOYEE_ID']
        self._dbfile.value = CONFIG['DEFAULT']['db_file']
        self._pwd.value = keyring.get_password('aim', CONFIG['AIM']['NETID'])
        self._theme_select.value = THEME_DICT[CONFIG['DEFAULT']['theme']]

    def _ch_theme(self):
        themes = {v: k for k, v in THEME_DICT.items()}
        self.set_theme(themes[self._theme_select.value])

    def on_chdb(self):
        self.save()
        self.scene.add_effect(FileBrowsePopup(self.screen, self._dbfile))

    def on_chpass(self):
        self._edit_pwd = True
        self._pwd.disabled = False
        self._pwd.focus()
        self._pwd2.disabled = False
        self._chpass.disabled = True

    def on_save(self):
        self.save()
        themes = {v: k for k, v in THEME_DICT.items()}
        if self._edit_pwd and self.data['pwd1'] != self.data['pwd2']:
            self.scene.add_effect(PopUpDialog(
                self.screen, 'Passwords do not match!', ['OK']))
        else:
            CONFIG['AIM']['NETID'] = self.data['netid']
            CONFIG['AIM']['EMPLOYEE_ID'] = self.data['id']
            CONFIG['DEFAULT']['db_file'] = self.data['db_file']
            CONFIG['DEFAULT']['theme'] = themes[self.data['theme']]
            with open(CONFIG_FILE, 'w') as f:
                CONFIG.write(f)
            if self._edit_pwd:
                keyring.set_password(
                    'aim', self.data['netid'], self.data['pwd1'])
            self.scene.remove_effect(self)
            self._db.dbfilename = self.data['db_file']
            raise NextScene('Main')
            # if self._db.dbfilename != self.data['db_file']:
            #     self._db.dbfilename = self.data['db_file']
            #     raise NextScene('Main')
            # else:
            #     self._parent.set_theme(CONFIG['DEFAULT']['theme'])

    def on_cancel(self):
        self.scene.remove_effect(self)

    def process_event(self, event):
        if isinstance(event, KeyboardEvent):
            if event.key_code == Screen.KEY_ESCAPE:
                self.on_cancel()
                event = None

        super().process_event(event)

    def refresh(self):
        self.save()
        self._dbfile.value = self.data['db_file']

    def clone(self, screen, scene):
        scene.add_effect(SettingsView(screen))


def init():
    CONFIG['DEFAULT']['db_file'] = os.path.join(
        os.path.expanduser('~'), 'Documents', 'time_cards.db')
    CONFIG['DEFAULT']['theme'] = 'bright'
    CONFIG['AIM'] = {}
    CONFIG['AIM']['EMPLOYEE_ID'] = ''
    CONFIG['AIM']['NETID'] = ''
    with open(CONFIG_FILE, 'w') as f:
        CONFIG.write(f)


def wrapper(func: Callable[[Screen, Scene], NoReturn]) -> Callable:
    """
    asciimatics wrapper:

    Wrapps a function in boilerplate code needed to act as
    an asciimatics main loop.
    """
    def wrapped(*args):
        last_scene = None
        while True:
            try:
                Screen.wrapper(func, catch_interrupt=False,
                               arguments=(last_scene, *args))
                sys.exit(0)
            except ResizeScreenError as e:
                last_scene = e.scene

    return wrapped


@wrapper
def main(screen: Screen, scene: Scene) -> NoReturn:
    if os.path.exists(CONFIG_FILE):
        CONFIG.read(CONFIG_FILE)
    else:
        init()
    db = TimeCardDatabase(CONFIG['DEFAULT']['db_file'])
    scenes = [Scene([TimeCardView(screen, db)], -1, name='Main'),
              Scene([SearchView(screen, db)], -1, name='Search')]
    screen.play(scenes, stop_on_resize=True, start_scene=scene)


if __name__ == '__main__':
    main()
