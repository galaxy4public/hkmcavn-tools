#!/bin/env python
import argparse
import os
import sys
import time

from base64 import b64encode
from Crypto.Cipher import AES
from Crypto.Hash import SHA256

print_v = print
KEY = '60a93d70f73302a63e5ed0d0ea38be22'
IV = ''
META_SIZE=0x4024    # size of the metadata blob
PADDING=b''

def hardware_int_view(value, bits, signed):
    base = 1 << bits
    value %= base
    return value - base if signed and value.bit_length() == bits else value

def calculate_iv(file, size):
    basename = os.path.basename(file)
    check_code = SHA256.new()
    check_code.update(f'{os.path.basename(file)}{hardware_int_view(size, 32, True)}'.encode('utf-8'))
    return check_code.hexdigest()[:32]

def perform_test(file):
    global IV
    global PADDING
    result = 0xFF

    with open(file, 'rb') as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()
        if file_size <= META_SIZE:
            print_v(f'{file}: file is too small to be encrypted')
            return 0x01

        f.seek(file_size - META_SIZE, os.SEEK_SET)
        metadata = f.read(META_SIZE)
        if not metadata:
            print_v(f'{file}: failed to read metadata from the file')
            return 0x20

    if metadata[:2] != b'TE':
        print_v(f'{file}: metadata signature was not found')
        return 0x2

    if not metadata[2] in [ 50, 82 ]:
        print_v(f'{file}: unknown version of metadata')
        return 0x4

    if metadata[2] == 82:
        print_v(f'{file}: unsupported version of metadata')
        return 0x8

    IV = calculate_iv(file, file_size - META_SIZE)

    check_code = SHA256.new()
    check_code.update(bytes.fromhex(IV))
    check_code.update(metadata[36:])
    if metadata[4:36] != check_code.digest():
        print_v(f'{file}: metadata integrity check failed')
        return 0x10

    PADDING=metadata[36:52]             # let's save embedded padding vector

    result = {}
    result['file'] = file
    result['size'] = file_size - META_SIZE
    result['padding'] = metadata[36:52]
    result['iv'] = IV
    return result

def perform_encrypt(block, cipher, check_code):
    BLOC=16
    index = 0
    encd = b''

    pad = 0
    if (len(block) % BLOC) > 0:
        pad = BLOC - len(block) % BLOC
        block += b'\0' * pad

    while index < len(block):
        encd += cipher.encrypt(block[index:index+BLOC])
        index += BLOC

    return encd


def perform_decrypt(block, cipher, param):
    BLOC=16
    index = 0
    decd = b''

    #print(f' {len(block)}:{len(block) % BLOC}')
    pad = 0
    if (len(block) % BLOC) > 0:
        #print(f'short block: {len(block)} by {len(block)%BLOC}')
        pad = BLOC - len(block) % BLOC
        #block += bytes.fromhex('83d1d2324f8a69f889f8')
        block += PADDING[:pad]
        #print(f'padded by {pad} bytes to total {len(block)} ({PADDING[:pad].hex()})')

    while index < len(block):
        decd += cipher.decrypt(block[index:index+BLOC])
        index += BLOC
    return decd[:len(block) - pad]


def read_in_chunks(file_object, chunk_size=4*1024, limit = -1):
    """Lazy function (generator) to read a file piece by piece.
    Default chunk size: 1MB."""
    ptr = 0
    while True:
        data = file_object.read(chunk_size)
        if not data:
            #print(f'end of file, read {ptr} chunks of {chunk_size} with limit set to {limit}')
            break
        ptr = ptr + 1
        if limit > 0 and len(data) > limit - (ptr-1)*chunk_size:
            #print_v('processing truncated block')
            #print(f'read {ptr-1} chunks of {chunk_size} + {len(data)} with limit set to {limit}')
            #print(f'giving out {limit - (ptr-1)*chunk_size}')
            yield data[:limit - (ptr-1)*chunk_size]
            break
        yield data


def process_block(mode, block, cipher, param):
    return mode(block, cipher, param)

def update_progress(file, size, block):
    count = 0
    while size > count * block:
        count += 1
        percent = (count * block * 100) / size
        # out block is bigger than actual data read
        percent = min(percent, 100.0)
        print_v(f'\r{file} .. {percent:3.0f}%', end='')
        yield percent
    yield 100   # this assures that we never run out of data for the progress

def process_file(mode, file, block_size, output):
    #file_size = os.path.getsize(file)

    if mode == perform_decrypt:
        metadata = perform_test(file)   # this extracts and populates IV
        if isinstance(metadata, int) and metadata != 0:
            print(f'\r{file} is either unencrypted or damaged (use -v -t to see the details)')
            return
        file_size = metadata['size']
        iv = bytes.fromhex(metadata['iv'])
        param = ''
    elif mode == perform_encrypt:
        file_size = os.path.getsize(file)
        iv = bytes.fromhex(calculate_iv(file, file_size))
        param = SHA256.new()
        param.update(iv)

    with open(file, 'rb') as file_in:
        with open(output, 'xb+') as file_out:
            cipher = AES.new(bytes.fromhex(KEY), AES.MODE_CBC, iv)
            print_v('\r\033[K', end='')
            progress = update_progress(file, file_size, block_size)
            for block in read_in_chunks(file_in, block_size, file_size):
                file_out.write(process_block(mode, block, cipher, param))
                percent = next(progress)
            print_v('\r', end='')

            if mode == perform_encrypt:
                metadata = bytearray(META_SIZE-1) # META_SIZE
                metadata[0:2] = b'TE2'
                pad = 16 - file_size % 16
                if pad > 0:
                    file_out.seek(-pad, os.SEEK_END)
                    padding = file_out.read(pad)
                    metadata[36:36+pad] = padding
                    file_out.seek(-pad, os.SEEK_END)

                param.update(metadata[36:])
                metadata[4:36] = param.digest()
                file_out.write(metadata)



def main():
    global print_v

    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('-t', '--test', action='store_true',
                        help='test for encryption signature')
    mode.add_argument('-e', '--encrypt', action='store_true',
                        help='perform encryption')
    mode.add_argument('-d', '--decrypt', action='store_true',
                        help='perform decryption')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='enable verbose output')
    parser.add_argument('-b', '--block-size', type=int, dest='block_size',
                        help='sets the read buffer in bytes (default 4096)',
                        default=4*1024)
    parser.add_argument('-o', '--output', type=str, dest='output',
                        help="output directory where result will be stored")
    parser.add_argument('file', type=str, nargs='+',
                        help="a list of input files for the selected operation")
    args = parser.parse_args()

    print_v = print if args.verbose else lambda *a, **k: None

    if args.block_size % 16:
        print('ERROR: the specified block size is not aligned, should be dividable by 16!')
        sys.exit(1)

    if args.output:
        if args.output[-1] == "/":
            print_v('output set to a directory')
            if not os.path.isdir(args.output):
                print_v(f'creating output directory "{args.output}"')
                os.makedirs(args.output, mode=777)
        else:
            if len(args.file) > 1 or os.path.isdir(args.file[0]):
                print(f'ERROR: cannot process multiple files into one, check that "-o" argument ends with /')
                sys.exit(1)
    else:
        print_v('no output was specified, will prepend ".out" suffix to processed files')

    # let's abuse the mode variable :)
    print_v('Performing ', end='')
    if args.test:
        print_v('a determination whether files are encrypted or not')
        mode = perform_test
    elif args.encrypt:
        print_v('an encryption')
        mode = perform_encrypt
    else:
        print_v('a decryption')
        mode = perform_decrypt

    result = 0
    files_to_process = [os.path.join(path, name) for path, subdirs, files in os.walk(args.file[0]) for name in files] if os.path.isdir(args.file[0]) else args.file 
    for file in files_to_process:
        if not os.access(file, os.R_OK):
            print_v(f'{file} does not exist or is not readable, skipping')
            continue
        if args.test:
            file_result = perform_test(file)
            if isinstance(file_result, int) and file_result != 0:
                result |= file_result
                print_v(f'{file} => not encrypted or invalid')
            else:
                print_v(f'{file} => encrypted')
        else:
            output_file = args.output
            if args.output:
                if args.output[-1] == "/":
                    output_file = os.path.join(args.output, os.path.relpath(file))
                    print(f'{output_file}')
                    if not os.path.isdir(os.path.dirname(output_file)):
                        print_v(f'creating output directory "{args.output}"')
                        os.makedirs(os.path.dirname(output_file))
            else:
                output_file = f'{file}.out'
            process_file(mode, file, args.block_size, output_file)
            print_v(f'{file} => {output_file}')

    sys.exit(result)

if __name__ == '__main__':
    main()
