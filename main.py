import re
import subprocess
from datetime import timedelta
from pathlib import Path
from time import sleep
from jinja2 import BaseLoader, Environment, select_autoescape

from utils import get_dict_keys
from utils.args import Args
import queue

from utils.config import Command, Config, Job
from utils.database import Database
from utils.logger import Logger, LoggerFormat
from utils.tasks import TasksHandler
from utils.updater import Updater


try:
    from version import VERSION
except ImportError:
    VERSION = 'dev'

try:
    Args()
    if Args.config_path.suffix not in ['.yml', '.yaml']:
            raise ValueError(f"Config file must have .yml or .yaml extension, got {Args.config_path.suffix}")

    Config(Args.config_path)
    if Config.logs.path.suffix != '.log':
        raise ValueError(f"Log file must have .log extension, got {Config.logs.path.suffix}")

    TasksHandler()
    Updater(
        github_user_name='RadoslawDrab',
        github_repo_name='job-worker',
        current_version=VERSION,
        mock=Args.mock_update
    )
    Logger(
        Config.logs.path,
        default_log_type='DEBUG',
        error_log_type='ERROR',
        logger_format=LoggerFormat(show_traceback=True),
        min_log_level=Config.logs.level)

    files_queue = queue.Queue()
    env = Environment(
        loader=BaseLoader(),
        autoescape=select_autoescape()
    )
except Exception as error:
    print(str(error))
    input()

def register_job(job: Job):
    task_name_prefix = job.name + '__'
    upload_dir = Config.upload_dir if job.upload_dir is None else job.upload_dir
    output_dir = Config.output_dir if job.output_dir is None else job.output_dir
    tmp_dir = Config.tmp_dir if job.tmp_dir is None else job.tmp_dir
    max_iterations = (Config.max_iterations if job.max_iterations is None else job.max_iterations) or 0
    include_dirs = job.include_dirs if job.include_dirs is not None else Config.include_dirs
    scan_interval = max(job.scan_interval if job.scan_interval is not None else Config.scan_interval, 1)

    if not output_dir.is_absolute():
        raise ValueError(f'Output directory must be absolute, got {output_dir}')
    if not upload_dir.is_absolute():
        raise ValueError(f'Upload directory must be absolute, got {upload_dir}')
    if output_dir.is_relative_to(upload_dir):
        raise ValueError(f'Output directory cannot be relative to upload directory, got {output_dir}')

    upload_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    tmp_dir.mkdir(exist_ok=True)

    Database(tmp_dir.joinpath('db.json'), persistent=Config.db_persistent)

    Logger.log(f"Registering task '{job.name}'", print_only=True)

    @TasksHandler.set(f'{task_name_prefix}watcher', interval=timedelta(seconds=scan_interval), log=Config.logs.log_watcher, print_message=True, log_type='DEBUG')
    def watcher(**kwargs):
        paths: list[Path] = []
        for item in upload_dir.glob('**/*' if Config.recursive else '*'):
            if not item.is_file() and not item.is_dir() if include_dirs else not item.is_file():
                continue
            relative_item = item.relative_to(upload_dir)
            if not job.check(str(relative_item), re.IGNORECASE):
                continue
            paths.append(relative_item)

        if len(paths) > 0:
            files_queue.put(paths)

    @TasksHandler.set(f'{task_name_prefix}worker', interval=timedelta(milliseconds=250), log=Config.logs.log_worker, log_type='DEBUG')
    def worker(**kwargs):
        paths: list[Path] | None = files_queue.get()
        if paths is None:
            return
        for path in paths:
            posix_path = path.as_posix()
            current_iteration = Database.data[posix_path] or 0

            if current_iteration >= max_iterations > 0:
                Logger.log(f"File '{path}' has reached maximum iterations ({max_iterations})", log_type='WARNING', print_message=False)
                continue

            Logger.log(f"Processing '{path}'", print_only=True)
            global_match = re.match(job.extract or '^.+$', str(path.name), re.IGNORECASE)

            if global_match is None and job.skip_no_match:
                Logger.log(f"File '{path}' does not match pattern '{job.extract}'", log_type='WARNING', print_message=False)
                return

            def get_match_args(match: re.Match, start_index: int = 0):
                return { '_' + str(index + start_index): value for index, value in enumerate(match.groups()) }

            cmds: list[str | Command] = (job.cmd if isinstance(job.cmd, list) else [job.cmd]) if job.cmd else []

            for cmd in cmds:
                if isinstance(cmd, Command):
                    cmd_value: str = cmd.value
                    continue_on_error: bool = cmd.continue_on_error
                    extract: str | None = cmd.extract
                    show_error: bool = cmd.show_error if cmd.show_error is not None else True
                    skip_no_match: bool = cmd.skip_no_match
                else:
                    cmd_value = cmd
                    continue_on_error = Config.continue_on_error
                    extract = None
                    show_error = True
                    skip_no_match = job.skip_no_match

                if len(cmd_value) == 0:
                    Logger.log(f"Command is empty, skipping", log_type='WARNING')
                    continue

                match_kwargs = global_match.groupdict() if global_match is not None else {}
                match_args = get_match_args(global_match) if global_match is not None else {}
                if extract:
                    match = re.match(extract, str(path.name), re.IGNORECASE)
                    if match is not None:
                        match_kwargs.update(match.groupdict())
                        match_args = get_match_args(match)
                    elif match is None and skip_no_match:
                        Logger.log(f"File '{path}' does not match pattern '{extract}'", log_type='WARNING', print_message=False)
                        continue

                template = env.from_string(cmd_value)
                _kwargs = {
                    **match_kwargs,
                    'args': match_args,
                    'input': str(upload_dir.joinpath(path)),
                    'input_stem': str(path.stem),
                    'input_name': str(path.name),
                    'input_ext': str(path.suffix).lstrip('.'),
                    'input_dir': upload_dir,
                    'input_parent_dir': path.parent if path.parent != '.' else '',
                    'output_dir': output_dir,
                    'tmp_dir': tmp_dir,
                    'cwd': Path.cwd()
                }

                try:
                    rendered = template.render(**_kwargs, keys=get_dict_keys(_kwargs, include_dicts=True))

                    text = subprocess.run(rendered, check=True, shell=True, capture_output=True, text=True)
                    if len(text.stdout) > 0: Logger.log(text.stdout, log_type='INFO')
                except subprocess.CalledProcessError as error:
                    if show_error or not continue_on_error:
                        Logger.log(f'Error executing command: {str(error.stderr).strip()}', log_type='ERROR')
                        Logger.log(f'[Command: {str(error.cmd).lstrip()}]', log_type='ERROR', continue_message=True)
                    if not continue_on_error: break

            Database.data[posix_path] = current_iteration + 1

            Database.save()
        files_queue.task_done()
# Register tasks
def register_jobs():
    for job in Config.jobs:
        if job.name is None:
            raise ValueError('Task name is required')
        if job.cmd is None:
            raise ValueError('Command is required')
        register_job(job)


def init():
    try:
        update = Updater.check() if not Args.no_update else None
        if Args.mock_update:
            if update is None:
                Logger.log('No update available', force_print=True, print_only=True)
                return
            Logger.log(f'Latest version: {update[0]}', force_print=True, print_only=True)
            Logger.log(f'Download url: {update[1]}', force_print=True, continue_message=True, print_only=True)
            return

        if update:
            Updater.apply(update[1])
        else:
            Logger.log(f'Version: {VERSION}', force_print=True)

        register_jobs()
        TasksHandler.start()
        while True:
            sleep(60 * 60 * 24)
    except Exception as error:
        Logger.log(str(error), log_type='ERROR')
        input()
if __name__ == '__main__':
    init()

