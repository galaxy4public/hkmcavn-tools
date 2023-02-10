#!/usr/bin/env python 
import argparse
import os
import sys
import zlib

from enum import Flag

print_v = print

def hardware_int_view(value, bits, signed):
    base = 1 << bits
    value %= base
    return value - base if signed and value.bit_length() == bits else value


class VersionHeader:
    """ The header line of the version file """

    def __init__(self, header):
        self.parse(header)

    def parse(self, header):
        (self.marker, self.release, self.target,
         self.vendor, self.model, self.model_id,
         self.unknown) = header.split('|');

    def __repr__(self):
        return (f'{self.__class__.__name__}('
                f'marker="{self.marker}", '
                f'release="{self.release}", '
                f'target="{self.target}", '
                f'vendor="{self.vendor}", '
                f'model="{self.model}", '
                f'model_id="{self.model_id}", '
                f'unknown="{self.unknown}"'
                ')')

    def __str__(self):
        return (f'{self.marker}'
                f'|{self.release}'
                f'|{self.target}'
                f'|{self.vendor}'
                f'|{self.model}'
                f'|{self.model_id}'
                f'|{self.unknown}')


class VersionFile:
    """ Manages a single file object in the file list """

    prefix = ''

    def __init__(self, definition):
        self.parse(definition)

    def parse(self, definition):
        (self.path, self.name, self.version,
         self.crc32, self.size, self.unknown) = definition.split('|')

        # normalise path
        self.path = self.path.replace('\\', '/')

        # convert to integers
        self.version = int(self.version)
        self.unknown = int(self.unknown)

        # zlib.crc32() is always unsigned integer in Python
        self.crc32 = hardware_int_view(int(self.crc32), 32, False)

        # it seems the manifest defines it as 64bit right away, but it costs us
        # nothing to ensure we get the right integer into the variable
        self.size = hardware_int_view(int(self.size), 64, False)

    def crc(self, update=False):
        result = 0
        for file in open(
                os.path.join(self.prefix, self.path, self.name),"rb"):
            result = zlib.crc32(file, result)
        if update:
            self.crc32 = result
        return result

    def validate(self, update=False):
        result = 0
        try:
            size = os.path.getsize(
                os.path.join(self.prefix, self.path, self.name))
            if self.size != size:
                if update:
                    self.size = size
                else:
                    result |= 0x1
            crc32 = self.crc(update)
            if self.crc32 != crc32:
                result |= 0x2
        except FileNotFoundError:
            if update:
                self.size = -1
            else:
                result |= 0x4
        except Exception as err:
            raise RuntimeError('unable to handle error')
        return result

    def __str__(self):
        # can't easily use an f-string here due to \\
        return '{}|{}|{}|{}|{}|{}'.format(
                self.path.replace('/','\\'),
                self.name,
                self.version,
                hardware_int_view(self.crc32, 32, True),
                hardware_int_view(self.size, 64, False),
                self.unknown)

    def __lt__(self, other):
        """ sorting operator that matches HKM's logic in the manifest """
        if self.path == other.path:
            return self.name.lower() < other.name.lower()
        return self.path.lower() < other.path.lower()

class VersionManifest:
    """ Handles operations related to the version files included in HKM firmware """

    def __init__(self, filename):
        self.filelist = []
        self.manifest = os.path.abspath(filename)
        self.manifest_dir = os.path.basename(os.path.dirname(self.manifest))
        self.firmware_dir = os.path.dirname(os.path.dirname(self.manifest))

        # XXX: out assumption here that we are never going to work with two
        #      firmware directories at the same time, if this changes the
        #      following line needs to be reworked!
        VersionFile.prefix = self.firmware_dir

        self.read(self.manifest)

    def read(self, filename):
        count = 0
        for line in open(filename, 'r'): # we are working with a text file
            count += 1
            if count == 1:  # the first line is a header
                if line[0] != '+':
                    raise(SyntaxError)
                self.header = VersionHeader(line.rstrip())
                continue

            # ready to enroll a new entry now
            self.filelist.append(VersionFile(line.rstrip()))


    def backup(self, suffix='.orig'):
        print_v('Saving the original manifest in '
                f'"{os.path.basename(self.manifest)}.orig" ... ', end='')
        os.replace(self.manifest, f'{self.manifest}.orig')
        print_v('done')


    def generate(self, filename=''):
        if not filename:
            filename = self.manifest
        print_v(f'Creating the new manifest file "{os.path.basename(filename)}"... ', end='')
        with open(filename, 'x') as file_out:
            file_out.write(f'{self.header}\n')  # write the header line
            for file in sorted(self.filelist):
                if file.size >= 0:              # check for removed files
                    file_out.write(f'{file}\n')
        print_v('done')


    def validate(self, interactive=False, update=False):

        def result2reason(code):
            """ an internal function to provide human readable reasons """
            msg =''

            # let's avoid using match/case it is too new
            if code == 0:
                return 'OK'

            if code == 0x4:
                return 'File not found'

            if code & 0x1:
                msg = 'Size mismatch'

            if code & 0x2:
                if msg:
                    msg += ' + '
                msg += 'CRC32 check failed'

            if code & 0x4:
                msg += ' (and file disapeared)'

            return msg

        if update:
            print_v('Re-validating and updating', end='')
        else:
            print_v('Validating', end='')
        print_v(' the firmware directory against the manifest file:')

        result = 0
        for file in self.filelist:
            answer =''
            print_v(f'{os.path.join(file.path, file.name)} => ', end='')
            ret = file.validate(update)
            if ret:
                print_v(f'FAILED: {result2reason(ret)}')
            else:
                print_v('ok')
            result |= ret

        if result:
            print_v('ERROR: at least one file has not be processed '
                    'successfully, chances are something is broken!')
            if not interactive:
                return result

            print('Some files seems to be changed and do not match '
                  'the manifest.')
            answer = input('Update the manifest file? [y/N] ')
            if answer and answer[0].lower() == 'y':
                answer = 'y'
                print('The current implementation requires to re-run the '
                      'calculations to apply the chage, re-validating ...')
                result = self.validate(False, True)
                if result:
                    print('The re-validation returned an unexpectd error!')
                    answer = input('Do you REALLY want to update the '
                                   'manifest file? [y/N] ')
                    if answer and answer[0].lower() == 'y':
                        answer = 'y'
                    else:
                        return -1

                self.backup()

                # now, that we successfully create a backup, let's create a new
                # manifest from our in-memory data
                self.generate()

            else:
                return -1

        return result


    def update(self, interactive=False):
        result = 0
        answer = ''

        print_v('Collecting the manifest data from the firmware directory:')
        self.filelist.clear()   # nuke the entries
        for path, subdirs, files in os.walk(
                os.path.join(self.firmware_dir, self.manifest_dir)):
            for file in files:
                if file.startswith(os.path.basename(self.manifest)):
                    continue    # skip the manifest itself and similar files
                self.filelist.append(
                    VersionFile(
                        f'{path[len(self.firmware_dir)+1:]}|{file}|14|0|0|1'
                    ))

        for file in self.filelist:
            print_v(f'{os.path.join(file.path, file.name)} => ', end='')
            ret = file.validate(True)
            if ret:
                print_v('FAILED')   # should not really happen
            else:
                print_v('ok')
            result |= ret

        if result:
            print_v('ERROR: at least one file has not be processed '
                    'successfully, chances are something is broken!')
            if not interactive:
                return result

        if interactive:
            if result:
                print('Some calculations were unsuccessful!')
            else:
                print('All calculations were completed successfully.')
            answer = input('Update the manifest file? [y/N] ')
            if answer and answer[0].lower() == 'y':
                answer = 'y'
            else:
                return -1

        self.backup()

        # now, that we successfully create a backup, let's create a new
        # manifest from our in-memory data
        self.generate()

        return result


    def __repr__(self):
        return (f'VersionFile(header={repr(self.header)}, '
                f'filelist=VersionFile[{len(self.filelist)}])')


def main():
    global print_v

    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('-t', '--test', action='store_true',
                        help='validate the firmware directory against manifest')
    mode.add_argument('-u', '--update', action='store_true',
                        help='perform encryption')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='enable verbose output')
    parser.add_argument('-i', '--interactive', action='store_true',
                        help='ask user for permission to make changes')
    parser.add_argument('file', type=str,
                        help="a manifest file (usually a .ver file)")
    args = parser.parse_args()

    print_v = print if args.verbose else lambda *a, **k: None

    print_v('Loading the manifest file ... ', end='')
    manifest = VersionManifest(args.file)
    print_v('done')

    result = 0
    if args.update:
        result = manifest.update(args.interactive)
    else:
        result = manifest.validate(args.interactive)

    if result == 0:
        print_v('\nAll done, the requested operation '
                'successfully completed!\n')


if __name__ == '__main__':
    main()
