from datetime import datetime, timedelta
import threading
from typing import Callable
from time import sleep

from utils.classes import Singleton
from utils.logger import Logger


class TasksHandler(Singleton):
	"""
	A singleton handler for managing and running background tasks using threading.

	This class allows for scheduling functions to run at regular intervals or at
	specific times, with control over starting, stopping, and managing the tasks.
	Being a singleton ensures that there is only one task manager instance across the application.
	"""
	def __init__(self, default_interval: timedelta = timedelta(minutes=15), dry: bool = False, log: bool = True, print_message: bool = True, **kwargs):
		"""
		Initializes the TasksHandler singleton instance.

		Args:
		    default_interval: The default time to wait between task executions if not specified.
		    dry (bool): If True, tasks will not actually execute their logic (a "dry run").
		    log (bool): If True, enables logging for task lifecycle events.
		    print_message (bool): If True, enables printing of task execution information.
		    **kwargs: Arbitrary keyword arguments that will be passed to every task function.
		              Useful for passing shared resources like a database connection.
		"""
		super().__init__()
		self._default_interval = default_interval
		self._event = threading.Event()  # A global event to signal all tasks to stop.
		self._tasks: list[tuple[str, Callable]] = []  # Stores tuples of (task_name, task_function).
		self._threads: list[threading.Thread] = []  # Holds the running thread objects.
		self._started = False  # A flag to track if the handler is active.
		self._kwargs = kwargs  # Stores shared arguments for all tasks.
		self._dry = dry
		self._log = log
		self._print_message = print_message

	@classmethod
	@Singleton.exists
	def started(cls):
		"""Returns True if the task handler has been started, False otherwise."""
		return cls._instance._started

	@classmethod
	@Singleton.exists
	def names(cls):
		"""Returns a list of the names of all registered tasks."""
		return [name for name, *_ in cls._instance._tasks]

	@classmethod
	@Singleton.exists
	def set_kwargs(cls, **kwargs):
		"""Sets or updates the shared keyword arguments that are passed to all tasks."""
		cls._instance._kwargs.update(kwargs)
	@classmethod
	@Singleton.exists
	def start(cls):
		"""Starts all registered tasks, each in its own background thread."""
		self = cls._instance
		try:
			self._event.set()  # Set the event, allowing the main loop in each task to run.

			for name, task in self._tasks:
				thread = threading.Thread(target=task)
				self._threads.append(thread)
				thread.name = name
				thread.daemon = True  # Allows the main program to exit even if threads are running.
				thread.start()

			self._started = True
		except Exception as error:
			return str(error)

	@classmethod
	@Singleton.exists
	def stop(cls):
		"""Stops all running tasks gracefully by clearing the run event."""
		self = cls._instance
		try:
			self._event.clear()  # Clear the event, causing the 'while' loop in each task to terminate.
			self._started = False
		except Exception as error:
			return str(error)

	@classmethod
	@Singleton.exists
	def delete(cls, name: str):
		"""Deletes a task definition. Can only be called before starting the handler."""
		self = cls._instance
		if self._started:
			raise RuntimeError("Cannot delete task when threads are started")
		for index, (task_name, task) in enumerate(self._tasks):
			if task_name != name:
				continue
			self._tasks.pop(index)

	@classmethod
	@Singleton.exists
	def get(cls, name: str):
		"""Retrieves the wrapped task function by its name."""
		self = cls._instance
		return next((task for task_name, task in self._tasks if task_name == name), None)

	@classmethod
	@Singleton.exists
	def event(cls, name: str):
		"""Manually triggers a single run of a registered task by its name."""
		self = cls._instance
		task = cls.get(name)
		if task is None:
			raise NameError(f"Task with '{name}' doesn't exist")
		task(*self._kwargs)

	@classmethod
	@Singleton.exists
	def set(
		cls,
		name: str,
		new: bool = True,
		start_time: timedelta | None = None,
		interval: timedelta = None,
		iterations: int | None = None,
		log: bool = None,
		dry: bool = None,
		print_message: bool = None,
		log_type: str = 'INFO'
	):
		"""
		A decorator factory to define and configure a new task.

		Args:
		    name: A unique name for the task.
		    new: If True, ensures the task name is new. If False, allows overwriting an existing task.
		    start_time: A timedelta from midnight to schedule the task's first run.
		    interval: A timedelta for the interval between task executions.
		    iterations: The total number of times the task should run. Runs indefinitely if None.
		    log: Overrides the handler's default log setting for this specific task.
		    dry: Overrides the handler's default dry run setting for this specific task.
		    print_message: Overrides the handler's default print info setting for this specific task.

		Returns:
		    A decorator to wrap the task function.
		"""
		self = cls._instance
		_dry = self._dry if dry is None else dry
		_log = self._log if log is None else log
		_print_message = self._print_message if print_message is None else print_message
		task_log = f"Task '{name}'"
		current_task_index = next(
			(index for index, (task_name, *_) in enumerate(self._tasks) if task_name == name),
			None
		)
		if current_task_index and new:
			raise NameError(f"{task_log} already exists")
		elif not current_task_index and not new:
			raise NameError(f"{task_log} doesn't exist")

		def task(func: Callable):
			sleep_time = max((interval or self._default_interval).total_seconds(), 1)

			# This is the wrapper function that will be executed in a separate thread.
			def wrapper(*args, **kwargs):
				# If a start_time is provided, calculate the next run time and sleep until then.
				if start_time:
					_start_time = datetime.replace(datetime.now(), hour=0, minute=0, second=0, microsecond=0) + start_time
					before = lambda: _start_time >= datetime.now()

					# Loop to find the next valid start time (today or tomorrow).
					while not before():
						_start_time += timedelta(days=1)

					Logger.log(task_log, f"will run at {_start_time}", log_type=log_type or 'INFO', print_only=not _log)
					sleep((_start_time - datetime.now()).total_seconds())

				return_value = None
				i = 0

				# A lambda to check all loop conditions at once.
				loop_check = lambda: (
						self._event.is_set() and
						(i < max(iterations, 0) if iterations else True) and
						(return_value is None or return_value is False)
				)
				# The main loop for the task.
				while loop_check():
					Logger.log(task_log, "started", log_type=log_type or 'INFO', print_only=not _log, print_message=_print_message)
					# Execute the user's original function if not a dry run.
					return_value = func(
						*args, **kwargs, **{
							'iteration'     : i,
							'max_iterations': iterations,
							'timestamp'     : datetime.timestamp(datetime.now()),
							**self._kwargs
						}
					) if not _dry else None
					if _dry:
						Logger.log(task_log, "dry run", log_type='DEBUG', print_only=True, print_message=_print_message)
					i += 1
					# Log the completion status of the current iteration.
					messages = [
						f"{task_log} finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
						f"{round(i / iterations * 100, 1)}% ({i}/{iterations})" if iterations else None,
						f"Next run at {(datetime.now() + timedelta(seconds=sleep_time)).strftime('%Y-%m-%d %H:%M:%S')}" if loop_check() else None,
					]
					Logger.log(*messages, log_type=log_type or 'INFO', sep=' | ', print_only=not _log, check_messages=True, print_message=_print_message)

					if loop_check(): sleep(sleep_time)

				Logger.log(task_log, "finished completely", log_type=log_type or 'INFO', print_only=not _log, print_message=_print_message)

			# Register the wrapped function with the handler.
			if new:
				self._tasks.append((name, wrapper))
			else:
				self._tasks.pop(current_task_index)
				self._tasks.append((name, wrapper))
			return wrapper

		return task