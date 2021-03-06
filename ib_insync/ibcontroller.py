import os
import asyncio
import logging
import configparser
from contextlib import suppress

from ib_insync.objects import Object
from ib_insync.contract import Forex
from ib_insync.ib import IB
from ib_insync.event import Event
import ib_insync.util as util

__all__ = ['IBC', 'IBController', 'Watchdog']


class IBC(Object):
    """
    Programmatic control over starting and stopping TWS/Gateway
    using IBC (https://github.com/IbcAlpha/IBC).

    This is not intended to be run in a notebook.

    Arguments:

    * ``twsVersion`` (required): The major version number for TWS or gateway.
    * ``tradingMode``: 'live' or 'paper'.
    * ``userid``: IB account username. It is recommended to set the real
      username/password in a secured IBC config file.
    * ``password``: IB account password.
    * ``twsPath``: Path to the TWS installation folder.

      =======  ==============
      Default
      =======================
      Linux    ~/Jts
      OS X     ~/Applications
      Windows  C:\\\\Jts
      =======  ==============

    * ``twsSettingsPath``: Path to the TWS settings folder.

      ========  =============
      Default
      =======================
      Linux     ~/Jts
      OS X      ~/Jts
      Windows   Not available
      ========  =============

    * ``ibcPath``: Path to the IBC installation folder.

      ========  =============
      Default
      =======================
      Linux     /opt/ibc
      OS X      /opt/ibc
      Windows   C:\\\\IBC
      ========  =============

    * ``ibcIni``: Path to the IBC configuration file.

      ========  =============
      Default
      =======================
      Linux     ~/ibc/config.ini
      OS X      ~/ibc/config.ini
      Windows   %%HOMEPATH%%\\\\Documents\\\\IBC\\\\config.ini
      ========  =============

    * ``javaPath``: Path to Java executable.
      Default is to use the Java VM included with TWS/gateway.
    * ``fixuserid``: FIX account user id (gateway only).
    * ``fixpassword``: FIX account password (gateway only).

    To use IBC on Windows, the proactor (or quamash) event loop
    must have been set:

    .. code-block:: python

        import asyncio
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    Example usage:

    .. code-block:: python

        ibc = IBC(969, gateway=True, tradingMode='live',
                userid='edemo', password='demouser')
        ibc.start()
        IB.run()
    """

    IbcLogLevel = logging.DEBUG

    _Args = dict(
        # key=(Default, UnixArg, WindowsArg)
        twsVersion=(None, '', ''),
        gateway=(None, '--gateway', '/Gateway'),
        tradingMode=(None, '--mode=', '/Mode:'),
        twsPath=(None, '--tws-path=', '/TwsPath:'),
        twsSettingsPath=(None, '--tws-settings-path=', ''),
        ibcPath=(None, '--ibc-path=', '/IbcPath:'),
        ibcIni=(None, '--ibc-ini=', '/Config:'),
        javaPath=(None, '--java-path=', '/JavaPath:'),
        userid=(None, '--user=', '/User:'),
        password=(None, '--pw=', '/PW:'),
        fixuserid=(None, '--fix-user=', '/FIXUser:'),
        fixpassword=(None, '--fix-pw=', '/FIXPW:'))

    defaults = {k: v[0] for k, v in _Args.items()}
    __slots__ = list(defaults) + ['_proc', '_logger', '_monitor']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        if not self.ibcPath:
            self.ibcPath = '/opt/ibc' if os.sys.platform != 'win32' \
                else 'C:\\IBC'
        self._proc = None
        self._monitor = None
        self._logger = logging.getLogger('ib_insync.IBC')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.terminate()

    def start(self):
        """
        Launch TWS/IBG.
        """
        util.syncAwait(self.startAsync())

    def terminate(self):
        """
        Terminate TWS/IBG.
        """
        util.syncAwait(self.terminateAsync())

    async def startAsync(self):
        if self._proc:
            return
        self._logger.info('Starting')

        # create shell command
        win32 = os.sys.platform == 'win32'
        cmd = [
            f'{self.ibcPath}\\scripts\\StartIBC.bat' if win32 else
            f'{self.ibcPath}/scripts/ibcstart.sh']
        for k, v in self.dict().items():
            arg = IBC._Args[k][2 if win32 else 1]
            if v:
                if arg.endswith('=') or arg.endswith(':'):
                    cmd.append(f'{arg}{v}')
                elif arg:
                    cmd.append(arg)
                else:
                    cmd.append(str(v))

        # run shell command
        self._proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE)
        self._monitor = asyncio.ensure_future(self.monitorAsync())

    async def terminateAsync(self):
        if not self._proc:
            return
        self._logger.info('Terminating')
        if self._monitor:
            self._monitor.cancel()
            self._monitor = None
        with suppress(ProcessLookupError):
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None

    async def monitorAsync(self):
        while self._proc:
            line = await self._proc.stdout.readline()
            if not line:
                break
            self._logger.log(IBC.IbcLogLevel, line.strip().decode())


class IBController(Object):
    """
    For new installations it is recommended to use IBC instead.

    Programmatic control over starting and stopping TWS/Gateway
    using IBController (https://github.com/ib-controller/ib-controller).

    On Windows the the proactor (or quamash) event loop must have been set:

    .. code-block:: python

        import asyncio
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    This is not intended to be run in a notebook.
    """
    defaults = dict(
        APP='TWS',  # 'TWS' or 'GATEWAY'
        TWS_MAJOR_VRSN='969',
        TRADING_MODE='live',  # 'live' or 'paper'
        IBC_INI='~/IBController/IBController.ini',
        IBC_PATH='~/IBController',
        TWS_PATH='~/Jts',
        LOG_PATH='~/IBController/Logs',
        TWSUSERID='',
        TWSPASSWORD='',
        JAVA_PATH='',
        TWS_CONFIG_PATH='')
    __slots__ = list(defaults) + ['_proc', '_logger', '_monitor']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        self._proc = None
        self._monitor = None
        self._logger = logging.getLogger('ib_insync.IBController')

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_exc):
        self.terminate()

    def start(self):
        """
        Launch TWS/IBG.
        """
        util.syncAwait(self.startAsync())

    def stop(self):
        """
        Cleanly shutdown TWS/IBG.
        """
        util.syncAwait(self.stopAsync())

    def terminate(self):
        """
        Terminate TWS/IBG.
        """
        util.syncAwait(self.terminateAsync())

    async def startAsync(self):
        if self._proc:
            return
        self._logger.info('Starting')

        # expand paths
        d = self.dict()
        for k, v in d.items():
            if k.endswith('_PATH') or k.endswith('_INI'):
                d[k] = os.path.expanduser(v)
        if not d['TWS_CONFIG_PATH']:
            d['TWS_CONFIG_PATH'] = d['TWS_PATH']
        self.update(**d)

        # run shell command
        ext = 'bat' if os.sys.platform == 'win32' else 'sh'
        cmd = f'{d["IBC_PATH"]}/Scripts/DisplayBannerAndLaunch.{ext}'
        env = {**os.environ, **d}
        self._proc = await asyncio.create_subprocess_exec(
            cmd, env=env, stdout=asyncio.subprocess.PIPE)
        self._monitor = asyncio.ensure_future(self.monitorAsync())

    async def stopAsync(self):
        if not self._proc:
            return
        self._logger.info('Stopping')

        # read ibcontroller ini file to get controller port
        txt = '[section]' + open(self.IBC_INI).read()
        config = configparser.ConfigParser()
        config.read_string(txt)
        contrPort = config.getint('section', 'IbControllerPort')

        _reader, writer = await asyncio.open_connection('127.0.0.1', contrPort)
        writer.write(b'STOP')
        await writer.drain()
        writer.close()
        await self._proc.wait()
        self._proc = None
        self._monitor.cancel()
        self._monitor = None

    async def terminateAsync(self):
        if not self._proc:
            return
        self._logger.info('Terminating')
        self._monitor.cancel()
        self._monitor = None
        with suppress(ProcessLookupError):
            self._proc.terminate()
            await self._proc.wait()
        self._proc = None

    async def monitorAsync(self):
        while self._proc:
            line = await self._proc.stdout.readline()
            if not line:
                break
            self._logger.info(line.strip().decode())


class Watchdog(Object):
    """
    Start, connect and watch over the TWS or gateway app and try to keep it
    up and running.

    The idea is to wait until there is no traffic coming from the app for
    a certain amount of time (the ``appTimeout`` parameter). This triggers
    a historical request to be placed just to see if the app is still alive
    and well. If yes, then continue, if no then restart the whole app
    and reconnect. Restarting will also occur directly on error 1100.

    Arguments:

    * ``controller`` (required): IBC or IBController instance;
    * ``ib`` (required): IB instance to be used. Do no connect this
      instance as Watchdog takes care of that.
    * ``host``, ``port``, ``clientId`` and ``connectTimeout``: Used for
      connecting to the app;
    * ``appStartupTime``: Time (in seconds) that the app is given to start up;
      Make sure that it is given ample time;
    * ``appTimeout``: Timeout (in seconds) for network traffic idle time;
    * ``retryDelay``: Time (in seconds) to restart app after a
      previous failure;

    Note: ``util.patchAsyncio()`` must have been called before.

    This is not intended to be run in a notebook.

    Example usage:

    .. code-block:: python

        util.patchAsyncio()

        ibc = IBC(973, gateway=True, tradingMode='paper')
        ib = IB()
        app = Watchdog(ibc, ib, port=4002)
        app.start()
        print(app.ib.accountValues())
        IB.run()

    Events:
        * ``startingEvent(watchdog)``
        * ``startedEvent(watchdog)``
        * ``stoppingEvent(watchdog)``
        * ``stoppedEvent(watchdog)``
        * ``softTimeoutEvent(watchdog)``
        * ``hardTimeoutEvent(watchdog)``
    """

    events = [
        'startingEvent', 'startedEvent', 'stoppingEvent', 'stoppedEvent',
        'softTimeoutEvent', 'hardTimeoutEvent']

    defaults = dict(
        controller=None,
        ib=None,
        host='127.0.0.1',
        port='7497',
        clientId=1,
        connectTimeout=2,
        appStartupTime=30,
        appTimeout=20,
        retryDelay=2)
    __slots__ = list(defaults.keys()) + events + [
        '_watcher', '_logger', '_isRunning', '_isRestarting']

    def __init__(self, *args, **kwargs):
        Object.__init__(self, *args, **kwargs)
        Event.init(self, Watchdog.events)
        if not self.controller:
            raise ValueError('No controller supplied')
        if not self.ib:
            raise ValueError('No IB instance supplied')
        if self.ib.isConnected():
            raise ValueError('IB instance must not be connected')
        assert 0 < self.appTimeout < 60
        assert self.retryDelay > 0
        self._watcher = asyncio.ensure_future(self._watchAsync())
        self._logger = logging.getLogger('ib_insync.Watchdog')
        self._isRunning = False
        self._isRestarting = False
        self.ib.errorEvent += self._onError
        self.ib.disconnectedEvent += self._stop

    def start(self):
        self._logger.info('Starting')
        self._isRunning = True
        self._isRestarting = False
        self.startingEvent.emit(self)
        self.controller.start()
        IB.sleep(self.appStartupTime)
        try:
            self._connect()
            self.ib.setTimeout(self.appTimeout)
            self.startedEvent.emit(self)
        except Exception:
            self.controller.terminate()
            self._scheduleRestart()

    def stop(self):
        self._isRunning = False
        self._stop()

    def _stop(self):
        self._logger.info('Stopping')
        self.stoppingEvent.emit(self)
        self._disconnect()
        self.controller.terminate()
        self.stoppedEvent.emit(self)
        if self._isRunning:
            self._scheduleRestart()

    def _connect(self):
        self.ib.connect(
            self.host, self.port, self.clientId, self.connectTimeout)

    def _disconnect(self):
        self.ib.disconnect()

    def _scheduleRestart(self):
        if self._isRestarting:
            return
        self._isRestarting = True
        loop = asyncio.get_event_loop()
        loop.call_later(self.retryDelay, self.start)
        self._logger.info(f'Schedule restart in {self.retryDelay}s')

    def _onError(self, reqId, errorCode, errorString, contract):
        if errorCode == 1100:
            self._logger.error(f'Error 1100: {errorString}')
            self._stop()

    async def _watchAsync(self):
        while True:
            await self.ib.wrapper.timeoutEv.wait()
            # soft timeout, probe the app with a historical request
            self._logger.debug('Soft timeout')
            self.softTimeoutEvent.emit(self)
            contract = Forex('EURUSD')
            probe = self.ib.reqHistoricalDataAsync(
                contract, '', '30 S', '5 secs', 'MIDPOINT', False)
            try:
                bars = await asyncio.wait_for(probe, 4)
                if not bars:
                    raise Exception()
                self.ib.setTimeout(self.appTimeout)
            except Exception:
                # hard timeout, flush everything and start anew
                self._logger.error('Hard timeout')
                self.hardTimeoutEvent.emit(self)
                self._stop()


if __name__ == '__main__':
    asyncio.get_event_loop().set_debug(True)
    util.logToConsole(logging.DEBUG)
    util.patchAsyncio()
    ibc = IBC(973, gateway=True, tradingMode='paper')
#             userid='edemo', password='demouser')
    ib = IB()
    app = Watchdog(ibc, ib, port=4002, appStartupTime=15, appTimeout=10)
    app.start()
    IB.run()
