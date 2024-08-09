xcrypt.py
===

This is a small (and not very Pythonic) Python script that implements both
decryption and encryption of the firmware files as distributed by several
automotive companies who are using the head unit solution designed by LG
Electronics (LGe).  These head units can be found in modern KIAs, Hyundais,
GMs, and Hondas (according to LGe's B2B site).  However, the work and all the
tests are performed on using firmware related to 2022 KIA Sportage GT-Line as
it was distributed in Australia.

The encrypted files are using AES128-CBC with a non-standard approach for
encrypting last incomplete 16 bytes blocks.  The files have also 16KB metadata
structure attached to them.  The [metadata format structure](https://github.com/galaxy4public/hkmcavn-tools/wiki/Metadata-format) is documented
in the Wiki.

Usage
---

The script currently supports three modes of operation:

1. testing whether a file (or a group of files) are encrypted or not encrypted

   The following session excerpt is from running the script against all files in
   the directory with downloaded firmware for 2022 KIA Sportage:

       $ ~/hkmcavn-tools/xcrypt/xcrypt.py -t -v $(find . -type f)
       no output was specified, will prepend ".out" suffix to processed files
       Performing a determination whether files are encrypted or not
       ./2022_Sportage_AU.ver: metadata signature was not found
       ./2022_Sportage_AU.ver => not encrypted or invalid
       ./whatsnew/whatsnew/KIA/RU/update-ko_KR.json => encrypted
       ./whatsnew/whatsnew/KIA/RU/whatsnew-el_GR.url => encrypted

   This mode of operation is a side-effect of the decryption routines, hence
   you may see a strange message in regard to the output prefix when the mode does
   not modify anything.  However, this mode might be useful to quickly assess what
   is encrypted in the directory tree and what is not, since Kia/Hyindai tend to
   provide both encrypted and plain firmware files inside their firmware updates.

   The command above was running with the verbose flag specified.  If the flag is
   omitted the script would not produce any output, but will indicate through the
   exit code whether it encountered any unencrypted files (exit code > 0) and one
   can determine what kind of an issue the script has encountered by checking the
   exit code (please see the script source to understand what different exit codes
   mean).  For a very simple use case, one can just run `xcrypt.py -t file_to_check`
   and if exit code is zero, then the file is encrypted and most likely can be
   decrypted using the script. If the exit code is not zero, then the file is
   either not encrypted or damaged.

2. decrypting one or more files

   The following demonstrates how to decrypt a single file:

       $ ~/hkmcavn-tools/xcrypt/xcrypt.py -d -v ~/KIA/2022_Sportage_AU/.lge.upgrade.xml -o .lge.upgrade.xml
       Performing a decryption
       /home/galaxy/KIA/2022_Sportage_AU/.lge.upgrade.xml => .lge.upgrade.xml

   The following demonstrates how to decrypt a whole folder:

       $ ~/hkmcavn-tools/xcrypt/xcrypt.py -d -v ./ -o ./decrypted/
       Performing a decryption
       ./.lge.upgrade.xml => ./decrypted/.lge.upgrade.xml
       ...

3. encrypting one or more files

   Below is an example of a session where a plain-text version of the XML
   file is encrypted back to its version from the firmware distribution:

       $ ~/hkmcavn-tools/xcrypt/xcrypt.py -e -v .lge.upgrade.xml -o encrypted/.lge.upgrade.xml
       Performing an encryption
       .lge.upgrade.xml => encrypted/.lge.upgrade.xml

   The following demonstrates how to encrypt a whole folder:

       $ ~/hkmcavn-tools/xcrypt/xcrypt.py -e -v ./ -o ./encrypted/
       Performing an encryption
       ./.lge.upgrade.xml => ./encrypted/.lge.upgrade.xml
       ...

   Note: the encryption logic implemented by LGe relies on the file name, so
   if you rename an encrypted file it would not be possible to decrypt it using
   the standard logic (perhaps a new mode needs to be introduced to specify
   the original name of the file for these cases?).

You can always get a help output with `-h` if you are not sure which options to
use, but since the script is in its early development there is no point of
documenting the options here at the moment.

When multiple files or a folder are specified on the command line for either encryption or
decryption, the only accepted value for the output is a directory.  As it is
currently implemented, the script will create full paths to files it was
working on under the specified directory, e.g. if you ask to decrypt files
`../abc.def` and `/somewhere/fed.bca` and put output into `out/`, then the
script will create `out/home/user/abc.def` (if that relative path to `abc.def`
was pointing to a file in user's home directory) and `out/somewhere/fed.bca`.
Most likely, this behaviour will be tuned in future versions of the script, but
right now it works as described above.

Known limitations / TODO
---
  - Only produces the 'TE2' version of the encrypted files (no 'TER' yet)
  - Does not yet support the addition of the RSA signature into the metadata

Thanks
---

The creation of this script would not be possible without generous help from
the community at [Gen5 Wide-Open](https://g4933.gitlab.io/wideopen/) and their
Telegram channel.  Specifically, the following people contributed the most
(listed in no particular order):

  - WideOpen (thanks for sharing previous research on the topic)
  - Brody (thanks for prompt responses and bootstrapping this research)
  - Alexey Murzilin (thanks for willingness to sacrifice your time for running commands on the real hardware)
  - AlexE (thanks for providing data from the real hardware)
  - Rob (thanks for keeping me up to date with news and moral support)
  
