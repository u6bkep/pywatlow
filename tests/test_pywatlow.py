from binascii import unhexlify

import pytest

from pywatlow import protocol
from pywatlow.cli import main
from pywatlow.protocol import ExceptionCode
from pywatlow.protocol import InvalidResponse
from pywatlow.protocol import NoResponse
from pywatlow.protocol import ProtocolError
from pywatlow.protocol import Repr
from pywatlow.protocol import WatlowException
from pywatlow.watlow import Watlow


def test_main():
    assert main([]) == 0


def test_watlow():
    watlow = Watlow()
    assert watlow.address == 1


class TestCheckBytes:
    '''
    Every frame below was exchanged with a real controller.
    '''

    def test_data_check_bytes(self):
        test_data = {
            # Request, Address 1, '4001'
            '55ff0510000006e8010301040101e399': b'\xe3\x99',
            # Request, Address 2, '4001'
            '55ff051100000661010301040101e399': b'\xe3\x99',
            # Request, Address 2, '7001'
            '55ff0511000006610103010701018776': b'\x87\x76',
            # Responses (not necessarily from requests above)
            '55FF060010000B8802030104010108468F3638DD0E': b'\xdd\x0e',
            '55ff060010000b8802030104010108468f3abe4346': b'\x43\x46',
            '55ff060011000b1002030104010108468f393a07ae': b'\x07\xae',
            '55ff060011000b100203010701010842960000d3b0': b'\xd3\xb0',
            # Exception reply captured from an EZ-ZONE PM4 (DataOutOfRange)
            '55ff06001000028f0286c9dd': b'\xc9\xdd',
        }
        for hex_frame, expected in test_data.items():
            frame = unhexlify(hex_frame)
            assert protocol.data_check_bytes(frame[8:-2]) == expected, hex_frame

    def test_header_check_byte(self):
        test_data = {
            '55ff0510000006e8010301040101e399': 0xe8,  # Request, Address 1
            '55ff051100000661010301040101e399': 0x61,  # Request, Address 2
            '55ff051f000006160103010701018776': 0x16,  # Request, Address 16
            '55FF060010000B8802030104010108468F3638DD0E': 0x88,
            '55ff060011000b1002030104010108468f3c3c89b5': 0x10,
            '55ff06001000028f0286c9dd': 0x8f,
        }
        for hex_frame, expected in test_data.items():
            assert protocol.header_check_byte(unhexlify(hex_frame)[:7]) == expected, hex_frame

    def test_header_check_byte_needs_seven_bytes(self):
        with pytest.raises(ProtocolError):
            protocol.header_check_byte(b'\x55\xff\x05')


class TestParameterIds:

    @pytest.mark.parametrize('param, cls, member', [
        (4005, 4, 5), (4007, 4, 7), (4001, 4, 1), (7001, 7, 1), (8003, 8, 3),
        (7017, 7, 17), (4042, 4, 42), (26029, 26, 29), (26026, 26, 26),
        (26030, 26, 30), (34005, 34, 5), (34029, 34, 29), (6001, 6, 1),
    ])
    def test_split_and_join(self, param, cls, member):
        assert protocol.split_param(param) == (cls, member)
        assert protocol.split_param(str(param)) == (cls, member)
        assert protocol.join_param(cls, member) == param

    def test_split_rejects_out_of_range(self):
        with pytest.raises(ProtocolError):
            protocol.split_param(100000)
        with pytest.raises(ProtocolError):
            protocol.split_param(4999)  # member 999 does not fit a byte


class TestRequests:

    @pytest.mark.parametrize('param, address, instance, expected', [
        # Verified against a real controller by the original author.
        ('4001', 1, '01', '55ff0510000006e8010301040101e399'),  # Process Value
        ('4002', 1, '01', '55ff0510000006e80103010402018bb3'),
        ('7001', 1, '01', '55ff0510000006e80103010701018776'),  # Set point
        ('4001', 2, '01', '55ff051100000661010301040101e399'),
        ('7001', 2, '01', '55ff0511000006610103010701018776'),
        ('4001', 11, '01', '55ff051a000006bd010301040101e399'),
        ('7001', 11, '01', '55ff051a000006bd0103010701018776'),
        ('4001', 16, '01', '55ff051f00000616010301040101e399'),
        ('7001', 16, '01', '55ff051f000006160103010701018776'),
        (4001, 2, 1, '55ff051100000661010301040101e399'),
        (4005, 1, '01', '55FF0510000006E801030104050183FE'),  # Sensor Type
        (4042, 1, '01', '55FF0510000006E8010301042A01785E'),  # Units
        (4012, 1, '01', '55FF0510000006E8010301040C019B29'),  # Calibration offset
        (34005, 1, '01', '55FF0510000006E8010301220501612B'),  # Linearization function
        (26029, 1, '01', '55FF0510000006E80103011A1D015C30'),  # Altitude Units
        (8003, 1, '01', '55FF0510000006E8010301080301F00F'),  # Heat Algorithm
        (6001, 1, '01', '55FF0510000006E80103010601015B2C'),  # Digital I/O Direction
    ])
    def test_read_request(self, param, address, instance, expected):
        assert protocol.build_read_request(address, param, instance) == unhexlify(expected)

    @pytest.mark.parametrize('param, value, address, instance, expected', [
        # Verified against a real controller by the original author.
        (7001, 81, 1, '01', '55ff051000000aec01040701010842a20000c4b8'),
        ('7001', 81.0, 1, '01', '55ff051000000aec01040701010842a20000c4b8'),
        (7001, 78.5, 1, '01', '55ff051000000aec010407010108429d0000ad74'),
        (7001, 80, 2, '01', '55FF051100000A6501040701010842A000007C0D'),
        (7001, 78.5, 16, '01', '55ff051f00000a12010407010108429d0000ad74'),
        (4016, 20.0, 2, '01', '55FF051100000A6501040410010841A000007D88'),  # Scale High
        (4018, 9999.0, 2, '01', '55FF051100000A65010404120108461C3C0004D8'),  # Range High
        (4014, 0.5, 2, '01', '55FF051100000A650104040E01083F0000004540'),  # Filter
        (26030, 14.7, 2, '01', '55FF051100000A6501041A1E0108416B3333C7D9'),  # Barometric Pressure
    ])
    def test_write_float_request(self, param, value, address, instance, expected):
        request = protocol.build_write_request(address, param, float, value, instance)
        assert request == unhexlify(expected)

    def test_write_wide_enum_request(self):
        '''
        The configurator writes a wide enum as ``0F 02 <hi> <lo>``: the byte
        after the representation is the value's byte length. pywatlow 0.1.x
        sent the reply-style entry count (``0F 01``) instead, from the bus
        master address 03 rather than 00.
        '''
        # Ramp Action (7014) = 1647 at address 1. Independently derived vector
        # (Raven furnace controller codec, verified against the PM4).
        request = protocol.build_write_request(1, 7014, int, 1647, 1)
        assert request[:7] == unhexlify('55ff05100000' + '09')
        assert request[7] == protocol.header_check_byte(request[:7])
        assert request[8:17] == unhexlify('0104070e010f02066f')
        assert request[17:] == protocol.data_check_bytes(request[8:17])
        assert len(request) == 19

    @pytest.mark.parametrize('param, value, address, adu', [
        # ADUs of the original author's int-write vectors, re-encoded with the
        # configurator's count byte.
        (8003, 71, 1, '01040803010f020047'),  # Heat Algorithm = PID
        (8003, 62, 1, '01040803010f02003e'),
        (4005, 95, 2, '01040405010f02005f'),  # Sensor Type
        (4042, 75, 2, '0104042a010f02004b'),  # Units
        (4037, 1449, 2, '01040425010f0205a9'),  # Thermistor resistance range
        (34029, 1539, 2, '0104221d010f020603'),  # Linearization Units
        (26028, 1671, 2, '01041a1c010f020687'),  # Pressure Units
    ])
    def test_write_wide_enum_adu(self, param, value, address, adu):
        request = protocol.build_write_request(address, param, int, value)
        assert request[3] == address + 15
        assert request[4] == protocol.MASTER_ADDRESS
        assert request[5:7] == b'\x00\x09'
        assert request[8:-2] == unhexlify(adu)

    def test_write_other_representations(self):
        assert protocol.encode_value(Repr.ENUM, 71) == b'\x01\x47'
        assert protocol.encode_value(Repr.WIDE_ENUM, 1647) == b'\x02\x06\x6f'
        assert protocol.encode_value(Repr.LIST, 300) == b'\x02\x01\x2c'
        assert protocol.encode_value(Repr.UBYTE, 200) == b'\xc8'
        assert protocol.encode_value(Repr.BYTE, -2) == b'\xfe'
        assert protocol.encode_value(Repr.UWORD, 0x1234) == b'\x12\x34'
        assert protocol.encode_value(Repr.WORD, -1) == b'\xff\xff'
        assert protocol.encode_value(Repr.ULONG, 0x01020304) == b'\x01\x02\x03\x04'
        assert protocol.encode_value(Repr.LONG, -2) == b'\xff\xff\xff\xfe'
        assert protocol.encode_value(Repr.FLOAT, 350.0) == b'\x43\xaf\x00\x00'
        assert protocol.encode_value(Repr.STRING, 'AB') == b'\x02AB\x00'

    def test_write_rejects_bad_values(self):
        with pytest.raises(ProtocolError):
            protocol.encode_value(Repr.UBYTE, 300)
        with pytest.raises(ProtocolError):
            protocol.encode_value(Repr.WIDE_ENUM, -1)
        with pytest.raises(ProtocolError):
            protocol.encode_value(Repr.EVENT, 1)

    def test_as_repr(self):
        assert protocol.as_repr(float) is Repr.FLOAT
        assert protocol.as_repr(int) is Repr.WIDE_ENUM
        assert protocol.as_repr(str) is Repr.STRING
        assert protocol.as_repr(Repr.ENUM) is Repr.ENUM
        assert protocol.as_repr(7) is Repr.ENUM
        with pytest.raises(ProtocolError):
            protocol.as_repr(bytes)


class TestReplies:

    @pytest.mark.parametrize('frame, address, param, value, repr_', [
        # Actual responses received by the original author.
        ('55FF06031100097702040803010F010047883B', 2, 8003, 71, Repr.WIDE_ENUM),  # write ack
        ('55FF060011000AEE02040701010842A000001579', 2, 7001, 80.0, Repr.FLOAT),  # write ack
        ('55ff06001f000a7702040701010842a20000adcc', 16, 7001, 81.0, Repr.FLOAT),  # write ack
        ('55FF060011000B1002030104010108451E40B2F377', 2, 4001, 2532.04345703125, Repr.FLOAT),  # read
        ('55ff060011000b100203010701010842960000d3b0', 2, 7001, 75.0, Repr.FLOAT),  # read
        ('55FF060010000A760203010803010F010047C56B', 1, 8003, 71, Repr.WIDE_ENUM),  # read
        ('55FF060011000AEE0203010425010F0105A90D37', 2, 4037, 1449, Repr.WIDE_ENUM),  # read
    ])
    def test_parse_reply(self, frame, address, param, value, repr_):
        reply = protocol.parse_reply(unhexlify(frame), address)
        assert reply.param == param
        assert reply.instance == 1
        assert reply.repr is repr_
        assert reply.value == value

    def test_exception_replies(self):
        # Original author: writing a read-only parameter
        with pytest.raises(WatlowException) as e:
            protocol.parse_reply(unhexlify('55FF0600110002170280FFB8'), 2)
        assert e.value.code is ExceptionCode.UNSUPPORTED_FUNCTION
        # PM4 refusing Ramp Action = 1647 (captured 2026-10-15)
        with pytest.raises(WatlowException) as e:
            protocol.parse_reply(unhexlify('55ff06001000028f0286c9dd'), 1)
        assert e.value.code is ExceptionCode.DATA_OUT_OF_RANGE
        assert 'DATA_OUT_OF_RANGE' in str(e.value)

    def test_wrong_address(self):
        with pytest.raises(InvalidResponse):
            protocol.parse_reply(unhexlify('55FF06031100097702040803010F010047883B'), 1)

    def test_bad_checks(self):
        with pytest.raises(InvalidResponse):  # data check
            protocol.parse_reply(unhexlify('55ff060010000b8802030104010108468f3abe4356'), 1)
        with pytest.raises(InvalidResponse):  # header check
            protocol.parse_reply(unhexlify('55FF060010000B8902030104010108468F3638DD0E'), 1)
        with pytest.raises(InvalidResponse):  # preamble
            protocol.parse_reply(unhexlify('56FF060010000B8802030104010108468F3638DD0E'), 1)

    def test_truncated(self):
        with pytest.raises(ProtocolError):
            protocol.parse_reply(unhexlify('55FF060010000B8802030104010108468F36'), 1)
        with pytest.raises(ProtocolError):
            protocol.parse_frame(b'\x55\xff\x06')

    def test_request_is_not_a_reply(self):
        with pytest.raises(InvalidResponse):
            protocol.parse_reply(unhexlify('55ff0510000006e8010301040101e399'), 1)

    def test_frame_address(self):
        frame = protocol.parse_frame(unhexlify('55ff0510000006e8010301040101e399'))
        assert frame.frame_type == protocol.FRAME_TYPE_REQUEST
        assert frame.address == 1
        frame = protocol.parse_frame(unhexlify('55ff06001f000a7702040701010842a20000adcc'))
        assert frame.frame_type == protocol.FRAME_TYPE_REPLY
        assert frame.address == 16

    def test_decode_value_all_representations(self):
        assert protocol.decode_value(b'\x01\xc8') == (Repr.UBYTE, 200, 2)
        assert protocol.decode_value(b'\x02\xfe') == (Repr.BYTE, -2, 2)
        assert protocol.decode_value(b'\x03\x12\x34') == (Repr.UWORD, 0x1234, 3)
        assert protocol.decode_value(b'\x04\xff\xff') == (Repr.WORD, -1, 3)
        assert protocol.decode_value(b'\x05\x01\x02\x03\x04') == (Repr.ULONG, 0x01020304, 5)
        assert protocol.decode_value(b'\x06\xff\xff\xff\xfe') == (Repr.LONG, -2, 5)
        assert protocol.decode_value(b'\x08\x43\xaf\x00\x00') == (Repr.FLOAT, 350.0, 5)
        assert protocol.decode_value(b'\x07\x01\x47') == (Repr.ENUM, 71, 3)
        assert protocol.decode_value(b'\x07\x02\x47\x3e') == (Repr.ENUM, (71, 62), 4)
        assert protocol.decode_value(b'\x0f\x01\x06\x6f') == (Repr.WIDE_ENUM, 1647, 4)
        assert protocol.decode_value(b'\x0f\x02\x00\x3e\x00\x58') == (Repr.WIDE_ENUM, (62, 88), 6)
        assert protocol.decode_value(b'\x0a\x01\x01\x2c') == (Repr.LIST, 300, 4)
        # String count includes the trailing NUL (GetListLength case 9)
        assert protocol.decode_value(b'\x09\x03AB\x00') == (Repr.STRING, 'AB', 5)

    def test_decode_value_errors(self):
        with pytest.raises(ProtocolError):
            protocol.decode_value(b'')
        with pytest.raises(ProtocolError):
            protocol.decode_value(b'\x08\x43\xaf')
        with pytest.raises(ProtocolError):
            protocol.decode_value(b'\x0f\x02\x00\x3e')
        with pytest.raises(ProtocolError):
            protocol.decode_value(b'\x0b')
        with pytest.raises(ProtocolError):
            protocol.decode_value(b'\x63\x00')


class FakeSerial:
    '''
    A serial port that answers each write with the next queued frame.
    '''
    port = 'FAKE'

    def __init__(self, *replies):
        self.replies = [unhexlify(r) if isinstance(r, str) else r for r in replies]
        self.writes = []
        self.pending = b''

    def reset_input_buffer(self):
        self.pending = b''

    def write(self, data):
        self.writes.append(bytes(data))
        self.pending = self.replies.pop(0) if self.replies else b''

    def read(self, n):
        out, self.pending = self.pending[:n], self.pending[n:]
        return out


class TestWatlow:

    def test_read(self):
        port = FakeSerial('55FF060011000B1002030104010108451E40B2F377')
        result = Watlow(serial=port, address=2).read()
        assert port.writes == [unhexlify('55ff051100000661010301040101e399')]
        assert result == {'address': 2, 'param': 4001, 'data': 2532.04345703125,
                          'repr': Repr.FLOAT, 'error': None}

    def test_read_ignores_legacy_data_type(self):
        port = FakeSerial('55FF060011000B1002030104010108451E40B2F377')
        result = Watlow(serial=port, address=2).readParam(4001, int)
        assert result['data'] == 2532.04345703125

    def test_write_setpoint(self):
        port = FakeSerial('55FF060011000AEE02040701010842A000001579')
        result = Watlow(serial=port, address=2).write(80)
        assert port.writes == [unhexlify('55FF051100000A6501040701010842A000007C0D')]
        assert result['param'] == 7001
        assert result['data'] == 80.0
        assert result['error'] is None

    def test_write_enum_with_explicit_type(self):
        # Ack carries the reply-style entry count; request carries the byte length.
        port = FakeSerial('55FF06031100097702040803010F010047883B')
        result = Watlow(serial=port, address=2).writeParam(8003, 71, int)
        assert port.writes[0][8:-2] == unhexlify('01040803010f020047')
        assert result['data'] == 71
        assert result['repr'] is Repr.WIDE_ENUM
        assert result['error'] is None

    def test_write_discovers_type_by_reading_first(self):
        # Read reply says 8003 is a wide enum holding 62; then the write ack.
        read_reply = protocol.build_frame(
            2, unhexlify('02030108030' + '10f01003e'), protocol.FRAME_TYPE_REPLY, src=0x11)
        port = FakeSerial(read_reply, '55FF06031100097702040803010F010047883B')
        result = Watlow(serial=port, address=2).writeParam(8003, 71)
        assert len(port.writes) == 2
        assert port.writes[0][8:-2] == unhexlify('010301080301')
        assert port.writes[1][8:-2] == unhexlify('01040803010f020047')
        assert result['data'] == 71

    def test_write_discovery_failure_is_reported(self):
        port = FakeSerial(b'')
        result = Watlow(serial=port, address=2).writeParam(8003, 71)
        assert isinstance(result['error'], NoResponse)
        assert len(port.writes) == 1

    def test_controller_exception(self):
        port = FakeSerial('55ff06001000028f0286c9dd')
        result = Watlow(serial=port, address=1).writeParam(7014, 1647, int)
        assert result['data'] is None
        assert isinstance(result['error'], WatlowException)
        assert result['error'].code is ExceptionCode.DATA_OUT_OF_RANGE

    def test_no_response(self):
        port = FakeSerial(b'')
        result = Watlow(serial=port, address=2).read()
        assert result == {'address': 2, 'param': 4001, 'data': None, 'repr': None,
                          'error': result['error']}
        assert isinstance(result['error'], NoResponse)

    def test_truncated_response(self):
        port = FakeSerial('55FF060011000B1002030104010108451E')
        result = Watlow(serial=port, address=2).read()
        assert isinstance(result['error'], InvalidResponse)

    def test_reply_from_wrong_address(self):
        port = FakeSerial('55FF060011000B1002030104010108451E40B2F377')
        result = Watlow(serial=port, address=1).read()
        assert isinstance(result['error'], InvalidResponse)

    def test_bad_data_type(self):
        port = FakeSerial()
        result = Watlow(serial=port, address=1).writeParam(7001, 1, bytes)
        assert isinstance(result['error'], ProtocolError)
        assert port.writes == []

    def test_value_out_of_range_for_type(self):
        port = FakeSerial()
        result = Watlow(serial=port, address=1).writeParam(7014, 70000, int)
        assert isinstance(result['error'], ProtocolError)
        assert port.writes == []

    def test_frame_read_is_length_driven(self):
        # A 12-byte exception followed by an unrelated frame: only the first is consumed.
        port = FakeSerial(unhexlify('55ff06001000028f0286c9dd') + b'\x55\xff\x06')
        result = Watlow(serial=port, address=1).read()
        assert isinstance(result['error'], WatlowException)
        assert port.pending == b'\x55\xff\x06'
