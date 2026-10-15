"""
Watlow Standard Bus wire codec: framing, check bytes, requests and replies.

Standard Bus is Watlow's proprietary EIA-485 protocol (a BACnet MS/TP
variant). It is always present on EZ-ZONE PM/RM controllers. This module is
pure Python with no I/O; :class:`pywatlow.watlow.Watlow` drives a serial port
with it.

The payload layout follows Watlow's own ``WatbusAppLibrary`` (the managed
half of the EZ-ZONE Configurator) rather than the earlier reverse-engineered
guesses, so every data representation the controllers use is encoded the way
Watlow's software encodes it.

Frame layout (requests and replies share it)::

    55 FF               MS/TP preamble
    <type>              05 = request expecting a reply, 06 = reply
    <dst>               zone = controller address + 15 (address 1 -> 0x10);
                        the bus master is 0x00
    <src>               sender's address
    <len hi> <len lo>   ADU length, big-endian
    <hdr check>         CRC-8 over header bytes 2..6 (see header_check_byte)
    <adu ...>           application data unit, <len> bytes
    <data check>        CRC-16 over the ADU, little-endian (see data_check_bytes)

ADU layout::

    request    : 01 <function> ...               01 = UnicastRequest
    reply      : 02 <function> ...               02 = UnicastResponse
    exception  : <type> <code 128..136>          see ExceptionCode
    ReadSingle (03) : 01 03 01 <class> <member> <instance>
              reply : 02 03 01 <class> <member> <instance> <repr> <value..>
    WriteSingle(04) : 01 04 <class> <member> <instance> <repr> <value..>
              reply : 02 04 <class> <member> <instance> <repr> <value..>

``<repr>`` is a :class:`Repr` code and fixes how ``<value..>`` is encoded.
Writes and replies encode enumerations differently: in a write the byte after
the representation is the value's *byte length* (1 for Enum, 2 for WideEnum);
in a reply it is the *number of entries* in the list.
"""
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any
from typing import Union

PREAMBLE = b'\x55\xff'
FRAME_TYPE_REQUEST = 0x05
FRAME_TYPE_REPLY = 0x06
MASTER_ADDRESS = 0x00
#: Bytes in a frame before the ADU (preamble through the header check byte).
HEADER_LEN = 8
#: Bytes in the data check that follow the ADU.
DATA_CHECK_LEN = 2

ADU_UNICAST_REQUEST = 0x01
ADU_UNICAST_RESPONSE = 0x02
FUNCTION_READ_SINGLE = 0x03
FUNCTION_WRITE_SINGLE = 0x04
#: The "read type" byte that follows the function code in a ReadSingle.
READ_TYPE_VALUE = 0x01


class Repr(IntEnum):
    """Data representation codes (``WatbusEnumerations.DataRepresentation``)."""
    UBYTE = 1
    BYTE = 2
    UWORD = 3
    WORD = 4
    ULONG = 5
    LONG = 6
    #: Enumeration with 1-byte values.
    ENUM = 7
    FLOAT = 8
    STRING = 9
    #: List of 2-byte values.
    LIST = 10
    EVENT = 11
    PARAMETER = 12
    #: Enumeration with 2-byte values. Every enum parameter in the PM manual
    #: (heat algorithm, ramp action, units, ...) uses this one.
    WIDE_ENUM = 15


class ExceptionCode(IntEnum):
    """Codes a controller returns instead of a reply."""
    UNSUPPORTED_FUNCTION = 128
    UNSUPPORTED_CLASS = 129
    UNSUPPORTED_SUBCODE = 130
    UNSUPPORTED_MEMBER = 131
    UNSUPPORTED_INSTANCE = 132
    UNSUPPORTED_ATTRIBUTE = 133
    DATA_OUT_OF_RANGE = 134
    CANNOT_PROCESS = 135
    ILLEGAL_ACCESS = 136


class WatlowError(Exception):
    """Base class for everything this package raises or reports."""


class ProtocolError(WatlowError):
    """A frame could not be built or parsed."""


class NoResponse(WatlowError):
    """The controller did not answer within the timeout."""


class InvalidResponse(ProtocolError):
    """The reply failed a check byte or came from the wrong address."""


class WatlowException(WatlowError):
    """The controller answered with an exception instead of a reply.

    * **code**: the :class:`ExceptionCode` (or raw int if unknown)
    """
    def __init__(self, code):
        try:
            code = ExceptionCode(code)
            name = code.name
        except ValueError:
            name = 'Unknown'
        self.code = code
        super().__init__('controller exception {0} ({1})'.format(int(code), name))


# ---------------------------------------------------------------------------
# Check bytes
# ---------------------------------------------------------------------------

_CRC8_TABLE = [
    0x00, 0xfe, 0xff, 0x01, 0xfd, 0x03, 0x02, 0xfc, 0xf9, 0x07, 0x06, 0xf8, 0x04, 0xfa, 0xfb, 0x05,
    0xf1, 0x0f, 0x0e, 0xf0, 0x0c, 0xf2, 0xf3, 0x0d, 0x08, 0xf6, 0xf7, 0x09, 0xf5, 0x0b, 0x0a, 0xf4,
    0xe1, 0x1f, 0x1e, 0xe0, 0x1c, 0xe2, 0xe3, 0x1d, 0x18, 0xe6, 0xe7, 0x19, 0xe5, 0x1b, 0x1a, 0xe4,
    0x10, 0xee, 0xef, 0x11, 0xed, 0x13, 0x12, 0xec, 0xe9, 0x17, 0x16, 0xe8, 0x14, 0xea, 0xeb, 0x15,
    0xc1, 0x3f, 0x3e, 0xc0, 0x3c, 0xc2, 0xc3, 0x3d, 0x38, 0xc6, 0xc7, 0x39, 0xc5, 0x3b, 0x3a, 0xc4,
    0x30, 0xce, 0xcf, 0x31, 0xcd, 0x33, 0x32, 0xcc, 0xc9, 0x37, 0x36, 0xc8, 0x34, 0xca, 0xcb, 0x35,
    0x20, 0xde, 0xdf, 0x21, 0xdd, 0x23, 0x22, 0xdc, 0xd9, 0x27, 0x26, 0xd8, 0x24, 0xda, 0xdb, 0x25,
    0xd1, 0x2f, 0x2e, 0xd0, 0x2c, 0xd2, 0xd3, 0x2d, 0x28, 0xd6, 0xd7, 0x29, 0xd5, 0x2b, 0x2a, 0xd4,
    0x81, 0x7f, 0x7e, 0x80, 0x7c, 0x82, 0x83, 0x7d, 0x78, 0x86, 0x87, 0x79, 0x85, 0x7b, 0x7a, 0x84,
    0x70, 0x8e, 0x8f, 0x71, 0x8d, 0x73, 0x72, 0x8c, 0x89, 0x77, 0x76, 0x88, 0x74, 0x8a, 0x8b, 0x75,
    0x60, 0x9e, 0x9f, 0x61, 0x9d, 0x63, 0x62, 0x9c, 0x99, 0x67, 0x66, 0x98, 0x64, 0x9a, 0x9b, 0x65,
    0x91, 0x6f, 0x6e, 0x90, 0x6c, 0x92, 0x93, 0x6d, 0x68, 0x96, 0x97, 0x69, 0x95, 0x6b, 0x6a, 0x94,
    0x40, 0xbe, 0xbf, 0x41, 0xbd, 0x43, 0x42, 0xbc, 0xb9, 0x47, 0x46, 0xb8, 0x44, 0xba, 0xbb, 0x45,
    0xb1, 0x4f, 0x4e, 0xb0, 0x4c, 0xb2, 0xb3, 0x4d, 0x48, 0xb6, 0xb7, 0x49, 0xb5, 0x4b, 0x4a, 0xb4,
    0xa1, 0x5f, 0x5e, 0xa0, 0x5c, 0xa2, 0xa3, 0x5d, 0x58, 0xa6, 0xa7, 0x59, 0xa5, 0x5b, 0x5a, 0xa4,
    0x50, 0xae, 0xaf, 0x51, 0xad, 0x53, 0x52, 0xac, 0xa9, 0x57, 0x56, 0xa8, 0x54, 0xaa, 0xab, 0x55,
]


def header_check_byte(header):
    """CRC-8 of the first seven frame bytes (preamble through length).

    Only bytes 2..6 enter the calculation; the preamble is skipped. The
    algorithm is the one worked out at
    https://reverseengineering.stackexchange.com/questions/8303 and matches
    every frame captured from real controllers.
    """
    if len(header) < 7:
        raise ProtocolError('header needs 7 bytes, got {0}'.format(len(header)))
    crc = _CRC8_TABLE[(~header[2]) & 0xff]
    for b in header[3:7]:
        crc = _CRC8_TABLE[b ^ crc]
    return (~crc) & 0xff


def _crc16_x25(data):
    # CRC-16 poly 0x1021 reflected (0x8408), init 0xFFFF, xor-out 0xFFFF:
    # the BACnet MS/TP data CRC.
    crc = 0xffff
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xffff


def data_check_bytes(adu):
    """CRC-16 of the ADU as it appears after it on the wire (little-endian)."""
    return struct.pack('<H', _crc16_x25(bytes(adu)))


# ---------------------------------------------------------------------------
# Parameter ids
# ---------------------------------------------------------------------------

def split_param(param):
    """Parameter id from the manual -> ``(class, member)`` wire bytes.

    The manual's four or five digit ids are ``CCMMM``: the class is the
    leading one or two digits and the member the last three, both in decimal
    (``4001`` -> ``(4, 1)``, ``26029`` -> ``(26, 29)``, ``7017`` -> ``(7, 17)``).
    """
    param = int(param)
    if not 0 <= param <= 99999:
        raise ProtocolError('parameter id {0} out of range'.format(param))
    cls, member = divmod(param, 1000)
    if cls > 255 or member > 255:
        raise ProtocolError('parameter id {0} does not fit the wire format'.format(param))
    return cls, member


def join_param(cls, member):
    """Inverse of :func:`split_param`."""
    return cls * 1000 + member


def _instance_byte(instance):
    # Accept the historical two-character string ('01') as well as an int.
    if isinstance(instance, str):
        instance = int(instance, 10)
    if not 0 <= instance <= 255:
        raise ProtocolError('instance {0} out of range'.format(instance))
    return instance


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

_INT_FORMATS = {
    Repr.UBYTE: '>B', Repr.BYTE: '>b',
    Repr.UWORD: '>H', Repr.WORD: '>h',
    Repr.ULONG: '>I', Repr.LONG: '>i',
}


def encode_value(repr_, value):
    """Encode ``value`` the way a WriteSingle carries it (without the repr byte).

    Follows ``EditSettingsOnLine.UIWriteSingleMemberValue`` in the configurator:

    * integers: raw big-endian, no count byte
    * ``FLOAT``: IEEE-754 big-endian
    * ``ENUM``: ``01 <value>`` (byte length, then the value)
    * ``WIDE_ENUM`` / ``LIST``: ``02 <hi> <lo>``
    * ``STRING``: ``<len> <chars> 00``
    """
    repr_ = Repr(repr_)
    try:
        if repr_ in _INT_FORMATS:
            return struct.pack(_INT_FORMATS[repr_], int(value))
        if repr_ is Repr.FLOAT:
            return struct.pack('>f', float(value))
        if repr_ is Repr.ENUM:
            return struct.pack('>BB', 1, int(value))
        if repr_ in (Repr.WIDE_ENUM, Repr.LIST):
            return struct.pack('>BH', 2, int(value))
        if repr_ is Repr.STRING:
            raw = value.encode('ascii') if isinstance(value, str) else bytes(value)
            return struct.pack('>B', len(raw)) + raw + b'\x00'
    except (struct.error, OverflowError, UnicodeEncodeError) as e:
        raise ProtocolError('{0!r} is not a valid {1} value: {2}'.format(value, repr_.name, e))
    raise ProtocolError('cannot write a {0} value'.format(repr_.name))


def decode_value(payload):
    """Decode ``<repr> <value..>`` from a reply.

    Returns ``(repr, value, consumed_bytes)``. Enumerations and lists decode
    to an ``int`` when they hold one entry and to a ``tuple`` of ints
    otherwise. Strings decode to ``str`` with the trailing NUL removed. The
    list-length rules are ``WatbusAPI.GetListLength`` in the configurator.
    """
    if not payload:
        raise ProtocolError('reply has no value')
    try:
        repr_ = Repr(payload[0])
    except ValueError:
        raise ProtocolError('unsupported representation {0}'.format(payload[0]))
    body = payload[1:]
    try:
        if repr_ in _INT_FORMATS:
            fmt = _INT_FORMATS[repr_]
            n = struct.calcsize(fmt)
            return repr_, struct.unpack(fmt, body[:n])[0], 1 + n
        if repr_ is Repr.FLOAT:
            return repr_, struct.unpack('>f', body[:4])[0], 5
        if repr_ in (Repr.ENUM, Repr.WIDE_ENUM, Repr.LIST, Repr.STRING):
            count = body[0]
            width = 1 if repr_ in (Repr.ENUM, Repr.STRING) else 2
            raw = body[1:1 + count * width]
            if len(raw) != count * width:
                raise struct.error('short list')
            consumed = 2 + count * width
            if repr_ is Repr.STRING:
                return repr_, raw.rstrip(b'\x00').decode('ascii', 'replace'), consumed
            fmt = '>{0}{1}'.format(count, 'B' if width == 1 else 'H')
            entries = struct.unpack(fmt, raw)
            return repr_, (entries[0] if count == 1 else entries), consumed
    except (struct.error, IndexError):
        raise ProtocolError('reply value truncated ({0})'.format(repr_.name))
    raise ProtocolError('cannot decode a {0} value'.format(repr_.name))


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def zone(address):
    """Controller address (1..16 on the setup menu) -> MS/TP destination byte."""
    address = int(address)
    if not 1 <= address <= 240:
        raise ProtocolError('address {0} out of range'.format(address))
    return address + 15


def build_frame(address, adu, frame_type=FRAME_TYPE_REQUEST, src=MASTER_ADDRESS):
    """Wrap an ADU in a complete frame addressed to ``address``."""
    adu = bytes(adu)
    header = PREAMBLE + bytes([frame_type, zone(address), src]) + struct.pack('>H', len(adu))
    return header + bytes([header_check_byte(header)]) + adu + data_check_bytes(adu)


def build_read_request(address, param, instance=1):
    """ReadSingle request for ``param`` at ``address``."""
    cls, member = split_param(param)
    adu = bytes([ADU_UNICAST_REQUEST, FUNCTION_READ_SINGLE, READ_TYPE_VALUE,
                 cls, member, _instance_byte(instance)])
    return build_frame(address, adu)


def build_write_request(address, param, repr_, value, instance=1):
    """WriteSingle request setting ``param`` to ``value`` encoded as ``repr_``.

    ``repr_`` is anything :func:`as_repr` accepts (``float``, ``int``, ``str``
    or a :class:`Repr`).
    """
    cls, member = split_param(param)
    repr_ = as_repr(repr_)
    adu = bytes([ADU_UNICAST_REQUEST, FUNCTION_WRITE_SINGLE, cls, member,
                 _instance_byte(instance), int(repr_)]) + encode_value(repr_, value)
    return build_frame(address, adu)


def header_adu_len(header):
    """ADU length announced by a frame header (the first 8 bytes)."""
    if len(header) < HEADER_LEN:
        raise ProtocolError('header truncated ({0} bytes)'.format(len(header)))
    if header[:2] != PREAMBLE:
        raise InvalidResponse('bad preamble {0}'.format(header[:2].hex()))
    if header[7] != header_check_byte(header):
        raise InvalidResponse('header check mismatch')
    return struct.unpack('>H', header[5:7])[0]


@dataclass
class Frame:
    """A checked frame split into its parts."""
    frame_type: int
    dst: int
    src: int
    adu: bytes

    @property
    def address(self):
        """Controller address this frame came from (replies) or went to (requests)."""
        peer = self.src if self.frame_type == FRAME_TYPE_REPLY else self.dst
        return peer - 15


def parse_frame(data):
    """Split and check a complete frame. Raises :class:`InvalidResponse`."""
    data = bytes(data)
    adu_len = header_adu_len(data)
    end = HEADER_LEN + adu_len
    if len(data) < end + DATA_CHECK_LEN:
        raise ProtocolError('frame truncated: header announces {0} ADU bytes, have {1}'.format(
            adu_len, len(data) - HEADER_LEN))
    adu = data[HEADER_LEN:end]
    if data[end:end + DATA_CHECK_LEN] != data_check_bytes(adu):
        raise InvalidResponse('data check mismatch')
    return Frame(data[2], data[3], data[4], adu)


@dataclass
class Reply:
    """A decoded ReadSingle or WriteSingle reply."""
    function: int
    param: int
    instance: int
    repr: Repr
    value: Any


def decode_reply(adu):
    """Decode a reply ADU. Raises :class:`WatlowException` for exception ADUs."""
    adu = bytes(adu)
    if len(adu) < 2:
        raise ProtocolError('reply ADU too short')
    if adu[1] >= 128:
        raise WatlowException(adu[1])
    if adu[0] != ADU_UNICAST_RESPONSE:
        raise ProtocolError('unexpected ADU type {0:#04x}'.format(adu[0]))
    function = adu[1]
    if function == FUNCTION_READ_SINGLE:
        if len(adu) < 7 or adu[2] != READ_TYPE_VALUE:
            raise ProtocolError('malformed ReadSingle reply')
        cls, member, instance = adu[3], adu[4], adu[5]
        payload = adu[6:]
    elif function == FUNCTION_WRITE_SINGLE:
        if len(adu) < 6:
            raise ProtocolError('malformed WriteSingle reply')
        cls, member, instance = adu[2], adu[3], adu[4]
        payload = adu[5:]
    else:
        raise ProtocolError('unsupported function {0:#04x} in reply'.format(function))
    repr_, value, _ = decode_value(payload)
    return Reply(function, join_param(cls, member), instance, repr_, value)


def parse_reply(data, address=None):
    """Check a reply frame and decode it.

    * **address**: when given, the reply must come from this controller.

    Raises :class:`InvalidResponse`, :class:`ProtocolError` or
    :class:`WatlowException`.
    """
    frame = parse_frame(data)
    if frame.frame_type != FRAME_TYPE_REPLY:
        raise InvalidResponse('not a reply (type {0:#04x})'.format(frame.frame_type))
    if address is not None and frame.address != int(address):
        raise InvalidResponse('reply from address {0}, expected {1}'.format(frame.address, address))
    return decode_reply(frame.adu)


#: Python types accepted as a shorthand for a representation when writing.
#: ``int`` means ``WIDE_ENUM`` because that is what every integer-looking
#: parameter in the PM manual (and every earlier pywatlow release) uses.
TYPE_REPRS = {float: Repr.FLOAT, int: Repr.WIDE_ENUM, str: Repr.STRING}

ReprLike = Union[Repr, int, type, None]


def as_repr(data_type):
    """Map ``float``/``int``/``str``, a :class:`Repr` or its int code to a :class:`Repr`."""
    if isinstance(data_type, Repr):
        return data_type
    if data_type in TYPE_REPRS:
        return TYPE_REPRS[data_type]
    try:
        return Repr(data_type)
    except ValueError:
        raise ProtocolError('unknown data type {0!r}'.format(data_type))
