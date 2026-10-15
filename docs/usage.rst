=====
Usage
=====

Command Line Usage
==================

Format::

	pywatlow [-h] [-r PORT ADDR PARAM | -w PORT ADDR TEMP | -s PORT ADDR PARAM VALUE]
	         [-t TYPE] [-i INSTANCE] [-b BAUDRATE]

Read the current temperature (in the controller's display units).
This is equivalent to calling `Watlow(port='COM5',address=1).read()`::

	# Read the process value (parameter 4001) of the Watlow controller
	# at address 1 (Watlow controller's default) on serial port COM5:
	>>> pywatlow -r COM5 1 4001
	{'address': 1, 'param': 4001, 'data': 50.5, 'repr': <Repr.FLOAT: 8>, 'error': None}

Any parameter can be read the same way; the controller reports the data type::

	>>> pywatlow -r COM5 1 8003
	{'address': 1, 'param': 8003, 'data': 71, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}

Change the set point. This is equivalent to calling `Watlow(port='COM5',address=1).write(60)`::

	>>> pywatlow -w COM5 1 60
	{'address': 1, 'param': 7001, 'data': 60.0, 'repr': <Repr.FLOAT: 8>, 'error': None}

Write any parameter. Without ``--type`` the parameter is read first to learn
how the controller encodes it::

	>>> pywatlow -s COM5 1 8003 71
	{'address': 1, 'param': 8003, 'data': 71, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}

Module Usage
============

To use pywatlow in a project::

	from pywatlow.watlow import Watlow
	watlow = Watlow(port='COM5', address=1)
	print(watlow.read())
	print(watlow.readSetpoint())
	print(watlow.write(55))

	##### Returns #####
	{'address': 1, 'param': 4001, 'data': 59.5, 'repr': <Repr.FLOAT: 8>, 'error': None}
	{'address': 1, 'param': 7001, 'data': 60.0, 'repr': <Repr.FLOAT: 8>, 'error': None}
	{'address': 1, 'param': 7001, 'data': 55.0, 'repr': <Repr.FLOAT: 8>, 'error': None}

Using multiple temperature controllers on a single USB to RS485 converter::

	from pywatlow.watlow import Watlow
	import serial

	ser = serial.Serial()
	ser.port = 'COM5'
	ser.baudrate = 38400  # Default baudrate for Watlow controllers
	ser.timeout = 0.5
	ser.open()

	watlow_one = Watlow(serial=ser, address=1)
	watlow_two = Watlow(serial=ser, address=2)
	print(watlow_one.read())
	print(watlow_two.read())

	##### Returns #####
	{'address': 1, 'param': 4001, 'data': 50.5, 'repr': <Repr.FLOAT: 8>, 'error': None}
	{'address': 2, 'param': 4001, 'data': 60.0, 'repr': <Repr.FLOAT: 8>, 'error': None}

Every reply is read by the length its header announces, so controllers sharing
a port never leave bytes behind for the next one.


Reading Other Parameters
========================

See the Watlow `user manual <https://www.watlow.com/-/media/documents/user-manuals/pm-pid-1.ashx>`_
for the parameter IDs and their functions. Any parameter can be read with
`readParam()`; the controller states the data type in its reply, so none has
to be given::

	from pywatlow.watlow import Watlow
	watlow = Watlow(port='COM5', address=1)

	# Read the current heat algorithm
	print(watlow.readParam(8003))

	##### Returns #####
	{'address': 1, 'param': 8003, 'data': 71, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}  # 71 --> PID algorithm

The ``repr`` key is a :class:`pywatlow.protocol.Repr` naming the data
representation the controller used. Floating point parameters come back as
``float``; enumerations (the manual's "uint" parameters, such as 8003) come
back as the integer code listed in the manual; strings as ``str``.

The `data_type` argument of `readParam()` is still accepted for code written
against pywatlow 0.1.x, but it is ignored.

Note: All methods of the Watlow object that read/write parameters use an instance
of 1 unless specified (e.g. `watlow.readParam(7001, instance=2)`). The
instance may be an int or the historical two-character string (`'02'`).

Setting Other Parameters
========================

`watlow.writeParam()` writes a parameter. How the value is encoded on the
wire depends on the parameter's data representation, which can be given with
`data_type` or discovered by reading the parameter first:

* `float` -- floating point parameters (set points, ramp rates, offsets...)
* `int` -- enumerated parameters, written as a wide (2-byte) enumeration.
  This is what every "uint" parameter in the PM manual uses, and what
  `int` meant in pywatlow 0.1.x.
* `str` -- string parameters
* a :class:`pywatlow.protocol.Repr` member for anything else (`Repr.ENUM`,
  `Repr.UWORD`, ...)
* `None` (the default) -- read the parameter and reuse the representation the
  controller reported. One extra exchange, but it cannot be wrong.

If instead of a PID algorithm we would like something relatively simple like an
"on-off" algorithm, we can set the value of parameter 8003 to 64::

	from pywatlow.watlow import Watlow
	watlow = Watlow(port='COM5', address=1)

	print(watlow.readParam(8003))
	print(watlow.writeParam(8003, 64))        # type discovered by reading first
	print(watlow.writeParam(8003, 71, int))   # type given: one exchange

	##### Returns #####
	{'address': 1, 'param': 8003, 'data': 71, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}  # 71 --> PID algorithm
	{'address': 1, 'param': 8003, 'data': 64, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}  # 64 --> on/off algorithm
	{'address': 1, 'param': 8003, 'data': 71, 'repr': <Repr.WIDE_ENUM: 15>, 'error': None}  # Back to 71, PID

Error Handling
==============

Errors are passed through using the 'error' key of the returned dictionary;
'data' is `None` whenever 'error' is set. All of them derive from
:class:`pywatlow.protocol.WatlowError`:

* :class:`pywatlow.protocol.NoResponse` -- nothing came back within the timeout.
  Here there is no temperature controller at address 2::

	print(watlow_one.read())
	print(watlow_two.read())

	##### Returns #####
	{'address': 1, 'param': 4001, 'data': 55.0, 'repr': <Repr.FLOAT: 8>, 'error': None}
	{'address': 2, 'param': 4001, 'data': None, 'repr': None, 'error': NoResponse('no response from address 2')}

* :class:`pywatlow.protocol.WatlowException` -- the controller answered with
  an exception instead of a reply. Its `code` is an
  :class:`pywatlow.protocol.ExceptionCode`. Writing a value the controller
  does not accept, or writing a read-only parameter, ends up here::

	print(watlow.writeParam(4001, 100.0, float))      # process value is read-only
	print(watlow.writeParam(7014, 1647, int))         # enum code this model rejects

	##### Returns #####
	{'address': 1, 'param': 4001, 'data': None, 'repr': None, 'error': WatlowException('controller exception 128 (UNSUPPORTED_FUNCTION)')}
	{'address': 1, 'param': 7014, 'data': None, 'repr': None, 'error': WatlowException('controller exception 134 (DATA_OUT_OF_RANGE)')}

  pywatlow 0.1.x reported both of these as a timeout or as an unparseable
  message, because an exception reply is shorter than the acknowledgement it
  waited for.

* :class:`pywatlow.protocol.InvalidResponse` -- a frame failed a check byte,
  was truncated, or came from another address.
* :class:`pywatlow.protocol.ProtocolError` -- the request could not be built,
  for instance a value that does not fit the data type.

Using the codec directly
========================

:mod:`pywatlow.protocol` builds and parses frames without touching a serial
port, which is handy for other transports or for tests::

	from pywatlow import protocol

	request = protocol.build_write_request(address=1, param=7014, repr_=int, value=13)
	reply = protocol.parse_reply(frame_from_the_wire, address=1)
	print(reply.param, reply.repr, reply.value)
