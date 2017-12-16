import logging
from logging.handlers import RotatingFileHandler
import requests
from time import sleep
from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout

from arrow import now
import RPi.GPIO as GPIO
from raspberrypi_utils.input_devices import VibrationSensor
from raspberrypi_utils.output_devices import LED
from raspberrypi_utils.utils import ReadConfigMixin, send_gmail

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

log_filehandler = RotatingFileHandler('/var/log/laundryalarm/laundryalarm.log', maxBytes=1024**2, backupCount=100)
log_filehandler.setFormatter(log_formatter)
log_filehandler.setLevel(logging.INFO)

log_consolehandler = logging.StreamHandler()
log_consolehandler.setFormatter(log_formatter)
log_consolehandler.setLevel(logging.DEBUG)

log = logging.getLogger(__name__)
log.addHandler(log_filehandler)
log.addHandler(log_consolehandler)
log.setLevel(logging.DEBUG)

utils_log = logging.getLogger('raspberrypi_utils.input_devices')
utils_log.setLevel(logging.DEBUG)
utils_log.addHandler(log_consolehandler)

transitions_log = logging.getLogger('transitions')
transitions_log.setLevel(logging.INFO)
transitions_log.addHandler(log_consolehandler)


@add_state_features(Timeout)
class TimeoutMachine(Machine):
    pass


class LaundryAlarm(ReadConfigMixin, TimeoutMachine):
    def __init__(self):
        states = [
            'off',
            {'name': 'starting', 'timeout': 60, 'on_timeout': 'steady_on'},
            'on',
            {'name': 'stopping', 'timeout': 60, 'on_timeout': 'steady_off'},
            'invalid',
        ]
        transitions = [
            # OFF
            {
                'trigger': 'motion_detected',
                'source': 'off',
                'dest': 'starting',
            },
            # STARTING
            {
                'trigger': 'no_motion_detected',
                'source': 'starting',
                'dest': 'off',
            },
            {
                'trigger': 'steady_on',
                'source': 'starting',
                'dest': 'on',
            },
            # ON
            {
                'trigger': 'no_motion_detected',
                'source': 'on',
                'dest': 'stopping',
            },
            # STOPPING
            {
                'trigger': 'motion_detected',
                'source': 'stopping',
                'dest': 'on',
            },
            {
                'trigger': 'steady_off',
                'source': 'stopping',
                'dest': 'off',
                'after': self.notification
            },
            # INVALID
            {
                'trigger': 'error',
                'source': '*',
                'dest': 'invalid',
            },
            {
                'trigger': 'error_resolved',
                'source': 'invalid',
                'dest': 'off',
            },
        ]

        super(LaundryAlarm, self).__init__(
            states=states,
            transitions=transitions,
            initial='off',
            ignore_invalid_triggers=True
        )

        self.config = self.read_config()
        GPIO.setmode(GPIO.BCM)
        self.led = LED(self.config['Main']['LED_PIN'])
        self.threshold = 0.4
        self.sensor = VibrationSensor(auto_sensitivity=1.25, threshold_per_minute=self.threshold)
        self.led.flash(on_seconds=0.25, off_seconds=5)  # because enter_off is not triggered upon startup
        self.last_check_connectivity_frequency_seconds = 600
        self.last_check_connectivity_at = None
        self.last_check_connectivity_result = True
        log.info('Initialized')

    def check(self):
        if not self.check_connectivity():
            self.error()
        elif self.state == 'invalid':
            log.info('Internet connectivity restored.')
            self.error_resolved()
        else:
            rate = self.sensor.read()
            log.debug('Rate = {}'.format(rate))
            if rate > self.threshold:
                self.motion_detected()
            else:
                self.no_motion_detected()
        sleep(self.config['Main']['SLEEP_SECONDS'])

    def check_connectivity(self):
        if not self.last_check_connectivity_at \
           or (now() - self.last_check_connectivity_at).seconds > self.last_check_connectivity_frequency_seconds:
            self.last_check_connectivity_at = now()
            try:
                requests.head('http://www.google.com')
                log.debug('Internet connectivity OK')
                self.last_check_connectivity_result = True
            except requests.ConnectionError:
                log.error('No internet connectivity!')
                self.last_check_connectivity_result = False
        return self.last_check_connectivity_result

    def on_enter_invalid(self):
        self.led.off()

    def on_enter_starting(self):
        self.led.flash(on_seconds=1, off_seconds=1)

    def on_enter_on(self):
        log.info('Laundry started')
        self.led.on()

    def on_enter_stopping(self):
        self.led.flash(on_seconds=0.25, off_seconds=0.25)

    def on_enter_off(self):
        self.sensor.reset()
        log.info('Laundry done')
        self.led.flash(on_seconds=0.25, off_seconds=5)

    def notification(self):
        send_gmail(
            self.config['Notifications']['EMAIL_FROM'],
            self.config['Notifications']['EMAIL_PASSWORD'],
            self.config['Notifications']['EMAILS_TO'],
            'Laundry is done',
            'Your laundry is done at {}, get it while it\'s fluffy!'.format(now(tz='US/Eastern').format('h:mma'))
        )
        log.debug('Notification sent')

    def cleanup(self):
        self.sensor.reset()
        self.led.off()
        GPIO.cleanup()
