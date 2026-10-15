Watlow Messaging Structure
==========================

Watlow "Standard Bus" is a BACnet MS/TP variant carried over EIA-485 (38400
baud, 8N1 by default). The layout below is taken from Watlow's own
``WatbusAppLibrary`` (the managed half of the EZ-ZONE Configurator), so the
meaning of every byte is known. Earlier pywatlow releases were built from
captured traffic alone and got two details wrong (see `Differences from
pywatlow 0.1.x`_).

Frame
-----

Requests and replies share one frame layout::

    55 FF               preamble
    <type>              05 = request expecting a reply, 06 = reply
    <dst>               destination: zone = controller address + 15
                        (address 1 -> 10, address 16 -> 1F); the bus master is 00
    <src>               source address (00 from the master, the zone from the controller)
    <len hi> <len lo>   ADU length, big-endian
    <hdr check>         CRC-8 over bytes 2..6 (not the preamble); see
                        ``protocol.header_check_byte`` and the write-up at
                        https://reverseengineering.stackexchange.com/questions/8303
    <adu ...>           application data unit, <len> bytes
    <data check>        CRC-16 (poly 0x1021 reflected, init FFFF, xor-out FFFF)
                        over the ADU, sent little-endian

The length field is what makes a frame readable without knowing in advance
what it carries: read 8 bytes, check the header, then read ``len + 2`` more.

ADU
---

::

    request    : 01 <function> ...            01 = UnicastRequest
    reply      : 02 <function> ...            02 = UnicastResponse
    exception  : <type> <code>                <code> is 128..136, in the function slot

    ReadSingle  (03) request : 01 03 01 <class> <member> <instance>
                     reply   : 02 03 01 <class> <member> <instance> <repr> <value..>
    WriteSingle (04) request : 01 04 <class> <member> <instance> <repr> <value..>
                     reply   : 02 04 <class> <member> <instance> <repr> <value..>

A parameter id from the manual, ``CCMMM``, is split in decimal into the class
(leading one or two digits) and member (last three): 4001 is class 4 member
1, 26029 is class 26 member 29. The instance is the channel, 1 on single-loop
controllers.

Data representations
--------------------

``<repr>`` says how ``<value..>`` is encoded:

===== ========== ================================= =================================
code  name       in a write                        in a reply
===== ========== ================================= =================================
1     UByte      1 byte                            1 byte
2     Byte       1 byte, signed                    1 byte, signed
3     UWord      2 bytes big-endian                2 bytes big-endian
4     Word       2 bytes big-endian, signed        2 bytes big-endian, signed
5     ULong      4 bytes big-endian                4 bytes big-endian
6     Long       4 bytes big-endian, signed        4 bytes big-endian, signed
7     Enum       ``01 <v>`` (byte length, value)   ``<n> <v>...`` (entry count, n values)
8     Float      IEEE-754 big-endian               IEEE-754 big-endian
9     String     ``<len> <chars> 00``              ``<len> <chars> 00`` (len includes NUL)
10    List       ``02 <hi> <lo>``                  ``<n> <hi> <lo>...`` (n 2-byte entries)
15    WideEnum   ``02 <hi> <lo>``                  ``<n> <hi> <lo>...`` (n 2-byte entries)
===== ========== ================================= =================================

Note the asymmetry for enumerations: the byte after the representation is the
value's byte length in a write and the number of entries in a reply, so a
wide enum goes out as ``0F 02 hi lo`` and comes back as ``0F 01 hi lo``.

Every enumerated parameter in the PM manual ("uint" in its tables: heat
algorithm, units, ramp action, sensor type...) is a WideEnum. Floating point
parameters are Float.

Exceptions
----------

Instead of a reply the controller may answer with a two-byte ADU,
``<type> <code>``. The codes (``WatbusEnumerations``):

===== =====================
128   UnsupportedFunction
129   UnsupportedClass
130   UnsupportedSubcode
131   UnsupportedMember
132   UnsupportedInstance
133   UnsupportedAttribute
134   DataOutOfRange
135   CannotProcess
136   IllegalAccess
===== =====================

Captured examples (all 12-byte frames):

* ``55 FF 06 00 11 00 02 17 02 80 FF B8`` -- writing the read-only process
  value (4001) at address 2: UnsupportedFunction
* ``55 FF 06 00 10 00 02 8F 02 86 C9 DD`` -- writing Ramp Action (7014) = 1647
  to an EZ-ZONE PM4 that does not offer that choice: DataOutOfRange
* ``55 FF 06 00 10 00 02 8F 02 85 52 EF`` -- CannotProcess
* ``55 FF 06 00 10 00 02 8F 02 83 64 8A`` -- UnsupportedMember

Differences from pywatlow 0.1.x
--------------------------------

* **Enum writes** were sent as ``0F 01 hi lo``, the reply encoding, from bus
  address 03. Watlow's software sends ``0F 02 hi lo`` from address 00, and that
  is what this version sends. (The author's PM3 did acknowledge the old form,
  so some firmware tolerates it; the configurator's form is the one Watlow
  ships, and an EZ-ZONE PM4 has been verified to accept it.)
* **Replies were read by a guessed fixed length** (19, 20 or 21 bytes picked
  from the data type the caller passed). A 12-byte exception reply therefore
  looked like a timeout, and a wrong `data_type` left bytes in the port for
  the next exchange. Replies are now read by the length in their header, and
  exceptions are decoded.
* **Data types are no longer guessed from the frame length.** The reply's
  representation byte is decoded, so any representation can be read and the
  caller need not know the type in advance.

Captured examples
-----------------

The tables below are traffic the original author captured from a PM3. Byte
labels follow the layout above. The integer-write *requests* use the 0.1.x
``0F 01`` form, which that controller acknowledged; the replies are as any
controller sends them.

Read requests, float reply:

.. csv-table:: Example Messages
  :file: messages_read_float.csv
  :header-rows: 1

Read requests, wide-enum reply:

.. csv-table:: Example Messages
  :file: messages_read_int.csv
  :header-rows: 1

Write requests, float:

.. csv-table:: Example Messages
  :file: messages_set_float.csv
  :header-rows: 1

Write requests, wide enum (0.1.x request encoding):

.. csv-table:: Example Messages
  :file: messages_set_int.csv
  :header-rows: 1
