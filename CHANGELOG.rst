
Changelog
=========

0.2.0 (unreleased)
------------------
Protocol overhaul, built on Watlow's own ``WatbusAppLibrary`` (the managed
half of the EZ-ZONE Configurator) instead of captured traffic.

* Enumerated parameters are written the way Watlow's software writes them
  (``0F 02 hi lo``, from bus address 00). 0.1.x sent the reply encoding
  (``0F 01 hi lo``), which some controllers do not act on.
* Replies are read by the length announced in their header instead of a
  guessed fixed length, so controller exceptions (12-byte frames) are
  decoded and reported as ``WatlowException`` with an ``ExceptionCode``
  instead of surfacing as a timeout, and a wrong data type can no longer
  leave bytes behind in the port.
* Replies decode every data representation (UByte..Long, Enum, Float,
  String, List, WideEnum). ``readParam()`` no longer needs ``data_type``;
  the argument is accepted and ignored. Results gain a ``repr`` key.
* ``writeParam()`` accepts ``float``, ``int`` (wide enum), ``str``, any
  ``Repr`` member, or ``None`` to read the parameter first and reuse the
  representation the controller reports.
* New pure codec module ``pywatlow.protocol`` (frames, check bytes,
  requests, replies) usable without a serial port.
* Errors are typed: ``NoResponse``, ``InvalidResponse``, ``ProtocolError``,
  ``WatlowException`` (all ``WatlowError``). Nothing is printed any more.
* ``Watlow()`` takes ``baudrate``; the CLI gains ``--set``, ``--type``,
  ``--instance`` and ``--baudrate`` and reads any parameter.
* Dropped the ``crcmod`` dependency (CRC-16 is in pure Python).
* Removed the private ``_buildReadRequest``/``_buildWriteRequest``/
  ``_parseResponse``/``_validateResponse``/``_headerCheckByte``/
  ``_dataCheckByte`` helpers; use ``pywatlow.protocol``.
* Requires Python 3.7+.

0.1.4 (2022-04-15)
------------------
* Fixed message generation/parsing for addresses 11 through 16

0.1.3 (2021-07-25)
------------------
* Fixed support for multiple instances where the parameter data type is an integer

0.1.2 (2021-01-13)
------------------
* added support for multiple instances, like in the RM series controllers with multiple channels

0.1.1 (2020-08-15)
------------------

* Initial PyPI release
* Various tox, badge, and metadata fixes
* Removed unused temperature unit conversion functions
* Updated Python version requirements
* Minor documentation clean up

0.1.0 (2020-08-08)
------------------

* Added basic functionality

  * Reading/writing of Watlow parameters
  * Request message generation
  * Calculation of check bytes
  * Response message parsing
