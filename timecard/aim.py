import getpass
import os
import sys
import time

import keyring
from typing import Optional, Iterable
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# URLS
AIM_BASE = 'https://cmms.admin.washington.edu/fmax/screen/'
AIM_TRAINING = 'https://cmms-train.admin.washington.edu/fmax/screen/'
HOME_PAGE = AIM_BASE + 'WORKDESK'
AIM_TIMECARD = AIM_BASE + 'TIMECARD_VIEW'
WORKORDER_VIEW = AIM_BASE + 'WO_VIEW'
PHASE_VIEW = AIM_BASE + 'PHASE_VIEW?proposal={}&sortCode={}'
RAPID_TIMECARD_EDIT = AIM_BASE + 'RAPID_TIMECARD_EDIT'

# Element IDs
UID = 'weblogin_netid'
PWD = 'weblogin_password'
SUBMIT = 'submit_button'

NEW = 'mainForm:buttonPanel:new'
DONE = 'mainForm:buttonPanel:done'
SAVE = 'mainForm:buttonPanel:save'
EDIT = 'mainForm:buttonPanel:edit'
YES = 'mainForm:buttonControls:yes'
CANCEL = 'mainForm:buttonPanel:cancel'

TC_ADD_FIRST = 'mainForm:TIMECARD_EDIT_content:oldTimecardLineList2:addTimecardItemButton2'
TC_ADD_NEXT = 'mainForm:buttonPanel:newDetail'
TC_PERSON = 'mainForm:TIMECARD_EDIT_content:ShopPersonZoom:level1'
TC_DATE = 'mainForm:TIMECARD_EDIT_content:workDateValue'
TC_DECRIPTION = 'mainForm:TIMECARD_DETAIL_EDIT_content:ae_p_wka_d_description'
TC_HOURS = 'mainForm:TIMECARD_DETAIL_EDIT_content:actHrsValue2'
TC_WORKORDER = 'mainForm:TIMECARD_DETAIL_EDIT_content:proposalZoom2:level0'
TC_PHASE = 'mainForm:TIMECARD_DETAIL_EDIT_content:proposalZoom2:level1'
TC_ACTION = 'mainForm:TIMECARD_DETAIL_EDIT_content:actionTakenZoom2:level1'
TC_LEAVE_CODE = 'mainForm:TIMECARD_DETAIL_EDIT_content:leaveCodeZoom2:level0'
TC_LABOR_CODE = 'mainForm:TIMECARD_DETAIL_EDIT_content:timeTypeZoom2:level0'
TC_ITEM_NUM = 'mainForm:TIMECARD_DETAIL_EDIT_content:ae_p_wka_d_item_no'
TC_ERROR_MSG = 'mainForm:TIMECARD_DETAIL_EDIT_content:messages'

RTC_WORK_DATE = 'mainForm:RAPID_TIMECARD_EDIT_content:workDate'
RTC_SHOP_PERSON = 'mainForm:RAPID_TIMECARD_EDIT_content:shopPersonZoom0:shopPersonZoom'
RTC_LEAVE_CODE = 'mainForm:RAPID_TIMECARD_EDIT_content:eaveCodeZoom0:leaveCodeZoom'
RTC_HOURS = 'mainForm:RAPID_TIMECARD_EDIT_content:defaultHours'
RTC_SAVE = 'mainForm:buttonPanel:save'
RTC_ADD = 'mainForm:RAPID_TIMECARD_EDIT_content:addDetail'

WO_DESC = 'mainForm:WO_EDIT_content:ae_p_pro_e_description'
WO_REQUESTER = 'mainForm:WO_EDIT_content:CDOCZoom:custId'
WO_RQ_BUTTON = 'mainForm:WO_EDIT_content:CDOCZoom:custId_button'
WO_TYPE = 'mainForm:WO_EDIT_content:WOTCZoom:level0'
WO_CAT = 'mainForm:WO_EDIT_content:WOTCZoom:level1'
WO_STATUS = 'mainForm:WO_EDIT_content:WOTCSZoom:level2'
WO_PROPERTY = 'mainForm:WO_EDIT_content:RFPLZoom:RFPLZoom2'
WO_PROP_ZOOM = 'mainForm:WO_EDIT_content:RFPLZoom:RFPLZoom2_button'
WO_ADD_PHASE = 'mainForm:WO_EDIT_content:oldPhaseList:addPhaseButton'
WO_NUMBER = 'mainForm:WO_VIEW_content:ae_p_pro_e_proposal'

PH_DESC = 'mainForm:PHASE_EDIT_content:ae_p_phs_e_description'
PH_SHOP = 'mainForm:PHASE_EDIT_content:shopShopPerson:level0'
PH_PRIORITY = 'mainForm:PHASE_EDIT_content:priorityCodeZoom:level1'
PH_PRI_ZOOM = 'mainForm:PHASE_EDIT_content:primaryShopPerson:level1_button'
PH_WORK_CODE = 'mainForm:PHASE_EDIT_content:craftCodeZoom:level1'
PH_WORK_CODE_GRP = 'mainForm:PHASE_EDIT_content:craftCodeGroupZoom:level1'
PH_STATUS = 'mainForm:PHASE_EDIT_content:phaseStatusZoom:level2'
PH_PRIMARY = 'mainForm:PHASE_EDIT_content:primaryShopPerson:level1'
PH_SELEC_SHOP_PEOPLE = 'mainForm:PHASE_EDIT_content:shopPeopleBrowse:select_all_check'
PH_REMOVE_SHOP_PEOPLE = 'mainForm:PHASE_EDIT_content:shopPeopleBrowse:deleteShopPerson'

ACCT_SETUP = 'mainForm:sideButtonPanel:moreMenu_2'
ACCT_ADD = 'mainForm:WO_ACCT_SETUP_EDIT_content:charge:addChargeAccounts'
ACCT_NEXT = 'mainForm:buttonPanel:zoomNext'
ACCT_ID = 'mainForm:WO_ACCT_SINGLE_EDIT_content:accountCodeZoom:level0'
ACCT_SUB = 'mainForm:WO_ACCT_SINGLE_EDIT_content:subCodeZoom:level1'
ACCT_PERCENT = 'mainForm:WO_ACCT_SINGLE_EDIT_content:subPercentValue'

CONNECTION = 'DSN=fmax;UID=fmereports;PWD=fmerpts'


def _locate_firefox_profile() -> str:
    home = os.path.expanduser('~')
    profile = ''
    if sys.platform == 'linux':
        profile = os.path.join(home, '.mozilla', 'firefox')
    elif sys.platform == 'darwin':
        profile = os.path.join(
            home, 'Library', 'Application Support', 'Firefox', 'Profiles')
    elif sys.platform == 'win32':
        profile = os.path.join(home, 'AppData', 'Roaming',
                               'Mozilla', 'Firefox', 'Profiles')
    try:
        profile = os.path.join(profile,
                               [d for d in os.listdir(profile)
                                if ('.webdriver' in d)][0])
    except FileNotFoundError:
        profile = ''
    return profile


class AimSession:
    """
    Wrapper class for a selenium webdriver object, tailored to
    interacting with the UW work management web app
    """

    def __init__(self, *, netid: str, driver: Optional[webdriver.Remote] = None) -> None:

        if driver is None:
            opt = webdriver.FirefoxOptions()
            try:
                opt.headless = True
                opt.profile = webdriver.FirefoxProfile(
                    _locate_firefox_profile())
            except (AttributeError, TypeError):
                opt.set_headless(True)
            driver = webdriver.Firefox(
                options=opt, service_log_path=os.devnull)

        self.netid = netid
        self.shop = '17 ELECTRICAL'
        self.driver = driver
        self.driver.implicitly_wait(20)

    def __enter__(self):
        # self.login()
        return self

    def __exit__(self, ex_type, ex_val, ex_trace):
        self.driver.quit()
        return True

    def __getattr__(self, name):
        return getattr(self.driver, name)

    def login(self) -> None:
        "Login to AiM. "
        password = keyring.get_password('aim', self.netid)
        if not password:
            password = getpass.getpass()
            keyring.set_password('aim', self.netid, password)
        if AIM_BASE not in self.driver.current_url:
            self.driver.get(HOME_PAGE)
        self.send_keys_to(UID, self.netid)
        self.send_keys_to(PWD, password)
        self.send_keys_to(PWD, Keys.RETURN)
        while 'NetID' in self.driver.title:
            time.sleep(1)

    def click(self, element_id: str) -> None:
        self.driver.find_element(By.ID, element_id).click()

    def clear(self, element_id: str) -> None:
        self.driver.find_element(By.ID, element_id).clear()

    def send_keys_to(self, element_id: str, keys: str) -> None:
        self.driver.find_element(By.ID, element_id).send_keys(keys)

    def new_timecard(self, employee: str, date: str, entries: Iterable[str]) -> Iterable[str]:

        self.get(AIM_TIMECARD)
        self.click(NEW)
        self.send_keys_to(TC_PERSON, employee)
        self.send_keys_to(TC_DATE, date)
        self.click(TC_ADD_FIRST)
        errors = []
        for i, entry in enumerate(entries):
            workorder, phase, hours, description, action, code = entry
            yield f'Processing... {i+1}/{len(entries)}'
            self.clear(TC_WORKORDER),
            self.clear(TC_PHASE),
            self.clear(TC_DECRIPTION),
            self.clear(TC_ACTION),
            self.clear(TC_HOURS),
            self.clear(TC_LEAVE_CODE)
            self.clear(TC_LABOR_CODE)

            if code in ('S', 'A', 'PH', 'CT', 'HOLIDAY'):
                self.send_keys_to(TC_LEAVE_CODE, code)
            else:
                self.send_keys_to(TC_LABOR_CODE, code)
                self.send_keys_to(TC_WORKORDER, workorder)
                self.send_keys_to(TC_PHASE, phase)
                self.send_keys_to(TC_ACTION, action)
            self.send_keys_to(TC_HOURS, hours)
            self.send_keys_to(TC_DECRIPTION, description)
            if i != len(entries) - 1:
                self.click(TC_ADD_NEXT)
                time.sleep(0.25)
                error = self.find_element(By.ID, TC_ERROR_MSG).text
                if error:
                    errors.append(workorder)
        self.click(DONE)
        self.click(SAVE)

        if errors:
            yield 'Error, invalid entries: {} 🤬'.format(', '.join(errors))
        else:
            yield 'Done! 😎'

        def vacation(self, employee, dates):
            self.get(RAPID_TIMECARD_EDIT)
            self.send_keys_to(RTC_SHOP_PERSON, employee)
            self.send_keys_to(RTC_LEAVE_CODE, 'A')
            self.send_keys_to(RTC_HOURS)
            for date in dates:
                self.clear(RTC_WORK_DATE)
                self.send_keys_to(RTC_WORK_DATE, date)
                self.click(RTC_ADD)
            self.click(RTC_SAVE)


if __name__ == '__main__':
    s = AimSession(netid='wsj3')
    s.login()
