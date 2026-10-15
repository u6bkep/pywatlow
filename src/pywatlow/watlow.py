import serial as ser

from pywatlow import protocol
from pywatlow.protocol import DATA_CHECK_LEN
from pywatlow.protocol import HEADER_LEN
from pywatlow.protocol import InvalidResponse
from pywatlow.protocol import NoResponse
from pywatlow.protocol import ProtocolError
from pywatlow.protocol import Repr
from pywatlow.protocol import WatlowError
from pywatlow.protocol import WatlowException

__all__ = ['Watlow', 'Repr', 'WatlowError', 'WatlowException', 'NoResponse',
           'InvalidResponse', 'ProtocolError']

#: Parameter ids used by the convenience wrappers (Control Loop, instance 1).
PARAM_PROCESS_VALUE = 4001
PARAM_SET_POINT = 7001


class Watlow():
    '''
    Object representing a Watlow PID temperature controller. This class
    builds and parses Standard Bus (BACnet MS/TP) messages to and from
    Watlow EZ-ZONE controllers; the wire format lives in
    :mod:`pywatlow.protocol`.

    * **serial**: serial object (see pySerial's serial.Serial class) or `None`
    * **port** (str): string representing the serial port or `None`
    * **timeout** (float): Read timeout value in seconds
    * **address** (int): Watlow controller address (found in the setup menu). Acceptable values are 1 through 16.
    * **baudrate** (int): Standard Bus baud rate; Watlow's default is 38400

    `timeout`, `baudrate` and `port` are not necessary if a serial object was
    already passed with those arguments.
    '''
    def __init__(self, serial=None, port=None, timeout=0.5, address=1, baudrate=38400):
        self.timeout = timeout
        self.baudrate = baudrate
        self.address = address
        if serial:
            self.port = serial.port
            self.serial = serial
        else:
            self.port = port
            self.open()

    def open(self):
        self.serial = ser.Serial(self.port, self.baudrate, timeout=self.timeout)

    def close(self):
        self.serial.flush()
        self.serial.close()

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _read_frame(self):
        '''
        Reads exactly one frame from the serial port, however long it is.

        The header announces the ADU length, so the read is driven by the
        frame itself rather than by a guess about the data type. An exception
        reply (12 bytes) and an ack (18 to 21 bytes) are therefore both read
        cleanly, and nothing is left behind to corrupt the next exchange.
        '''
        header = self.serial.read(HEADER_LEN)
        if not header:
            raise NoResponse('no response from address {0}'.format(self.address))
        if len(header) < HEADER_LEN:
            raise InvalidResponse('short frame from address {0}: {1}'.format(self.address, header.hex()))
        adu_len = protocol.header_adu_len(header)
        rest = self.serial.read(adu_len + DATA_CHECK_LEN)
        frame = header + rest
        if len(rest) < adu_len + DATA_CHECK_LEN:
            raise InvalidResponse('truncated frame from address {0}: {1}'.format(self.address, frame.hex()))
        return frame

    def _transact(self, request):
        '''
        Sends ``request`` and returns the decoded :class:`protocol.Reply`.
        Raises a :class:`WatlowError` subclass on any failure.
        '''
        self.serial.reset_input_buffer()
        self.serial.write(request)
        return protocol.parse_reply(self._read_frame(), self.address)

    def _result(self, request, param):
        '''
        Runs ``request`` and packs the outcome into the result dict::

            {'address': 1, 'param': 7001, 'data': 80.0, 'repr': Repr.FLOAT, 'error': None}

        `error` is `None` on success, otherwise the exception describing what
        went wrong (a :class:`WatlowException` when the controller rejected
        the request, :class:`NoResponse` on timeout, :class:`InvalidResponse`
        on a corrupt frame). `data` is always `None` when `error` is set.
        '''
        output = {'address': self.address, 'param': param, 'data': None, 'repr': None, 'error': None}
        try:
            reply = self._transact(request)
        except WatlowError as e:
            output['error'] = e
        except ser.SerialException as e:
            output['error'] = e
        else:
            output['param'] = reply.param
            output['data'] = reply.value
            output['repr'] = reply.repr
        return output

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, instance='01'):
        '''
        Reads the current temperature. This is a wrapper around `readParam()`
        and is equivalent to `readParam(4001, instance=instance)`.

        Returns a dict containing the response data, parameter ID, and address.
        * **instance**: the channel to read, as an int or a two digit string (e.g. '01', '05')
        '''
        return self.readParam(PARAM_PROCESS_VALUE, instance=instance)

    def readSetpoint(self, instance='01'):
        '''
        Reads the current setpoint. This is a wrapper around `readParam()` and is
        equivalent to `readParam(7001, instance=instance)`.

        Returns a dict containing the response data, parameter ID, and address.
        * **instance**: the channel to read, as an int or a two digit string (e.g. '01', '05')
        '''
        return self.readParam(PARAM_SET_POINT, instance=instance)

    def readParam(self, param, data_type=None, instance='01'):
        '''
        Reads a parameter from the controller at the object's address. See the Watlow
        `user manual <https://www.watlow.com/-/media/documents/user-manuals/pm-pid-1.ashx>`_
        for individual parameters and the Usage section of these docs.

        * **param**: a four or five digit integer corresponding to a Watlow parameter (e.g. 4001, 7001)
        * **data_type**: ignored; the reply states its own data type. Kept so
          code written for pywatlow 0.1.x keeps working.
        * **instance**: the channel to read, as an int or a two digit string (e.g. '01', '05')

        Returns a dict containing the response data, parameter ID, data
        representation (`repr`), and address. Enumerations come back as the
        integer code listed in the manual (e.g. 71 for PID on parameter 8003).
        '''
        param = int(param)
        return self._result(protocol.build_read_request(self.address, param, instance), param)

    def write(self, value, instance='01'):
        '''
        Changes the watlow temperature setpoint. Takes a value (in the controller's
        display units), builds request, writes to watlow, receives and returns
        response object.

        * **value**: an int or float representing the new target setpoint
        * **instance**: the channel to set, as an int or a two digit string (e.g. '01', '05')

        This is a wrapper around `writeParam()` and is equivalent to
        `writeParam(7001, value, float, instance)`.

        Returns a dict containing the response data, parameter ID, and address.
        '''
        return self.writeParam(PARAM_SET_POINT, value, float, instance)

    def writeParam(self, param, value, data_type=None, instance='01'):
        '''
        Changes the value of the passed watlow parameter ID. See the Watlow
        `user manual <https://www.watlow.com/-/media/documents/user-manuals/pm-pid-1.ashx>`_
        for individual parameters and the Usage section of these docs.

        * **param**: a four or five digit integer corresponding to a Watlow parameter (e.g. 7001, 8003)
        * **value**: the new value: a number, an enumeration code from the manual, or a string
        * **data_type**: how to encode `value` on the wire. `float` for floating
          point parameters, `int` for the enumerated ones (the manual's
          "uint" parameters), `str` for strings, or a :class:`Repr` member for
          anything else. With `None` (the default) the parameter is read first
          and written back in whatever representation the controller reported,
          which costs one extra exchange but cannot be wrong.
        * **instance**: the channel to set, as an int or a two digit string (e.g. '01', '05')

        Returns a dict containing the response data, parameter ID, and address.
        When the controller rejects the value (for instance an enumeration code
        it does not support) `error` holds a :class:`WatlowException` whose
        `code` says why.
        '''
        param = int(param)
        if data_type is None:
            probe = self.readParam(param, instance=instance)
            if probe['error'] is not None:
                return probe
            repr_ = probe['repr']
        else:
            try:
                repr_ = protocol.as_repr(data_type)
            except ProtocolError as e:
                return {'address': self.address, 'param': param, 'data': None, 'repr': None, 'error': e}
        try:
            request = protocol.build_write_request(self.address, param, repr_, value, instance)
        except ProtocolError as e:
            return {'address': self.address, 'param': param, 'data': None, 'repr': repr_, 'error': e}
        return self._result(request, param)
