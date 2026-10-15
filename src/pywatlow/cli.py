"""
Module that contains the command line app.

Why does this file exist, and why not put this in __main__?

  You might be tempted to import things from __main__ later, but that will cause
  problems: the code will get executed twice:

  - When you run `python -mpywatlow` python will execute
    ``__main__.py`` as a script. That means there won't be any
    ``pywatlow.__main__`` in ``sys.modules``.
  - When you import __main__ it will get executed again (as a module) because
    there's no ``pywatlow.__main__`` in ``sys.modules``.

  Also see (1) from http://click.pocoo.org/5/setuptools/#setuptools-integration
"""
import argparse

from pywatlow.protocol import Repr
from pywatlow.watlow import Watlow

parser = argparse.ArgumentParser(description='A Python driver for Watlow EZ-ZONE temperature controllers')
group = parser.add_mutually_exclusive_group()
group.add_argument('-r', '--read', metavar=('PORT', 'ADDR', 'PARAM'), nargs=3,
                   help='Read a Watlow parameter. Specify the port, RS485 address, and parameter id '
                        '(e.g. "4001" for the process value, "7001" for the set point, "8003" for the '
                        'heat algorithm). Parameter ids are listed in the Watlow user manual')
group.add_argument('-w', '--write', metavar=('PORT', 'ADDR', 'TEMP'), nargs=3,
                   help='Change the set point. Specify the port, RS485 address, and the desired set '
                        'point in the controller\'s display units')
group.add_argument('-s', '--set', metavar=('PORT', 'ADDR', 'PARAM', 'VALUE'), nargs=4,
                   help='Write any parameter. The controller is read first to learn the parameter\'s '
                        'data type unless --type is given. Enumerated parameters take the integer '
                        'code from the manual (e.g. 71 for PID on 8003)')
parser.add_argument('-t', '--type', choices=['float', 'int', 'str'] + [r.name.lower() for r in Repr if r is not Repr.FLOAT],
                    help='Data type for --set: float, int (a wide enumeration), str, or a '
                         'representation name (ubyte, uword, enum, wide_enum, ...)')
parser.add_argument('-i', '--instance', type=int, default=1,
                    help='Parameter instance (channel), default 1')
parser.add_argument('-b', '--baudrate', type=int, default=38400,
                    help='Standard Bus baud rate, default 38400')


def _data_type(name):
    if name is None:
        return None
    return {'float': float, 'int': int, 'str': str}.get(name) or Repr[name.upper()]


def _value(text):
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def main(args=None):
    """
    Example usage:
    pywatlow -r COM5 1 4001
    pywatlow -w COM5 1 100
    pywatlow -s COM5 1 8003 71
    """
    args = parser.parse_args(args=args)

    if args.read:
        watlow = Watlow(port=args.read[0], address=int(args.read[1]), baudrate=args.baudrate)
        print(watlow.readParam(int(args.read[2]), instance=args.instance))
    elif args.write:
        watlow = Watlow(port=args.write[0], address=int(args.write[1]), baudrate=args.baudrate)
        print(watlow.write(float(args.write[2]), instance=args.instance))
    elif args.set:
        watlow = Watlow(port=args.set[0], address=int(args.set[1]), baudrate=args.baudrate)
        print(watlow.writeParam(int(args.set[2]), _value(args.set[3]), _data_type(args.type),
                                instance=args.instance))
    else:
        parser.print_help()
    return 0
