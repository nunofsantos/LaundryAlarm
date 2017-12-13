import logging
from time import sleep
from transitions import Machine
from transitions.extensions.states import add_state_features, Timeout

from arrow import now
import RPi.GPIO as GPIO
from raspberrypi_utils.input_devices import VibrationSensor
from raspberrypi_utils.output_devices import LED
from raspberrypi_utils.utils import ReadConfigMixin, send_gmail

logging.basicConfig(format='%(asctime)s - %(levelname)s  (%(module)s) - %(message)s', level=logging.ERROR)
logging.getLogger('transitions').setLevel(logging.INFO)
logging.getLogger('raspberrypi_utils').setLevel(logging.ERROR)
logging.getLogger(__name__).setLevel(logging.DEBUG)
log = logging.getLogger()


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
        self.threshold = 1
        self.sensor = VibrationSensor(threshold_per_minute=self.threshold)

    def check(self):
        rate = self.sensor.read()
        if rate > self.threshold:
            self.motion_detected()
        else:
            self.no_motion_detected()
        sleep(self.config['Main']['SLEEP_SECONDS'])

    def on_enter_starting(self):
        self.led.flash(on_seconds=1, off_seconds=1)

    def on_enter_on(self):
        self.led.on()

    def on_enter_stopping(self):
        self.led.flash(on_seconds=0.25, off_seconds=0.25)

    def on_enter_off(self):
        self.sensor.reset()
        self.led.off()

    def notification(self):
        send_gmail(
            self.config['Notifications']['EMAIL_FROM'],
            self.config['Notifications']['EMAIL_PASSWORD'],
            self.config['Notifications']['EMAILS_TO'],
            'Laundry is done',
            'Your laundry is done at {}, get it while it\'s fluffy!'.format(now(tz='US/Eastern').format('h:mma'))
        )

    def cleanup(self):
        self.sensor.reset()
        self.led.off()
        GPIO.cleanup()
