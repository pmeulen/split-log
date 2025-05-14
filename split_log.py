#!/usr/bin/env python3

"""
Split a log file into multiple files based on the dates at the start at each line.
For that time when logrotate did not run...
See the help text for more information on using this script.

Limitations:
- The date must be at the start of each line must have a fixed length. This could be made more flexible by e.g. allowing
  the user to provide a regex to match the date.
- The script keeps the output files open until it has finished processing the input file. You may run out of file
  descriptors if many output files are created.
  Use "ulimit -n" to see the current limit and "ulimit -n <number>" to set a new limit.
- The script will stop when it encounters an error, like a date that cannot be parsed or an output file that already
  exists. You can use the --dry-run option to test for parsing problems or output files that already exist.

Changelog:
1.1:
- Added support for gzip compression
"""

__version__ = 1.1
__license__ = "Apache 2.0"

import argparse
import os
import sys
from datetime import datetime
from enum import Enum, auto
from io import TextIOWrapper
from time import strptime, strftime

class Compression(Enum):
    NONE = auto()
    GZIP = auto()
    BZIP = auto()

def create_file(output_file: str, compress: Compression, dry_run: bool):
    """
    Create the output file in binary mode. Use x mode to ensure a new file is created and an error is returned if the
    file already exists.
    :param output_file: Name of the output file to create. ".bz2" will be appended if compress is True
    :param compress: Compression type to be used for the output file (NONE, GZIP, or BZIP)
    :param dry_run: True if the file should not be created, but only checked if it would be created
    :return: the file handle for the output file. If dry_run is True, the file handle is True
             None if the file could not be created
    """

    if compress == Compression.BZIP:
        output_file += '.bz2'
    elif compress == Compression.GZIP:
        output_file += '.gz'
    sys.stderr.write(f"Creating output file: {output_file}\n")

    if dry_run:
        # In dry run mode do not create the file, but do check if it would be created and if it already exists
        if os.path.exists(output_file):
            sys.stderr.write(f"Error creating output file: {output_file}\n")
            sys.stderr.write("Error: File already exists\n")
            return None  # Error
        return True  # Dummy file handle

    try:
        # Create the output file in binary mode
        # Use x mode to ensure a new file is created and an error is raised if the file already exists
        if compress == Compression.BZIP:
            import bz2  # only import bz2 if we need it
            # noinspection PyUnboundLocalVariable
            return bz2.BZ2File(output_file, 'xb')
        elif compress == Compression.GZIP:
            import gzip
            return gzip.GzipFile(output_file, 'xb')
        else:
            return open(output_file, 'xb')

    except IOError as e:
        sys.stderr.write(f"Error creating output file: {output_file}\n")
        sys.stderr.write(f"Error: {e}\n")
        return None  # Error


def process(input_stream: TextIOWrapper, output_directory: str, input_date_format: str, basename: str,
            output_suffix: str,
            dry_run: bool, compress: Compression) -> int:
    """
    Process the input stream and write the output to the output stream.
    :param input_stream: the input stream to read the log file from
    :param output_directory: the output directory to write the log files to
    :param input_date_format: the date format to be used in the log files
    :param basename: the basename to be used in the log files
    :param output_suffix: the suffix to be used in the log files
    :param dry_run: if True, do not write to output files, only show what files would be created
    :param compress: compression type to be used for the output files (NONE, GZIP, or BZIP)

    :return: int 0 on success, 1 on error
    """

    if dry_run:
        sys.stderr.write("Dry run mode: no files will be written.\n")

    if compress == Compression.BZIP:
        sys.stderr.write("Compressing output files using bzip2.\n")
        try:
            import bz2  # only import bz2 if we need it
        except ImportError:
            sys.stderr.write("Error: bzip2 module not found. Please install it.\n")
            sys.stderr.write("E.g. pip install bz2\n")
            return 1
    elif compress == Compression.GZIP:
        sys.stderr.write("Compressing output files using gzip.\n")
        try:
            import gzip
        except ImportError:
            sys.stderr.write("Error: gzip module not found.\n")
            return 1

    # Check if the input_date_format parses the year
    now = datetime.now()
    date_includes_year = format_includes_year(input_date_format)
    if not date_includes_year:
        sys.stderr.write(f"Warning: The input date format does not include the year:\n")
        sys.stderr.write(f"  - Dates in the past will be interpreted as being in the current year ({now.year}).\n")
        sys.stderr.write(f"  - Dates after in the future be interpreted as being in the past year ({now.year - 1}).\n")

    # Get the length of the input date format so we can cut it from the start of the lines
    # assume the input date format is always the same length
    input_date_length = len(now.strftime(input_date_format))
    sys.stderr.write(f"Using a length of {input_date_length} for the dates in the input.\n")

    num_lines = 0  # Number of lines read from the input stream
    files_created = {}  # Map of formatted date to file handle
    try:
        for line in input_stream:  # read the input stream line by line
            num_lines += 1
            date_str = line[0:input_date_length]
            try:
                date = datetime.strptime(date_str, input_date_format)
            except ValueError as e:
                sys.stderr.write(f"Error parsing line #{num_lines}:\n")
                sys.stderr.write(f"{line}\n")
                sys.stderr.write(
                    f"Date string \"{date_str}\" could not be parsed using format string \"{input_date_format}\"\n")
                sys.stderr.write(f"Error: {e}\n")
                return 1

            # Adjust the year if needed
            if not date_includes_year:
                now = datetime.now()
                date=date.replace(year=now.year) # Assume the date is in the current year
                if date > now:  # If the date is in the future, set the year to the past year
                    date = date.replace(year=now.year - 1)

            # Check if we have a file handle for this date_key, if not create it
            date_key = date.strftime(output_suffix)
            if date_key not in files_created:
                output_file = os.path.join(output_directory, basename + date_key)
                file_handle = create_file(output_file, compress, dry_run)
                if file_handle is None:
                    return 1
                files_created[date_key] = file_handle

            file_handle = files_created[date_key]

            # Write the line to the output file
            if not dry_run:
                try:
                    file_handle.write(line.encode('utf-8'))
                except IOError as e:
                    sys.stderr.write(f"Error writing to output file for date: {date_key}\n")
                    sys.stderr.write(f"Error: {e}\n")
                    return 1
        return 0

    except Exception as e:  # Does not catch KeyboardInterrupt
        sys.stderr.write(f"Aborted...\n")
        sys.stderr.write(f"Error: {e}\n")
        return 1

    finally:
        sys.stderr.write(f"Processed {num_lines} line(s).\n")
        # Close all the file handles
        sys.stderr.write(f"Closing {len(files_created)} output files... ")
        if not dry_run:
            for file_handle in files_created.values():
                file_handle.close()
        sys.stderr.write("done.\n")
        # Do not return any error codes here, the return code is already set in the try block or the except block

# Check if input_date_format parses the year
def format_includes_year(input_date_format: str) -> bool:
    # Create a date string for the previous year and check if the year is parsed correctly.
    now = datetime.now()
    now_min_one_year = now.replace(year=now.year - 1)
    date_formatted_last_year = now_min_one_year.strftime(input_date_format)
    date_parsed_last_year = strptime(date_formatted_last_year, input_date_format)
    return date_parsed_last_year.tm_year == now_min_one_year.year


### Main function
def main():
    # Get the current working directory
    current_dir = os.getcwd()

    default_input_date_format = '%b %d %H:%M:%S'  # Default date format for the input log file
    default_output_suffix = '-%Y%m%d'  # Default suffix for the output log files
    default_basename = 'split_log'  # Default basename for the output log files

    # Create examples using the current date
    default_input_date_format_example = datetime.now().strftime(default_input_date_format)
    default_output_suffix_example = datetime.now().strftime(default_output_suffix)

    parser = argparse.ArgumentParser(
        description="Split a log file into multiple files based on the dates at the start at each line.",
        formatter_class=argparse.RawTextHelpFormatter,  # Show embedded newlines in the help text
        epilog="""\
Split a log file into multiple files based on the date at the start of each line.  The dates do not need to be in 
chronological order.  

The date format at the start of each line must have a fixed length and can be specified using the `-f` option  
(default: "%s"). Processing stops if a date cannot be parsed.

For each unique date found in the input file, a new output file will be created.  The output files will be named using 
the specified basename (default: "%s") and the date format provided with the `-p` option (default: "%s").
If the output file already exists, an error will be raised.

By default, the output files will be created in the current working directory.  Use the `-d` option to specify a 
different output directory. This directory must exist and be writable.

The `--dry-run` option allows you to simulate the process of parsing the file without creating or writing to any output 
files.  The `-z` option compresses the output files using the gzip or bzip2 algorithm, this will add the `.gz` or `.bz2` 
extension to the output files automatically.

""" % (default_input_date_format, default_basename, default_output_suffix_example))

    parser.add_argument('input', nargs='?', type=argparse.FileType('r'), default=sys.stdin,
                        help='Input file. Defaults to stdin if not provided.')
    parser.add_argument('-d', '--output-dir', dest='output_dir', type=str, default=current_dir,
                        help='Output directory for the split log files')
    parser.add_argument('-b', '--basename', dest='basename', type=str,
                        help='Basename for the split log files. Defaults to the input file name or "%s" when not provided.'
                        % default_basename)

    # Add the -f option to specify the input date format
    input_date_format_help = ('Input date format as used by strptime(). Default: "%s". Example: "%s"'
                              % (default_input_date_format, default_input_date_format_example))
    input_date_format_help = input_date_format_help.replace('%', '%%')  # Must escape the % sign in the help message
    parser.add_argument('-f', '--input-date-format', dest='input_date_format', type=str,
                        default=default_input_date_format,
                        help=input_date_format_help)

    # Add the -p option to specify the output suffix pattern
    output_suffix_help = ('Output suffix for the split log files as used by strftime(). Default: "%s". Example: "%s"'
                          % (default_output_suffix, default_output_suffix_example))
    output_suffix_help = output_suffix_help.replace('%', '%%')  # Must escape the % sign in the help message
    parser.add_argument('-p', '--output-suffix-pattern', dest='output_suffix', type=str, default=default_output_suffix,
                        help=output_suffix_help)

    parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                        help='Do not write to output files, only show what files would be created.')
    parser.add_argument('-z', '--compress', choices=['none', 'gzip', 'bzip'], default='none', dest='compress', type=str,
                        help='Compress output files (none, gzip, or bzip).')
    parser.add_argument('--version', action='version', version='%(prog)s ' + str(__version__),
                        help='Show the version number and exit.')
    parser.add_argument('--show-format-help', action='store_true', dest='show_format_help',
                        help='Show help for the format string (strftime and strptime) syntax.')
    args = parser.parse_args()

    # Show help for the format string (strftime and strptime) syntax
    if args.show_format_help:
        show_format_help()

    # Print help hint if no arguments are provided
    if args.input.name == '<stdin>':
        sys.stderr.write("No input file provided, reading input file from stdin.\n")
    if len(sys.argv) == 1:
        sys.stderr.write("Use the -h option for help.\n")

    # Check if the provided patterns are valid by reconstructing the current date using the provided patterns
    try:
        input_date_format_example = datetime.now().strftime(args.input_date_format)
    except ValueError:
        sys.stderr.write(f"Invalid input date format: {args.input_date_format}\n")
        sys.exit(1)
    sys.stderr.write('Using input date format: "%s" ("%s")\n' % (args.input_date_format, input_date_format_example))

    try:
        default_output_suffix_example = datetime.now().strftime(args.output_suffix)
    except ValueError:
        sys.stderr.write(f"Invalid output suffix format: {args.output_suffix}\n")
        sys.exit(1)

    # Check if the output directory exists
    if not os.path.exists(args.output_dir):
        sys.stderr.write(f"Output directory {args.output_dir} does not exist.\n")
        sys.exit(1)
    # Get the absolute path of the output directory
    args.output_dir = os.path.abspath(args.output_dir)
    # Check if the output directory is writable
    if not os.access(args.output_dir, os.W_OK):
        sys.stderr.write(f"Output directory {args.output_dir} is not writable.\n")
        sys.exit(1)

    if args.basename is None:
        # Use the input file name as the basename if not provided
        if args.input.name == '<stdin>':
            # If the input is from stdin, use the default basename
            args.basename = default_basename
        else:
            args.basename = os.path.splitext(os.path.basename(args.input.name))[0]

    example_output_file = os.path.join(args.output_dir, args.basename + strftime(default_output_suffix_example))
    sys.stderr.write('Using output file format: "%s%s"\n' % (args.basename, args.output_suffix))
    sys.stderr.write('Example output file: "%s"\n' % example_output_file)

    compression_map = {
        'none': Compression.NONE,
        'gzip': Compression.GZIP,
        'bzip': Compression.BZIP
    }
    compression_type = compression_map[args.compress.lower()]

    input_stream = TextIOWrapper(args.input.buffer, encoding='utf-8')

    try:
        res = process(input_stream, args.output_dir, args.input_date_format, args.basename, args.output_suffix,
                      args.dry_run, compression_type)
        if res != 0:
            sys.stderr.write("Error processing input file.\n")
            sys.exit(1)
        sys.stderr.write('Successfully processed the input file.\n')
    except KeyboardInterrupt:
        print("\nCTRL+C caught.")
        sys.exit(1)

    sys.exit(0)


def show_format_help():
    sys.stderr.write("""\
Common format string (strftime and strptime) codes for use in the input date format (-f) 
and the output suffix pattern (-p) options.  For a complete list of format codes, see the Python documentation:
https://docs.python.org/3/library/datetime.html#strftime-and-strptime-format-codes

Directive  Meaning
     %a    Abbreviated weekday name (e.g. 'Mon')
     %d    Day of the month as a zero-padded decimal number (01 - 31)
     %b    Abbreviated month name (e.g. 'Jan')
     %m    Month as a zero-padded decimal number (01 - 12)
     %y    Year without century as a zero-padded decimal number (00 - 99)
     %Y    Year with century as a decimal number (e.g. '2025')
     %H    Hour (00 - 23)
     %I    Hour (01 - 12)
     %p    AM or PM
     %M    Minute (00- 59)
     %S    Second (00 - 59)
     %f    Microsecond (000000 - 999999)
     %z    UTC offset in the form +HHMM or -HHMM
     %j    Day of the year as a zero-padded decimal number (001 - 366)
     %U    Week number of the year (Sunday as the first day of the week) as a zero-padded decimal number (00 - 53)
     %W    Week number of the year (Monday as the first day of the week) as a zero-padded decimal number (00 - 53)
    %:z    UTC offset in the form +HH:MM or -HH:MM

""")
    sys.exit(0)


if __name__ == '__main__':
    main()
