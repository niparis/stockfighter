import shelve
import os
import time
import threading
from contextlib import closing

import requests

from stockfighter import config
from stockfighter import BASE_PATH

API_KEY = config.get('api', 'APIKEY')


class GameMaster(object):
    """
        Starts / Restarts sessions
        Keeps game info and feeds it to further objects
        Starts a thread that will update the game state every 5 seconds (_update method)
            - thread start after start or restart methods are called
        from : https://discuss.starfighters.io/t/the-gm-api-how-to-start-stop-restart-resume-trading-levels-automagically/143/2

        Public Methods :
            - start     : arg : level, string identifying the level. Must be part of _LEVELS class attribute
            - stop      : stop a level
            - restart   : restart a level with same stock / venue
            - completion : Prints completion (number of days in game). Usefull to get extra data

    """
    _URL = 'https://www.stockfighter.io/gm'
    _LEVELS = ['first_steps', 'chock_a_block', 'sell_side']

    def __init__(self, db=None):
        self.ready = None   # Is the instance ready ?
        self._shelve_path = os.path.join(BASE_PATH, 'lib/gm.db')
        self.headers = {
            'Cookie' : 'api_key={}'.format(API_KEY)
                       }
        self._instanceId = self._load_instance_id()

        if not db:
            raise Exception('An instance of StockDataBase needs to be passed as argument db')
        else:
            self._db = db

        if self._instanceId:
            # try to resume
            self.resume()

        ## setting up level info
        self.target_price_l2 = None
        self._live = None

    """
        API helpers
    """
    def _post(self, url):
        resp = requests.post(url, headers=self.headers)
        return resp.json()

    def _get(self, url):
        resp = requests.get(url, headers=self.headers)
        return resp.json()

    """
        Saving and Loading the instanceId to disk for easier resume
    """
    def _save_instance_id(self, instanceid):
        with closing(shelve.open(self._shelve_path)) as db:
            db['instanceId'] = instanceid

    def _load_instance_id(self):
        with closing(shelve.open(self._shelve_path)) as db:
            instanceid = db.get('instanceId')

        return instanceid

    """
        Updating the GameMaster to know advancement / get extra data
    """
    def _start_update_thread(self):
        thrd = threading.Thread(target=self._loop)
        thrd.daemon = True
        thrd.start()

    def _loop(self):
        time.sleep(2)
        while True:
            self._update()
            time.sleep(5)

    def completion(self):
        """
            Updates GameMaster so that we know what is the current trading day
        """
        if self._live:
            print('{}/{} trading days'.format(self._tradingDay, self._endOfTheWorldDay))
        else:
            print('Game closed')

    def _flash_level2(self):
        """
            Parses the flash message for level 2 (it includes the target price)
        """
        flash = self._status.get('flash', {}).get('info')
        if flash:
            idx1 = flash.index('$')
            idx2 = flash[idx1 + 1:].index('$')
            self.target_price_l2 = float(flash[idx1 + idx2 + 2 : - 1])
        else:
            self.target_price_l2 = None

    def _update(self):
        url = self._URL + '/instances/{instanceId}'.format(instanceId=self._instanceId)
        resp = self._get(url)
        self._live = resp.get('ok')
        if self._live:
            self._endOfTheWorldDay = resp.get('details', {}).get('endOfTheWorldDay')
            self._tradingDay = resp.get('details', {}).get('tradingDay')
            self._status = resp
            self._flash_level2()

    """
        Controls the GameMaster
    """
    def _parse_starting_info(self, resp):
        if resp.get('ok'):
            self.account = resp.get('account')
            self._instanceId = resp.get('instanceId')
            self.tickers = resp.get('tickers')
            self.venues = resp.get('venues')
            self._start_resp = resp
            self.target_price_l2 = None
            ret_val = True
            self.ready = True
        else:
            print('Error : {}'.format(resp.get('error')))
            ret_val = False
            self.ready = False

        return ret_val

    def start(self, level):
        if level not in self._LEVELS:
            raise Exception('Available levels are : {}'.fornat(self._LEVELS))

        url = self._URL + '/levels/{level}'.format(level=level)
        resp = self._post(url)
        if self._parse_starting_info(resp):
            self._save_instance_id(self._instanceId)
            print('GameMaster : level {} initiated'.format(level))
            self._start_update_thread()

    def stop(self):
        if self._instanceId is not None:
            url = self._URL + '/instances/{instanceId}/stop'.format(instanceId=self._instanceId)
            self._post(url)
            print('Stopped')
        else:
            raise Exception('Cant stop because there is no recorded instanceId')

    def restart(self):
        if self._instanceId is not None:
            url = self._URL + '/instances/{instanceId}/restart'.format(instanceId=self._instanceId)
            resp = self._post(url)
            if self._parse_starting_info(resp):
                print('Restarted')
                self._start_update_thread()
        else:
            raise Exception('Cant restart because there is no recorded instanceId')

    def resume(self):
        if self._instanceId is not None:
            url = self._URL + '/instances/{instanceId}/resume'.format(instanceId=self._instanceId)
            resp = self._post(url)
            if self._parse_starting_info(resp):
                print('Resumed')
        else:
            raise Exception('Cant resume because there is no recorded instanceId')
