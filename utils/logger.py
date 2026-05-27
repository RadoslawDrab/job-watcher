import traceback
from pathlib import Path
from datetime import datetime

from utils.classes import Singleton


LOG_TYPES = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

class LoggerFormat:
	"""A configuration class to define the format of log messages."""
	def __init__(self, date_format: str | None = '%d/%m/%Y, %H:%M:%S', show_log_type: bool = True, show_traceback: bool = False, traceback_limit: int | None = None):
		self.date = date_format
		self.show_log_type = show_log_type
		self.show_traceback = show_traceback
		self.traceback_limit = traceback_limit
	@property
	def default(self):
		"""Returns a default LoggerFormat instance."""
		return LoggerFormat()

class Logger(Singleton):
	"""
	A singleton class for handling application-wide logging.

	It supports logging to a file, different log levels, custom formatting,
	and automatic exception traceback logging.
	"""
	def __init__(self,
	             log_file: str | Path,
	             default_log_type: str | None = None,
	             error_log_type: str | None = None,
	             log_types: list[str] | None = None,
	             title: str = 'LOG FILE',
	             header_wrappers: str = '###',
	             print_only: bool = False,
	             min_log_level: str = 'DEBUG',
	             logger_format: LoggerFormat = LoggerFormat.default
	             ):
		"""
		Initializes the Logger singleton instance.

		Args:
		    log_file: Path to the log file.
		    default_log_type: The default level for logs (e.g., 'INFO').
		    error_log_type: The log level to use when an exception is detected.
		    log_types: A list of valid log type strings.
		    title: The title to write at the top of a new log file.
		    header_wrappers: Characters to wrap the title in.
		    print_only: If True, logs will only be printed to the console, not written to a file.
		    logger_format: A LoggerFormat instance to configure the log message format.
		"""
		log_types = log_types or LOG_TYPES
		# Validate the provided log types.
		if default_log_type and default_log_type not in log_types:
			raise ValueError(f"Invalid default log type: '{default_log_type}'. Valid options: {log_types}")
		if error_log_type and error_log_type not in log_types:
			raise ValueError(f"Invalid error log type: '{error_log_type}'. Valid options: {log_types}")

		self._path = Path(log_file)
		self._path.parent.mkdir(exist_ok=True)
		self._title = title
		self._print_only = print_only
		self._min_log_index = log_types.index(min_log_level.upper())
		self._header_wrappers = (header_wrappers or '###').strip()
		self._logger_format = logger_format

		self._log_types: list[str] = log_types
		self._error_log_type = error_log_type
		self._default_log_type = default_log_type

		self._init()

		super().__init__()

	@property
	def log_types(self) -> list[str]:
		"""Returns the list of valid log types."""
		return self._log_types
	@classmethod
	def error_log_type(cls) -> str:
		"""Returns the configured log type for errors."""
		return cls._instance._error_log_type
	def _init(self) -> None:
		"""Initializes the log file, writing a header if it's new."""
		self._write(self._get_header(self._title) if not self._path.exists() else '')
		self.logs: list[dict[str, any]] = self._read()
	def _write(self, content: str) -> None:
		"""Appends content to the log file."""
		with open(self._path, 'a' if self._path.exists() else 'w', encoding='utf-8') as f:
			f.write(content)
	def _read(self) -> list:
		"""Reads the content of the log file."""
		if not self._path.exists():
			raise FileNotFoundError(f"File '{self._path}' not found")
		with open(self._path, 'r', encoding='utf-8', errors='replace') as f:
			content = f.read()

			return [l for l in content.split('\n') if not l.startswith(self._header_wrappers) and l]
	def _get_header(self, content: str):
		"""Formats a header string with wrappers."""
		return f'{self._header_wrappers} {content.strip()} {self._header_wrappers}'
	def _get_info(self, log_type: str | None = None, traceback = None):
		"""Gathers and formats metadata for a log entry based on current settings."""
		if self._logger_format.show_log_type and log_type and log_type not in self._log_types:
			raise ValueError(f"Invalid log type: {log_type}. Valid values: {self._log_types}")
		date = datetime.now().strftime(self._logger_format.date)
		return {
			'date': date,
			'log_type': log_type if self._logger_format.show_log_type else None,
			'traceback': traceback if self._logger_format.show_traceback else None
		}

	@property
	def _max_log_type_length(self):
		"""Calculates the length of the longest log type for formatting purposes."""
		return max(map(len, self._log_types))

	@classmethod
	@Singleton.exists
	def log(cls, *messages: any, log_type: str | None = None, sep: str = ' ', end: str = '', print_message: bool | None = None, print_only: bool | None = None, check_messages: bool = False, force_print: bool | None = None) -> None:
		"""
		The main logging method. Writes a message to the console and/or log file.

		Args:
		    *messages: The message parts to be logged.
		    log_type: The level of the log (e.g., 'INFO', 'ERROR').
		    sep: The separator to use when joining message parts.
		    end: The character to append at the end of the log message.
		    print_message: If True, prints the log to the console.
		    print_only: Overrides the instance's print_only setting for this specific call.
		    check_messages: If True, filters out any message parts that are None or empty.
		    force_print: If True, forces the log to be printed to the console.
		"""
		self = cls._instance
		log_type = log_type or self._default_log_type or ''

		# Automatically detect if an exception object is passed in the messages.
		exception = next((m for m in messages if isinstance(m, Exception)), None)
		tb = exception.__traceback__ if exception else None

		# Get formatted metadata for the log entry.
		info = self._get_info(log_type=log_type, traceback=tb)
		log_type, date = info.get('log_type'), info.get('date')
		tb = info.get('traceback')
		# If a traceback is present, automatically use the error log type.
		if tb and self._error_log_type is not None:
			log_type = self._error_log_type

		# Join the message parts into a single string.
		message = sep.join(str(m) for m in messages if m or not check_messages)

		# Construct the log header (e.g., '[INFO | 15/01/2026, 13:30:51]').
		header: list[str | None] = [
			log_type.ljust(self._max_log_type_length, ' ') if log_type else None,
			date,
		]
		header_string = '[' + " | ".join([h for h in header if h is not None]) + ']'

		# Assemble the final log content.
		content: list[str | None] = [
			header_string,
			message,
		]
		# If a traceback exists, format it and append it to the log.
		if tb:
			traceback_indent = len(header_string) + len(sep) - 1
			def print_indent(*_content: any):
				content.append("\n" + " " * traceback_indent + sep.join(_content))

			lines: list[tuple] = []

			_tb = traceback.extract_tb(tb, limit=self._logger_format.traceback_limit)

			for frame in _tb:
				lines.append(
					(f"'{frame.line}' in '{frame.name}'",
					 f"[{frame.lineno}]",
					 f'"{frame.filename}"')
				)

			print_indent(self._get_header('Traceback'))

			max_widths = []
			for line in lines:
				for index, item in enumerate(line):
					if index >= len(max_widths):
						max_widths.append(0)
					max_widths[index] = max(max_widths[index], len(str(item)))

			for line in lines:
				print_indent(*[str(item).ljust(max_widths[index], ' ') for index, item in enumerate(line)])
		content.append(end)
		_content = ' '.join(content)
		# Print to console if required.
		is_min_log = self._min_log_index <= self.log_types.index(log_type)
		if force_print if force_print is not None else (is_min_log if print_message is None else print_message and is_min_log):
			print(_content)
		# Write to file if not in print-only mode.
		if print_only or self._print_only:
			return
		self._write('\n' + _content)