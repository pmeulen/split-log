Split a log file into multiple files based on the dates at the start at each line.
For that time when logrotate did not run...

run: `python split_log_by_date.py --help` for more information on using this script.

Limitations:
- The date must be at the start of each line must have a fixed length. This could be made more flexible by e.g. allowing
  the user to provide a regex to match the date.
- The script keeps the output files open until it has finished processing the input file. You may run out of file
  descriptors if many output files are created.
  Use "ulimit -n" to see the current limit and "ulimit -n <number>" to set a new limit.
- The script will stop when it encounters an error, such as an output file that already exists.
  Except for Lines with dates that cannot be parsed. These are reported and skipped, and processing then continues with
  the next line. You can use the --dry-run option to test for parsing problems or output files that already exist.

Changelog:
* 1.1:
  - Added support for gzip compression
* 1.2:
  - Added support for skipping the first N lines of the input file
  - Include the cutoff date in the warning that is shown when the year is not parsed from the date in the input file
* 1.3:
  - Continue processing after encountering a date that cannot be parsed, ignoring the line