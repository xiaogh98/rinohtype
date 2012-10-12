
import hashlib, math, struct
from datetime import datetime, timedelta
from collections import OrderedDict


def grab(file, data_format):
    data = file.read(struct.calcsize(data_format))
    return struct.unpack('>' + data_format, data)


def grab_datetime(file):
    return datetime(1904, 1, 1, 12) + timedelta(seconds=grab(file, 'Q')[0])


# using the names and datatypes from the OpenType specification
# http://www.microsoft.com/typography/otspec/

# TODO: speed up by not re-creating the struct over and over again
#       (create once and re-use)
def create_reader(data_format):
    data_struct = struct.Struct('>' + data_format)
    return lambda file: data_struct.unpack(file.read(data_struct.size))[0]


byte = create_reader('B')
char = create_reader('b')
ushort = create_reader('H')
short = create_reader('h')
ulong = create_reader('L')
long = create_reader('l')
fixed = lambda file: grab(file, 'L')[0] / 2**16
int16 = fword = short
uint16 = ufword = ushort
longdatetime = lambda file: grab_datetime(file)
string = lambda file: grab(file, '4s')[0].decode('ascii')
tag = string
glyph_id = uint16
offset = uint16


##byte = lambda file: grab(file, 'B')[0]
##char = lambda file: grab(file, 'b')[0]
##ushort = lambda file: grab(file, 'H')[0]
##short = lambda file: grab(file, 'h')[0]
##ulong = lambda file: grab(file, 'L')[0]
##long = lambda file: grab(file, 'l')[0]
##fixed = lambda file: grab(file, 'L')[0] / 2**16
##int16 = fword = short
##uint16 = ufword = ushort
##longdatetime = lambda file: grab_datetime(file)
##string = lambda file: grab(file, '4s')[0].decode('ascii')
##tag = string
##glyph_id = uint16
##offset = uint16


def array(reader, length):
    return lambda file: [reader(file) for i in range(length)]


def indirect(reader):
    def read_and_restore_file_position(not_used, file, file_offset):
        indirect_offset = offset(file)
        restore_position = file.tell()
        result = reader(file, file_offset + indirect_offset)
        file.seek(restore_position)
        return result
    return read_and_restore_file_position


class Packed(OrderedDict):
    reader = None
    fields = []

    def __init__(self, file):
        super().__init__(self)
        self.value = self.__class__.reader(file)
        for name, mask, processor in self.fields:
            self[name] = processor(self.value & mask)


PLATFORM_UNICODE = 0
PLATFORM_MACINTOSH = 1
PLATFORM_ISO = 2
PLATFORM_WINDOWS = 3
PLATFORM_CUSTOM = 4

NAME_COPYRIGHT = 0
NAME_FAMILTY = 1
NAME_SUBFAMILY = 2
NAME_UID = 3
NAME_FULL = 4
NAME_VERSION = 5
NAME_PS_NAME = 6
NAME_TRADEMARK = 7
NAME_MANUFACTURER = 8
NAME_DESIGNER = 9
NAME_DESCRIPTION = 10
NAME_VENDOR_URL = 11
NAME_DESIGNER_URL = 12
NAME_LICENSE = 13
NAME_LICENSE_URL = 14
NAME_PREFERRED_FAMILY = 16
NAME_PREFERRED_SUBFAMILY = 17
# ...


def decode(platform_id, encoding_id, data):
    try:
        return data.decode(encodings[platform_id][encoding_id])
    except KeyError:
        raise NotImplementedError()


encodings = {}

encodings[PLATFORM_UNICODE] = {}

UNICODE_1_0 = 0
UNICODE_1_1 = 1
UNICODE_ISO_IEC_10646 = 2
UNICODE_2_0_BMP = 3
UNICODE_2_0_FULL = 4
UNICODE_VAR_SEQ = 5
UNICODE_FULL = 6

encodings[PLATFORM_MACINTOSH] = {}

encodings[PLATFORM_ISO] = {}

ISO_ASCII = 0
ISO_10646 = 1
ISO_8859_1 = 2

encodings[PLATFORM_WINDOWS] = {1: 'utf_16_be',
                               2: 'cp932',
                               3: 'gbk',
                               4: 'cp950',
                               5: 'euc_kr',
                               6: 'johab',
                               10: 'utf_32_be'}


from .cff import CompactFontFormat
from .tables import parse_table, HmtxTable


class OpenTypeParser(dict):
    def __init__(self, filename):
        self.file = file = open(filename, 'rb')
        tup = grab(file, '4sHHHH')
        version, num_tables, search_range, entry_selector, range_shift = tup
        tables = {}
        for i in range(num_tables):
            tag, checksum, offset, length = grab(file, '4sLLL')
            tables[tag.decode('ascii')] = offset, length, checksum
        for tag, (offset, length, checksum) in tables.items():
            cs = self._calculate_checksum(file, offset, length, tag=='head')
            assert cs == checksum

        for tag in ('head', 'hhea', 'cmap', 'maxp', 'name', 'post', 'OS/2'):
            self[tag] = parse_table(tag, file, tables[tag][0])

        self['hmtx'] = HmtxTable(file, tables['hmtx'][0],
                                 self['hhea']['numberOfHMetrics'],
                                 self['maxp']['numGlyphs'])
        self['CFF'] = CompactFontFormat(file, tables['CFF '][0])
        for tag in ('kern', 'GPOS', 'GSUB'):
            if tag in tables:
                self[tag] = parse_table(tag, file, tables[tag][0])

    def _calculate_checksum(self, file, offset, length, head=False):
        tmp = 0
        file.seek(offset)
        end_of_data = offset + 4 * math.ceil(length / 4)
        while file.tell() < end_of_data:
            uint32 = grab(file, 'L')[0]
            if not (head and file.tell() == offset + 12):
                tmp += uint32
        return tmp % 2**32
