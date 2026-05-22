import os
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from time import sleep
from jinja2 import BaseLoader, Environment, select_autoescape

from utils.args import Args
import queue

from utils.config import Config
from utils.logger import Logger, LoggerFormat
from utils.tasks import TasksHandler


Args()
if Args.config_path.suffix not in ['.yml', '.yaml']:
        raise ValueError(f"Config file must have .yml or .yaml extension, got {Args.config_path.suffix}")

Config(Args.config_path)
if Config.logs.path.suffix != '.log':
    raise ValueError(f"Log file must have .log extension, got {Config.logs.path.suffix}")
Config.logs.path.parent.mkdir(exist_ok=True)

TasksHandler()
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

# Register tasks
def register_task():
    try:
        for conv in Config.conversion:
            if conv.name is None:
                raise ValueError('Task name is required')

            task_name_prefix = conv.name + '__'
            if conv.upload_dir is None: conv.upload_dir = Config.upload_dir
            if conv.output_dir is None: conv.output_dir = Config.output_dir

            if not conv.output_dir.is_absolute():
                raise ValueError(f'Output directory must be absolute, got {conv.output_dir}')
            if not conv.upload_dir.is_absolute():
                raise ValueError(f'Upload directory must be absolute, got {conv.upload_dir}')
            if conv.output_dir.is_relative_to(conv.upload_dir):
                raise ValueError(f'Output directory cannot be relative to upload directory, got {conv.output_dir}')

            Logger.log(f"Registering task '{conv.name}'", print_only=True)

            @TasksHandler.set(f'{task_name_prefix}watcher', interval=timedelta(seconds=conv.scan_interval), log=False, print_message=False)
            def watcher(**kwargs):
                paths: list[Path] = []
                for item in conv.upload_dir.rglob('*'):
                    if not item.is_file():
                        continue
                    if not conv.check(str(item), re.IGNORECASE):
                        continue
                    paths.append(item.relative_to(conv.upload_dir))
                if len(paths) > 0:
                    files_queue.put(paths)

            @TasksHandler.set(f'{task_name_prefix}worker', interval=timedelta(milliseconds=250))
            def worker(**kwargs):
                paths: list[Path] | None = files_queue.get()
                if paths is None:
                    return
                for path in paths:
                    Logger.log(f"Converting '{path}'", print_only=True)
                    match = re.match(conv.extract or '^.+$', str(path.name), re.IGNORECASE)

                    if match is None:
                        Logger.log(f"File '{path}' does not match pattern '{conv.extract}'", log_type='WARNING')
                        return

                    match_data = { '_' + str(index): value for index, value in enumerate(match.groups()) }

                    cmds: list[str] = conv.cmd
                    if isinstance(cmds, str):
                        cmds = [cmds]

                    for cmd in cmds:
                        template = env.from_string(cmd)
                        rendered = template.render(
                            **match.groupdict(),
                            args=match_data,
                            input=str(conv.upload_dir.joinpath(path)),
                            input_stem=str(path.stem),
                            input_name=str(path.name),
                            input_ext=str(path.suffix),
                            input_dir=conv.upload_dir,
                            output_dir=conv.output_dir,
                            tmp_dir=conv.tmp_dir,
                            cwd=Path.cwd()
                        )

                        try:
                            text = subprocess.run(rendered, check=True, shell=True, capture_output=True, text=True)
                            Logger.log(text.stdout)
                        except Exception as error:
                            Logger.log('Error executing command:', str(error), f'[CMD: "{rendered}"]', log_type='ERROR')
                            break

                    files_queue.task_done()
    except Exception as error:
        Logger.log(str(error), log_type='ERROR')

def init():
    Logger.log(f'Version: {os.getenv("VERSION") or "unknown"}')
    # import json
    # print(json.dumps(Config.data, indent=2))

    register_task()
    TasksHandler.start()
    while True:
        sleep(60 * 60 * 24)

if __name__ == '__main__':
    init()

